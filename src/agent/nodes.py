"""Graph nodes. Auto-Resolver and Unified Desktop are stubs for now (#18, #19)."""

from datetime import timedelta
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from src.agent.categorizer import categorize
from src.agent.context import GraphContext
from src.agent.state import ResumeValue, SupportState, history_from
from src.history import build_history
from src.models import Priority
from src.models.types import utcnow
from src.repositories import SupportCaseRepository

GraphRuntime = Runtime[GraphContext]


async def analyzer(state: SupportState, runtime: GraphRuntime) -> dict:
    """The memory bridge. Plain Python, no LLM; runs every turn so the history is never stale."""
    history = await build_history(
        state["account_id"], runtime.context.legacy, runtime.context.session_factory
    )
    return {"history": history.model_dump(mode="json")}


async def categorizer(state: SupportState, runtime: GraphRuntime) -> dict:
    result = await categorize(
        runtime.context.llm,
        state["messages"],
        history_from(state),
        force_handoff=state.get("force_handoff", False),
    )
    return {
        "is_self_service": result.is_self_service,
        "category": result.category,
        "reason": result.reason,
        "meter_reading": result.meter_reading.model_dump() if result.meter_reading else None,
        "force_handoff": False,  # the "No" override applies to one message only
    }


def route_after_categorizer(state: SupportState) -> Literal["auto_resolver", "unified_desktop"]:
    return "auto_resolver" if state["is_self_service"] else "unified_desktop"


async def auto_resolver(state: SupportState, runtime: GraphRuntime) -> dict:
    # TODO(#18): Gemini tool-calling agent with show_bill_breakdown.
    return {"messages": [AIMessage("(Auto-Resolver not built yet)")]}


async def unified_desktop(state: SupportState, runtime: GraphRuntime) -> dict:
    # TODO(#19): category table, join an open case, AI summary, reading receipt, case card.
    async with runtime.context.session_factory() as session:
        case = await SupportCaseRepository(session).create(
            account_id=state["account_id"],
            conversation_id=state["conversation_id"],
            category="General enquiry",
            priority=Priority.LOW,
            sla_days=20,
            queue="Customer care",
            expected_response_by=(utcnow() + timedelta(days=20)).date(),
            summary="(summary not built yet)",
        )
        await session.commit()
    return {
        "case_id": case.id,
        "case_outcome": None,
        "messages": [AIMessage(f"I've passed this to our team. Your case number is {case.id}.")],
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
    return {"messages": [AIMessage(acknowledgement(state["case_id"]))]}


async def close(state: SupportState, runtime: GraphRuntime) -> dict:
    """The case is closed (the Human Agent API has already recorded it). The conversation is
    live again; the Case Outcome stays in state for the AI Assistant to refer to."""
    return {"case_id": None}
