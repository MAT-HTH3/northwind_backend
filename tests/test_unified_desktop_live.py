"""Real Gemini writes a case summary after a conversation that used a tool.

Opt-in: RUN_LIVE_LLM=1 uv run pytest -k live
"""

import os

import pytest
from dotenv import dotenv_values
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.agent.unified_desktop import summarise
from src.core.config import get_settings
from src.history import build_history
from src.legacy import get_legacy_systems

pytestmark = pytest.mark.skipif(not os.getenv("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1")


async def test_live_summary_after_a_tool_call(session_factory):
    history = await build_history("ACC-372876", get_legacy_systems(), session_factory)
    gemini = ChatGoogleGenerativeAI(
        model=get_settings().gemini_resolver_model, api_key=dotenv_values(".env")["GEMINI_API_KEY"]
    )
    messages = [
        HumanMessage("Why is my bill so high?"),
        AIMessage("", tool_calls=[{"id": "c1", "name": "show_bill_breakdown", "args": {}}]),
        ToolMessage('{"amount_due": 169.6}', tool_call_id="c1"),
        AIMessage("It's based on an estimated reading."),
        HumanMessage("My meter actually says 48213"),
    ]

    summary = await summarise(gemini, "Meter reading review", messages, history)

    assert not summary.startswith("Sarah Whitfield (Dunmoor) was handed off")  # not the fallback
    assert "48213" in summary.replace(",", "")
