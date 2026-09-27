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
from src.history import build_history
from src.legacy import get_legacy_systems

pytestmark = pytest.mark.skipif(not os.getenv("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1")

CASES = [
    # message, is_self_service, category (None = any), meter reading (None = must be absent)
    ("Why is my bill so high?", True, None, None),
    ("When will my next payment be taken?", True, None, None),
    ("My bill says I used 486 kWh, is that right?", True, None, None),
    ("My electricity meter says 48213", False, "Meter reading", 48213),
    ("it reads 48,213 now", False, "Meter reading", 48213),
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


@pytest.fixture
async def history(session_factory):
    return await build_history("ACC-DEMO01", get_legacy_systems(), session_factory)


@pytest.fixture
def gemini():
    # The test conftest sets a dummy key in the environment; read the real one from .env.
    return ChatGoogleGenerativeAI(
        model=get_settings().gemini_model, api_key=dotenv_values(".env")["GEMINI_API_KEY"]
    )


@pytest.mark.parametrize(("message", "self_service", "category", "reading"), CASES)
async def test_live_categorization(gemini, history, message, self_service, category, reading):
    result = await categorize(gemini, [HumanMessage(message)], history, force_handoff=False)

    assert result.is_self_service is self_service, result.reason
    if category:
        assert result.category == category, result.reason
    assert (result.meter_reading.value if result.meter_reading else None) == reading
