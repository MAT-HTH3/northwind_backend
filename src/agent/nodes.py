"""Graph nodes. Each node is thin; the logic lives in its own module."""

from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from src.agent.auto_resolver import respond
from src.agent.cards import UI_CARDS, receipt_card
from src.agent.case_status import case_status_reply
from src.agent.categorizer import categorize
from src.agent.context import GraphContext
from src.agent.readings import check_reading, revised_amount
from src.agent.state import ResumeValue, SupportState, history_from
from src.agent.transcript import written_by_code
from src.agent.unified_desktop import UK, hand_off, reply
from src.history import build_history
from src.models import ReadingStatus, Service
from src.models.types import utcnow
from src.repositories import ReadingRepository, SupportCaseRepository

GraphRuntime = Runtime[GraphContext]


async def analyzer(state: SupportState, runtime: GraphRuntime) -> dict:
    """The memory bridge. Plain Python, no LLM; runs every turn so the history is never stale."""
    history = await build_history(
        state["account_id"], runtime.context.legacy, runtime.context.session_factory
    )
    return {"history": history.model_dump(mode="json")}


async def categorizer(state: SupportState, runtime: GraphRuntime) -> dict:
    force_handoff = state.get("force_handoff", False)
    result = await categorize(
        runtime.context.categorizer_llm, state["messages"], force_handoff=force_handoff
    )
    is_self_service, reading_check = result.is_self_service, None
    if result.meter_reading is not None:
        # Code, not the model, decides whether a reading is accepted (ADR 0004).
        check = check_reading(
            history_from(state), result.meter_reading.service, result.meter_reading.value
        )
        reading_check = "accepted" if check.plausible and not force_handoff else "needs_review"
        is_self_service = reading_check == "accepted"
    return {
        "is_self_service": is_self_service,
        "reading_check": reading_check,
        "category": result.category,
        "subject": result.subject,
        "disputed_amount": result.disputed_amount,
        "case_status_request": result.case_status_request,
        "reason": result.reason,
        "meter_reading": result.meter_reading.model_dump() if result.meter_reading else None,
        "force_handoff": False,  # the "No" override applies to one message only
    }


def route_after_categorizer(
    state: SupportState,
) -> Literal["accept_reading", "case_status", "auto_resolver", "unified_desktop"]:
    if state.get("reading_check") == "accepted":
        return "accept_reading"
    if not state["is_self_service"]:
        return "unified_desktop"
    return "case_status" if state.get("case_status_request") else "auto_resolver"


async def case_status(state: SupportState, runtime: GraphRuntime) -> dict:
    """Where the customer's cases stand, written by code from the history. No LLM."""
    return {"messages": [case_status_reply(history_from(state))], "topic": "Case status checked"}


async def accept_reading(state: SupportState, runtime: GraphRuntime) -> dict:
    """A plausible Customer Reading: saved, the bill re-priced, a receipt shown. No LLM, no case."""
    mention, history = state["meter_reading"], history_from(state)
    check = check_reading(history, mention["service"], mention["value"])
    revised = revised_amount(history, mention["service"], check.usage)
    async with runtime.context.session_factory() as session:
        reading = await ReadingRepository(session).create(
            account_id=state["account_id"],
            conversation_id=state["conversation_id"],
            service=Service(mention["service"]),
            value=mention["value"],
            read_date=utcnow().astimezone(UK).date(),
            status=ReadingStatus.ACCEPTED,
        )
        await session.commit()
    previous = history.billing.bills[0].amount_due if history.billing else None
    direction = "comes down to" if previous is not None and revised < previous else "is now"
    text = (
        f"Thanks, I've recorded your {reading.service.value} reading of "
        f"**{reading.value:,} {reading.unit}**. Your latest bill has been recalculated with it, "
        f"so it {direction} **£{revised:,.2f}**."
    )
    return {
        "meter_reading": None,
        "reading_check": None,
        "topic": "Reading accepted",
        "messages": [
            written_by_code(
                text,
                summary="The assistant accepted the customer's meter reading and showed the "
                "recalculated bill on screen.",
                **{UI_CARDS: [receipt_card(reading, revised)]},
            )
        ],
    }


async def auto_resolver(state: SupportState, runtime: GraphRuntime) -> dict:
    """Answers a Self-service request. Loops through the tools node while Gemini calls tools."""
    reply = await respond(runtime.context.resolver_llm, state["messages"])
    if reply.tool_calls:
        return {"messages": [reply]}
    return {"messages": [reply], "topic": resolver_topic(state["messages"])}


def resolver_topic(messages: list) -> str:
    """ "Bill explained" if the bill card was shown for the latest message."""
    latest = next(i for i in range(len(messages) - 1, -1, -1) if messages[i].type == "human")
    shown = any(m.type == "tool" and m.name == "show_bill_breakdown" for m in messages[latest:])
    return "Bill explained" if shown else "Question answered"


def route_after_auto_resolver(state: SupportState) -> Literal["resolver_tools", "__end__"]:
    last = state["messages"][-1]
    return "resolver_tools" if getattr(last, "tool_calls", None) else "__end__"


async def unified_desktop(state: SupportState, runtime: GraphRuntime) -> dict:
    """Hands the request to a Human Agent, then the graph waits at the hold."""
    result = await hand_off(
        session_factory=runtime.context.session_factory,
        account_id=state["account_id"],
        conversation_id=state["conversation_id"],
        category=state.get("category"),
        subject=state.get("subject"),
        disputed_amount=state.get("disputed_amount"),
        meter_reading=state.get("meter_reading"),
        messages=state["messages"],
        history=history_from(state),
        now=utcnow(),
    )
    return {
        "case_id": result.case.id,
        "case_outcome": None,
        "meter_reading": None,
        "reading_check": None,
        "topic": "Handed to a person",
        "messages": [reply(result)],
    }


async def wait(
    state: SupportState, runtime: GraphRuntime
) -> Command[Literal["acknowledge", "close"]]:
    """The hold. Pauses until the customer writes again or the Human Agent closes the case.

    Every customer message arrives as a resume, not a new run: a new run would discard this
    pending interrupt and the Human Agent could no longer resume the thread (ADR 0001).
    """
    resume: ResumeValue = interrupt({"case_id": state["case_id"]})
    if resume["kind"] == "customer_message":
        return Command(goto="acknowledge", update={"messages": [HumanMessage(resume["content"])]})
    return Command(goto="close", update={"case_outcome": resume["outcome"]})


def acknowledgement(case_id: str) -> str:
    return f"Your case {case_id} is with our team. I've added this to it so they'll see it."


async def acknowledge(state: SupportState, runtime: GraphRuntime) -> dict:
    """Adds the held message to the Support Case and replies without the LLM."""
    content = state["messages"][-1].content
    async with runtime.context.session_factory() as session:
        repo = SupportCaseRepository(session)
        case = await repo.get(state["case_id"])
        await repo.add_held_message(case, state["conversation_id"], content)
        await session.commit()
    return {
        "messages": [
            written_by_code(
                acknowledgement(state["case_id"]),
                summary="The assistant added the customer's message to their open case, which "
                "a person is handling.",
            )
        ]
    }


async def close(state: SupportState, runtime: GraphRuntime) -> dict:
    """The case is closed (the Human Agent API has already recorded it). The conversation is
    live again; the Case Outcome stays in state for the AI Assistant to refer to."""
    return {"case_id": None}
