from datetime import UTC, date, datetime

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.case_status import case_status_text
from src.agent.categorizer import Categorization
from src.agent.graph import build_graph
from src.agent.transcript import WRITTEN_BY_CODE
from src.agent.turns import thread_config, turn_input
from src.history import build_history
from src.history.models import SupportCaseSummary
from src.legacy import get_legacy_systems
from tests.fakes import FakeLLM, fake_context

ACCOUNT = "ACC-DEMO01"


@pytest.fixture
async def history(session_factory):
    return await build_history(ACCOUNT, get_legacy_systems(), session_factory)


def case(case_id, status="open", outcome=None, queue="Billing specialists"):
    return SupportCaseSummary(
        case_id=case_id,
        category="Billing",
        priority="P2",
        status=status,
        queue=queue,
        opened_at=datetime(2026, 9, 20, 9, tzinfo=UTC),
        expected_response_by=date(2026, 10, 6),
        closed_at=datetime(2026, 9, 28, 15, tzinfo=UTC) if status == "closed" else None,
        outcome=outcome,
    )


def with_cases(history, *cases):
    return history.model_copy(update={"support_cases": list(cases)})


def test_an_open_case_gives_its_team_and_reply_date(history):
    text = case_status_text(with_cases(history, case("NW-100001")))

    assert text == (
        "Your case **NW-100001** is with our billing team. They'll reply by **Tuesday 6 October**."
    )


def test_several_open_cases_are_all_listed(history):
    text = case_status_text(
        with_cases(history, case("NW-100001"), case("NW-100002", queue="Field operations"))
    )

    assert "**NW-100001** is with our billing team" in text
    assert "**NW-100002** is with our field team" in text


def test_a_resolved_case_gives_its_outcome_in_plain_words(history):
    text = case_status_text(with_cases(history, case("NW-100001", "closed", "bill_corrected")))

    assert text == (
        "Your case **NW-100001** was resolved on **Monday 28 September**: we corrected your bill."
    )


def test_open_cases_come_before_resolved_ones(history):
    text = case_status_text(
        with_cases(history, case("NW-100002", "closed", "refund_issued"), case("NW-100001"))
    )

    assert text.startswith("Your case **NW-100001** is with our billing team")


def test_with_no_support_cases_it_falls_back_to_the_latest_legacy_case(history):
    text = case_status_text(history)

    assert text == (
        "I can't see an open case for you. Your most recent one, **CT-88123** (query about an "
        "estimated bill), was closed on **Wednesday 19 August**. If you need more help, I can put "
        "you through to a person."
    )


def test_with_no_cases_at_all_it_offers_a_person(history):
    text = case_status_text(history.model_copy(update={"support_cases": [], "past_cases": []}))

    assert (
        text == "I can't see any cases for you. If you'd like, I can put you through to a person."
    )


async def test_the_route_answers_without_the_model(session_factory):
    llm = FakeLLM(
        lambda _m: Categorization(
            is_self_service=True, category="Service", reason="fake", case_status_request=True
        )
    )
    graph = build_graph(InMemorySaver())
    payload = await turn_input(
        graph, conversation_id="c1", account_id=ACCOUNT, message="Any update on my complaint?"
    )

    state = await graph.ainvoke(
        payload, thread_config("c1"), context=fake_context(session_factory, llm)
    )

    reply = state["messages"][-1]
    assert reply.text.startswith(
        "I can't see an open case for you. Your most recent one, **CT-88123**"
    )
    assert reply.additional_kwargs[WRITTEN_BY_CODE]
    assert llm.tool_calls == []  # the Auto-Resolver's model was never called


async def test_a_case_question_that_asks_for_a_person_is_still_handed_off(session_factory):
    llm = FakeLLM(
        lambda _m: Categorization(
            is_self_service=False, category="Service", reason="fake", case_status_request=True
        )
    )
    graph = build_graph(InMemorySaver())
    payload = await turn_input(
        graph, conversation_id="c1", account_id=ACCOUNT, message="Nobody replied, get me a person"
    )

    state = await graph.ainvoke(
        payload, thread_config("c1"), context=fake_context(session_factory, llm)
    )

    assert state["case_id"] is not None
