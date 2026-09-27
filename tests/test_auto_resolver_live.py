"""Real Gemini through the whole graph (Analyzer, Categorizer, Auto-Resolver).

Opt-in: RUN_LIVE_LLM=1 uv run pytest -k live
"""

import os
import re

import pytest
from dotenv import dotenv_values
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.context import GraphContext
from src.agent.graph import build_graph
from src.agent.turns import thread_config, turn_input
from src.core.config import get_settings
from src.legacy import get_legacy_systems

pytestmark = pytest.mark.skipif(not os.getenv("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1")


@pytest.fixture
def context(session_factory):
    # The test conftest sets a dummy key in the environment; read the real one from .env.
    key = dotenv_values(".env")["GEMINI_API_KEY"]
    settings = get_settings()
    return GraphContext(
        session_factory=session_factory,
        legacy=get_legacy_systems(),
        categorizer_llm=ChatGoogleGenerativeAI(model=settings.gemini_model, api_key=key),
        resolver_llm=ChatGoogleGenerativeAI(model=settings.gemini_resolver_model, api_key=key),
    )


async def ask(context, message):
    graph = build_graph(InMemorySaver())
    payload = await turn_input(graph, conversation_id="c", account_id="ACC-DEMO01", message=message)
    state = await graph.ainvoke(payload, thread_config("c"), context=context)
    tools = [c["name"] for m in state["messages"] for c in getattr(m, "tool_calls", None) or []]
    return state["messages"][-1].text, tools


FIGURES = re.compile(r"£|\d")  # no amounts, dates or readings in the model's own words


async def test_live_bill_question_shows_the_card_and_quotes_no_figures(context):
    reply, tools = await ask(context, "Why is my bill so high?")

    assert tools == ["show_bill_breakdown"]
    assert not FIGURES.search(reply), reply
    assert "recalculat" not in reply.lower()


async def test_live_payment_question_shows_the_card_too(context):
    reply, tools = await ask(context, "When is my payment due?")

    assert tools == ["show_bill_breakdown"]
    assert not FIGURES.search(reply), reply


async def test_live_complaint_question_shows_no_card(context):
    reply, tools = await ask(context, "I want to complain about how long this is taking")

    assert tools == []
