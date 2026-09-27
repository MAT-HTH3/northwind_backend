from datetime import timedelta

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.categorizer import Categorization, MeterReadingMention
from src.agent.graph import build_graph
from src.agent.transcript import WRITTEN_BY_CODE, transcript_text
from src.agent.turns import is_held, thread_config, turn_input
from src.agent.unified_desktop import UI_CARDS, UK
from src.models import CaseStatus, ReadingStatus, Service, Urgency
from src.models.types import utcnow
from src.repositories import ReadingRepository, SupportCaseRepository
from src.schemas.cards import MeterReadingReceipt, SupportCaseCard
from tests.fakes import FakeLLM, fake_context

ACCOUNT = "ACC-DEMO01"
TODAY = utcnow().astimezone(UK).date()


def hand_off_as(category, reading=None):
    return FakeLLM(
        lambda _messages: Categorization(
            is_self_service=False, category=category, reason="fake", meter_reading=reading
        )
    )


async def send(graph, context, conversation_id, message):
    payload = await turn_input(
        graph, conversation_id=conversation_id, account_id=ACCOUNT, message=message
    )
    return await graph.ainvoke(payload, thread_config(conversation_id), context=context)


async def stored(session_factory):
    async with session_factory() as session:
        cases = await SupportCaseRepository(session).list_all()
        readings = await ReadingRepository(session).list_for_account(ACCOUNT)
        return cases, readings


@pytest.fixture
def graph():
    return build_graph(InMemorySaver())


@pytest.mark.parametrize(
    ("message", "urgency", "sla_days"),
    [
        ("Water is leaking by my meter", Urgency.MEDIUM, 10),  # Supply 20 + assistant 10
        ("We have no power at all", Urgency.HIGH, 2),  # + no supply 40
    ],
)
async def test_a_new_case_is_triaged_like_the_desk(
    graph, session_factory, message, urgency, sla_days
):
    context = fake_context(session_factory, hand_off_as("Supply"))

    state = await send(graph, context, "c1", message)

    [case], _ = await stored(session_factory)
    due = (utcnow() + timedelta(days=sla_days)).astimezone(UK).date()
    assert (case.category, case.priority, case.sla_days, case.queue) == (
        "Supply",
        urgency,
        sla_days,
        "Field operations",
    )
    assert case.expected_response_by == due
    assert case.summary.startswith("Other supply problem, raised in chat.")
    assert case.status == CaseStatus.OPEN

    message = state["messages"][-1]
    [card] = message.additional_kwargs[UI_CARDS]
    assert card["name"] == "create_support_case"
    parsed = SupportCaseCard.model_validate(card["result"])
    assert (parsed.case_id, parsed.priority, parsed.queue) == (
        case.id,
        urgency.value,
        "Field operations",
    )
    assert f"**{case.id}**" in message.content and "our field team" in message.content
    assert await is_held(graph, "c1")


async def test_an_earlier_case_counts_as_repeat_contact(graph, session_factory):
    context = fake_context(session_factory, hand_off_as("Billing"))
    await send(graph, context, "c1", "Please call me about my bill")  # Billing 10 + assistant 10
    async with session_factory() as session:
        repo = SupportCaseRepository(session)
        await repo.close(await repo.get((await repo.list_all())[0].id), "information_only")
        await session.commit()

    await send(graph, context, "c2", "Please call me about my bill again")  # + repeat 20

    cases, _ = await stored(session_factory)
    assert sorted(c.priority for c in cases) == [Urgency.MEDIUM, Urgency.LOW]


async def test_a_meter_reading_is_saved_and_its_receipt_comes_first(graph, session_factory):
    reading = MeterReadingMention(service=Service.ELECTRICITY, value=48213)
    context = fake_context(session_factory, hand_off_as("Service", reading))

    state = await send(graph, context, "c1", "My meter says 48213")

    [case], [saved] = await stored(session_factory)
    assert case.category == "Meter reading"  # the Categorizer's rule
    assert (saved.value, saved.status, saved.case_id, saved.read_date) == (
        48213,
        ReadingStatus.AWAITING_REVIEW,
        case.id,
        TODAY,
    )
    message = state["messages"][-1]
    receipt, case_card = message.additional_kwargs[UI_CARDS]
    assert [receipt["name"], case_card["name"]] == ["submit_meter_reading", "create_support_case"]
    assert receipt["args"] == {"service": "electricity", "value": 48213}
    assert MeterReadingReceipt.model_validate(receipt["result"]).reading_id == saved.id
    assert message.content.startswith(
        "Thanks, I've recorded your electricity reading of **48,213 kWh**"
    )
    assert state["meter_reading"] is None


async def test_a_second_conversation_on_the_same_topic_joins_the_open_case(graph, session_factory):
    context = fake_context(session_factory, hand_off_as("Billing"))
    await send(graph, context, "c1", "I want a refund")

    state = await send(graph, context, "c2", "Following up on my refund")

    [case], _ = await stored(session_factory)
    assert [link.conversation_id for link in case.conversations] == ["c1", "c2"]
    assert state["messages"][-1].content.startswith(
        f"I've added this to your open case **{case.id}**"
    )
    assert await is_held(graph, "c1") and await is_held(graph, "c2")


async def test_a_different_topic_opens_its_own_case(graph, session_factory):
    await send(graph, fake_context(session_factory, hand_off_as("Supply")), "c1", "Meter broken")

    await send(
        graph,
        fake_context(session_factory, hand_off_as("Billing")),
        "c2",
        "Refund",
    )

    cases, _ = await stored(session_factory)
    assert sorted(c.category for c in cases) == ["Billing", "Supply"]


async def test_the_summary_is_written_by_code_from_the_case_facts(graph, session_factory):
    reading = MeterReadingMention(service=Service.ELECTRICITY, value=48213)
    await send(
        graph, fake_context(session_factory, hand_off_as("Service", reading)), "c1", "It says 48213"
    )

    [case], _ = await stored(session_factory)
    assert case.summary == (
        "Reading needs checking, raised in chat. The customer said: “It says 48213”. "
        "Meter reading given: 48,213 kWh (electricity). "
        "Latest bill INV-2609-DEMO01: £169.60, estimated reading, due 5 October. "
        "Earlier case CT-88123: Query about an estimated bill, closed, reopened 1×."
    )


async def test_hand_off_replies_are_marked_as_written_by_code(graph, session_factory):
    await send(graph, fake_context(session_factory, hand_off_as("Supply")), "c1", "No power")

    state = await send(graph, fake_context(session_factory), "c1", "Any update?")

    hand_off_reply, _, acknowledgement = state["messages"][-3:]
    assert hand_off_reply.additional_kwargs[WRITTEN_BY_CODE]
    assert acknowledgement.additional_kwargs[WRITTEN_BY_CODE]


def test_transcript_text_shows_cards_and_skips_tool_data():
    messages = [
        HumanMessage("Why is my bill so high?"),
        AIMessage("", tool_calls=[{"id": "c1", "name": "show_bill_breakdown", "args": {}}]),
        ToolMessage('{"amount_due": 169.6}', tool_call_id="c1"),
        AIMessage("It's estimated."),
    ]

    assert transcript_text(messages) == (
        "Customer: Why is my bill so high?\n"
        "[AI Assistant showed show_bill_breakdown]\n"
        "AI Assistant: It's estimated."
    )
