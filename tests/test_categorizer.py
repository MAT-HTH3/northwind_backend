from typing import get_args

import pytest
from langchain_core.messages import HumanMessage

from src.agent.categories import TEAM, Category
from src.agent.categorizer import Categorization, MeterReadingMention, categorize
from src.models import Service
from tests.fakes import FakeLLM

MESSAGES = [HumanMessage("hello")]


def llm_says(**fields) -> FakeLLM:
    defaults = dict(is_self_service=True, category="Billing", reason="llm")
    return FakeLLM(lambda _messages: Categorization(**(defaults | fields)))


def failing_llm() -> FakeLLM:
    def boom(_messages):
        raise RuntimeError("Gemini unavailable")

    return FakeLLM(boom)


async def test_the_llm_decides_when_no_rule_applies():
    result = await categorize(llm_says(), MESSAGES, force_handoff=False)

    assert (result.is_self_service, result.category) == (True, "Billing")


async def test_a_meter_reading_is_always_a_meter_reading_review_hand_off():
    reading = MeterReadingMention(service=Service.ELECTRICITY, value=48213)
    llm = llm_says(is_self_service=True, category="Service", meter_reading=reading)

    result = await categorize(llm, MESSAGES, force_handoff=False)

    assert (result.is_self_service, result.category) == (False, "Meter reading")
    assert result.meter_reading == reading


async def test_after_a_no_the_llm_cannot_keep_it_self_service():
    result = await categorize(llm_says(is_self_service=True), MESSAGES, force_handoff=True)

    assert result.is_self_service is False
    assert result.category == "Billing"  # the LLM still picks the topic


async def test_after_a_no_the_hand_off_survives_a_gemini_outage():
    result = await categorize(failing_llm(), MESSAGES, force_handoff=True)

    assert (result.is_self_service, result.category) == (False, "Service")


async def test_without_a_rule_a_gemini_outage_is_an_error():
    with pytest.raises(RuntimeError, match="Gemini unavailable"):
        await categorize(failing_llm(), MESSAGES, force_handoff=False)


async def test_the_prompt_has_the_conversation_and_no_account_data():
    llm = llm_says()
    await categorize(llm, [HumanMessage("Why is my bill so high?")], force_handoff=False)

    [sent] = llm.calls
    assert "INV-" not in sent[0].content and "ACC-" not in sent[0].content  # ADR 0003
    assert sent[-1].content == "Why is my bill so high?"


async def test_a_subject_from_another_category_falls_back_to_the_catch_all():
    llm = llm_says(category="Payments", subject="Discoloured water")

    result = await categorize(llm, MESSAGES, force_handoff=False)

    assert result.subject == "Other payments query"


async def test_a_reading_is_titled_reading_needs_checking():
    reading = MeterReadingMention(service=Service.ELECTRICITY, value=48213)

    result = await categorize(llm_says(meter_reading=reading), MESSAGES, force_handoff=False)

    assert result.subject == "Reading needs checking"


def test_every_triage_queue_has_a_team_name_for_the_customer():
    from src.triage import ROUTE

    assert set(ROUTE) == set(get_args(Category))
    assert set(ROUTE.values()) <= set(TEAM)
