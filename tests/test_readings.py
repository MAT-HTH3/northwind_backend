"""ADR 0004: plausible readings are accepted and re-priced by code; others go to a Human Agent."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.bill_breakdown import build_bill_breakdown
from src.agent.categorizer import Categorization, MeterReadingMention
from src.agent.graph import build_graph
from src.agent.readings import check_reading, revised_amount
from src.agent.turns import is_held, thread_config, turn_input
from src.history import build_history
from src.legacy import get_legacy_systems
from src.models import ReadingStatus, Service
from src.repositories import ReadingRepository, SupportCaseRepository
from tests.fakes import FakeLLM, fake_context

ACCOUNT = "ACC-DEMO01"


@pytest.fixture
async def history(session_factory):
    return await build_history(ACCOUNT, get_legacy_systems(), session_factory)


# The current bill opened at 47,871 kWh (an estimate); the last actual read was 47,242.
@pytest.mark.parametrize(
    ("value", "plausible", "usage"),
    [
        (48213, True, 342),  # the demo reading
        (49871, True, 2000),  # the most a bill period can plausibly use
        (49872, False, 2001),
        (47500, False, -371),  # above the last actual read, below the estimate the bill used
        (47000, False, -871),  # below the last actual read
        (47871, False, 0),  # no usage at all
    ],
)
def test_the_plausibility_check(history, value, plausible, usage):
    check = check_reading(history, "electricity", value)

    assert (check.plausible, check.usage) == (plausible, usage)


def test_the_demo_reading_re_prices_the_bill_like_the_widget(history):
    assert revised_amount(history, "electricity", 342) == 132.01


def test_a_water_reading_is_checked_in_cubic_metres(history):
    assert check_reading(history, "water", 612).plausible  # 8.8 m³ since the bill opened
    assert not check_reading(history, "water", 900).plausible


def reading_llm(value):
    return FakeLLM(
        lambda _m: Categorization(
            is_self_service=False,  # the model's view doesn't matter: code decides
            category="Meter reading",
            reason="fake",
            meter_reading=MeterReadingMention(service=Service.ELECTRICITY, value=value),
        )
    )


async def test_a_plausible_reading_is_accepted_without_a_case(session_factory):
    graph = build_graph(InMemorySaver())
    context = fake_context(session_factory, reading_llm(48213))
    payload = await turn_input(graph, conversation_id="c1", account_id=ACCOUNT, message="48213")

    state = await graph.ainvoke(payload, thread_config("c1"), context=context)

    async with session_factory() as session:
        [saved] = await ReadingRepository(session).list_for_account(ACCOUNT)
        assert await SupportCaseRepository(session).list_all() == []
    assert (saved.status, saved.case_id) == (ReadingStatus.ACCEPTED, None)
    [receipt] = state["messages"][-1].additional_kwargs["ui_cards"]
    assert receipt["result"]["status"] == "accepted"
    assert receipt["result"]["revised_amount_due"] == 132.01
    assert "comes down to **£132.01**" in state["messages"][-1].text
    assert not await is_held(graph, "c1")


async def test_after_acceptance_the_bill_card_shows_the_re_priced_bill(session_factory):
    graph = build_graph(InMemorySaver())
    context = fake_context(session_factory, reading_llm(48213))
    payload = await turn_input(graph, conversation_id="c1", account_id=ACCOUNT, message="48213")
    await graph.ainvoke(payload, thread_config("c1"), context=context)

    history = await build_history(ACCOUNT, get_legacy_systems(), session_factory)
    card = build_bill_breakdown(history)

    assert (card.amount_due, card.reading_type) == (132.01, "actual")
    assert card.lines[0].quantity == 342
    assert card.change_reasons[0].startswith(
        "Recalculated from your electricity meter reading of 48,213 kWh"
    )


async def test_after_a_no_even_a_plausible_reading_goes_to_a_person(session_factory):
    graph = build_graph(InMemorySaver())
    context = fake_context(session_factory, reading_llm(48213))
    payload = await turn_input(graph, conversation_id="c1", account_id=ACCOUNT, message="48213")
    payload["force_handoff"] = True

    await graph.ainvoke(payload, thread_config("c1"), context=context)

    assert await is_held(graph, "c1")
