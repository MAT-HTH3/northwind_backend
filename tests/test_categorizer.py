from typing import get_args

import pytest
from langchain_core.messages import HumanMessage

from src.agent.categories import TEAM, Category
from src.agent.categorizer import Categorization, MeterReadingMention, categorize
from src.history import build_history
from src.legacy import get_legacy_systems
from src.models import Service
from tests.fakes import FakeLLM

MESSAGES = [HumanMessage("hello")]


@pytest.fixture
async def history(session_factory):
    return await build_history("ACC-DEMO01", get_legacy_systems(), session_factory)


def llm_says(**fields) -> FakeLLM:
    defaults = dict(is_self_service=True, category="Billing", reason="llm")
    return FakeLLM(lambda _messages: Categorization(**(defaults | fields)))


def failing_llm() -> FakeLLM:
    def boom(_messages):
        raise RuntimeError("Gemini unavailable")

    return FakeLLM(boom)


async def test_the_llm_decides_when_no_rule_applies(history):
    result = await categorize(llm_says(), MESSAGES, history, force_handoff=False)

    assert (result.is_self_service, result.category) == (True, "Billing")


async def test_a_meter_reading_is_always_a_meter_reading_review_hand_off(history):
    reading = MeterReadingMention(service=Service.ELECTRICITY, value=48213)
    llm = llm_says(is_self_service=True, category="Service", meter_reading=reading)

    result = await categorize(llm, MESSAGES, history, force_handoff=False)

    assert (result.is_self_service, result.category) == (False, "Meter reading")
    assert result.meter_reading == reading


async def test_after_a_no_the_llm_cannot_keep_it_self_service(history):
    result = await categorize(llm_says(is_self_service=True), MESSAGES, history, force_handoff=True)

    assert result.is_self_service is False
    assert result.category == "Billing"  # the LLM still picks the topic


async def test_after_a_no_the_hand_off_survives_a_gemini_outage(history):
    result = await categorize(failing_llm(), MESSAGES, history, force_handoff=True)

    assert (result.is_self_service, result.category) == (False, "Service")


async def test_without_a_rule_a_gemini_outage_is_an_error(history):
    with pytest.raises(RuntimeError, match="Gemini unavailable"):
        await categorize(failing_llm(), MESSAGES, history, force_handoff=False)


async def test_the_prompt_carries_the_history_and_the_latest_message(history):
    llm = llm_says()
    await categorize(llm, [HumanMessage("Why is my bill so high?")], history, force_handoff=False)

    [sent] = llm.calls
    assert "INV-2609-DEMO01" in sent[0].content  # the Unified Customer History
    assert sent[-1].content == "Why is my bill so high?"


def test_every_triage_queue_has_a_team_name_for_the_customer():
    from src.triage import ROUTE

    assert set(ROUTE) == set(get_args(Category))
    assert set(ROUTE.values()) <= set(TEAM)
