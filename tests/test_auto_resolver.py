import json
from datetime import date

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.bill_breakdown import BillNotFoundError, build_bill_breakdown
from src.agent.graph import build_graph
from src.agent.transcript import recent_messages
from src.agent.turns import is_held, thread_config, turn_input
from src.history import build_history
from src.history.models import Tariff
from src.legacy import get_legacy_systems
from src.schemas.bill import BillBreakdown
from tests.fakes import FakeLLM, fake_context

ACCOUNT = "ACC-DEMO01"


@pytest.fixture
async def history(session_factory):
    return await build_history(ACCOUNT, get_legacy_systems(), session_factory)


def test_latest_bill_breakdown(history):
    b = build_bill_breakdown(history)

    assert (b.bill_id, b.amount_due, b.previous_amount) == ("INV-2609-DEMO01", 169.6, 118.39)
    assert (b.payment_method, b.reading_type) == ("Direct Debit", "estimated")
    assert (b.due_date, b.last_actual_read_date) == (date(2026, 10, 5), date(2026, 6, 12))
    assert round(sum(line.amount for line in b.lines), 2) == b.amount_due
    assert [u.month for u in b.usage_history] == [
        "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"
    ]  # fmt: skip
    assert b.change_reasons == [
        "It uses an estimated electricity reading. We haven't had an actual reading since 12 June.",
        "We estimated 486 kWh. Your last three actual readings averaged 338 kWh.",
    ]


def test_an_older_bill_has_no_previous_amount_and_no_later_usage(history):
    b = build_bill_breakdown(history, "INV-2608-DEMO01")

    assert (b.amount_due, b.previous_amount) == (118.39, None)
    assert b.usage_history[-1].month == "2026-08"


def test_unknown_bill_id_raises(history):
    with pytest.raises(BillNotFoundError):
        build_bill_breakdown(history, "INV-0000")


def test_a_rate_change_since_the_previous_bill_is_a_reason(history):
    rise = Tariff(
        service="electricity", component="unit", effective_from=date(2026, 8, 20), rate=0.2612
    )
    changed = history.model_copy(
        update={"billing": history.billing.model_copy(
            update={"tariffs": [*history.billing.tariffs, rise]}
        )}
    )  # fmt: skip

    reasons = build_bill_breakdown(changed).change_reasons

    assert (
        reasons[-1] == "The electricity unit rate rose on 20 August, from 24.86p to 26.12p per kWh."
    )


def test_transcript_window_never_starts_with_an_orphaned_tool_result():
    messages = [
        HumanMessage("Why is my bill so high?"),
        AIMessage("", tool_calls=[{"id": "c1", "name": "show_bill_breakdown", "args": {}}]),
        ToolMessage("{}", tool_call_id="c1"),
        AIMessage("Here it is."),
        HumanMessage("Thanks"),
        AIMessage("You're welcome."),
    ]

    assert recent_messages(messages, 3) == messages[4:]
    assert recent_messages(messages, 5) == messages[4:]
    assert recent_messages(messages, 6) == messages
    # Mid tool loop, no customer message inside the limit: stretch back to the latest one.
    assert recent_messages(messages[:3], 1) == messages[:3]


async def test_bill_question_calls_the_tool_then_answers(session_factory):
    llm = FakeLLM(
        replies=[
            AIMessage("", tool_calls=[{"id": "c1", "name": "show_bill_breakdown", "args": {}}]),
            AIMessage("Your bill is **£169.60**, mainly because it's estimated."),
        ]
    )
    context = fake_context(session_factory, llm)
    graph = build_graph(InMemorySaver())

    payload = await turn_input(
        graph, conversation_id="c1", account_id=ACCOUNT, message="Why is my bill so high?"
    )
    state = await graph.ainvoke(payload, thread_config("c1"), context=context)

    human, call, result, answer = state["messages"]
    assert call.tool_calls[0]["name"] == "show_bill_breakdown"
    card = BillBreakdown.model_validate(json.loads(result.content))
    assert (result.tool_call_id, card.amount_due) == ("c1", 169.6)
    assert answer.content.startswith("Your bill is **£169.60**")
    assert len(llm.tool_calls) == 2  # Gemini saw the tool result before answering
    assert not await is_held(graph, "c1")


async def test_an_unknown_bill_goes_back_to_gemini_instead_of_crashing(session_factory):
    llm = FakeLLM(
        replies=[
            AIMessage(
                "",
                tool_calls=[
                    {"id": "c1", "name": "show_bill_breakdown", "args": {"bill_id": "INV-JULY"}}
                ],
            ),
            AIMessage("I can see your August and September bills."),
        ]
    )
    context = fake_context(session_factory, llm)
    graph = build_graph(InMemorySaver())

    payload = await turn_input(
        graph, conversation_id="c1", account_id=ACCOUNT, message="July bill?"
    )
    state = await graph.ainvoke(payload, thread_config("c1"), context=context)

    result = state["messages"][2]
    assert result.status == "error"
    assert "INV-2609-DEMO01" in result.content and "INV-2608-DEMO01" in result.content
    assert state["messages"][-1].content == "I can see your August and September bills."
