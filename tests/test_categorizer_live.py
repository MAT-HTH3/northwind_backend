"""Real Gemini calls that check the prompt, not the code.

Opt-in: RUN_LIVE_LLM=1 uv run pytest -k live
"""

import os

import pytest
from dotenv import dotenv_values
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.agent.categorizer import categorize
from src.core.config import get_settings

pytestmark = pytest.mark.skipif(not os.getenv("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1")

CASES = [
    # message, is_self_service (None = any), category (None = any), reading (None = absent)
    ("Why is my bill so high?", True, None, None),
    ("When will my next payment be taken?", True, None, None),
    ("My bill says I used 486 kWh, is that right?", True, None, None),
    ("My electricity meter says 48213", None, "Meter reading", 48213),  # code decides (ADR 0004)
    ("it reads 48,213 now", None, "Meter reading", 48213),
    (
        "Water is leaking from the pipe next to my meter",
        False,
        "Supply",
        None,
    ),
    ("I want a refund, that estimate was way too high", False, "Billing", None),
    ("Can I pay this off in instalments?", False, "Payments", None),
    ("Can I speak to a real person please?", False, None, None),
]


async def test_live_subject_disputed_amount_and_case_status(gemini):
    refund = await categorize(
        gemini, [HumanMessage("You overcharged me £180, I want it refunded")], force_handoff=False
    )
    chasing = await categorize(
        gemini, [HumanMessage("Any update on the complaint I made last week?")], force_handoff=False
    )

    assert (refund.is_self_service, refund.disputed_amount) == (False, 180)
    assert refund.category in {"Billing", "Payments"}
    assert chasing.case_status_request is True


@pytest.fixture
def gemini():
    # The test conftest sets a dummy key in the environment; read the real one from .env.
    return ChatGoogleGenerativeAI(
        model=get_settings().gemini_model, api_key=dotenv_values(".env")["GEMINI_API_KEY"]
    )


@pytest.mark.parametrize(("message", "self_service", "category", "reading"), CASES)
async def test_live_categorization(gemini, message, self_service, category, reading):
    result = await categorize(gemini, [HumanMessage(message)], force_handoff=False)

    if self_service is not None:
        assert result.is_self_service is self_service, result.reason
    if category:
        assert result.category == category, result.reason
    assert (result.meter_reading.value if result.meter_reading else None) == reading
