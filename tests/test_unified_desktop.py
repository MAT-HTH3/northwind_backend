from datetime import date, timedelta

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.categorizer import Categorization, MeterReadingMention
from src.agent.graph import build_graph
from src.agent.transcript import transcript_text
from src.agent.turns import is_held, thread_config, turn_input
from src.agent.unified_desktop import UI_CARDS
from src.models import CaseStatus, Priority, ReadingStatus, Service
from src.repositories import ReadingRepository, SupportCaseRepository
from src.schemas.cards import MeterReadingReceipt, SupportCaseCard
from tests.fakes import FAKE_SUMMARY, FakeLLM, fake_context

ACCOUNT = "ACC-DEMO01"
TODAY = date.today()


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


async def test_a_new_case_is_routed_by_category(graph, session_factory):
    context = fake_context(session_factory, hand_off_as("Supply fault - repair needed"))

    state = await send(graph, context, "c1", "Water is leaking by my meter")

    [case], _ = await stored(session_factory)
    assert (case.category, case.priority, case.sla_days, case.queue) == (
        "Supply fault - repair needed",
        Priority.HIGH,
        5,
        "Field engineers",
    )
    assert case.expected_response_by == TODAY + timedelta(days=5)
    assert case.summary == FAKE_SUMMARY and case.status == CaseStatus.OPEN

    message = state["messages"][-1]
    [card] = message.additional_kwargs[UI_CARDS]
    assert card["name"] == "create_support_case"
    assert SupportCaseCard.model_validate(card["result"]).case_id == case.id
    assert f"**{case.id}**" in message.content and "our engineers" in message.content
    assert await is_held(graph, "c1")


async def test_a_meter_reading_is_saved_and_its_receipt_comes_first(graph, session_factory):
    reading = MeterReadingMention(service=Service.ELECTRICITY, value=48213)
    context = fake_context(session_factory, hand_off_as("General enquiry", reading))

    state = await send(graph, context, "c1", "My meter says 48213")

    [case], [saved] = await stored(session_factory)
    assert case.category == "Meter reading review"  # the Categorizer's rule
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
    context = fake_context(session_factory, hand_off_as("Billing - dispute or refund"))
    await send(graph, context, "c1", "I want a refund")

    state = await send(graph, context, "c2", "Following up on my refund")

    [case], _ = await stored(session_factory)
    assert [link.conversation_id for link in case.conversations] == ["c1", "c2"]
    assert state["messages"][-1].content.startswith(
        f"I've added this to your open case **{case.id}**"
    )
    assert await is_held(graph, "c1") and await is_held(graph, "c2")


async def test_a_different_topic_opens_its_own_case(graph, session_factory):
    await send(
        graph, fake_context(session_factory, hand_off_as("Meter fault")), "c1", "Meter broken"
    )

    await send(
        graph,
        fake_context(session_factory, hand_off_as("Billing - dispute or refund")),
        "c2",
        "Refund",
    )

    cases, _ = await stored(session_factory)
    assert sorted(c.category for c in cases) == ["Billing - dispute or refund", "Meter fault"]


async def test_the_hand_off_survives_a_summary_failure(graph, session_factory):
    llm = hand_off_as("Meter fault")
    llm.summary = RuntimeError("Gemini unavailable")

    await send(graph, fake_context(session_factory, llm), "c1", "My meter display is blank")

    [case], _ = await stored(session_factory)
    assert case.summary.startswith("Sarah Whitfield (North) was handed off as Meter fault.")
    assert "My meter display is blank" in case.summary


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
