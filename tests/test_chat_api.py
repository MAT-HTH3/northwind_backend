import json

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.categorizer import Categorization, MeterReadingMention
from src.agent.graph import build_graph
from src.api.deps import get_graph, get_graph_context
from src.api.streaming import CUSTOMER_SAFE_ERROR, from_message
from src.main import app
from src.models import Service
from tests.fakes import FakeLLM, fake_context

ACCOUNT = "ACC-DEMO01"


@pytest.fixture
def graph():
    return build_graph(InMemorySaver())


@pytest.fixture
def use(graph):
    """Point the app at a test graph and context."""

    def install(context):
        app.dependency_overrides[get_graph] = lambda: graph
        app.dependency_overrides[get_graph_context] = lambda: context

    yield install
    app.dependency_overrides.clear()


async def post_chat(message, conversation_id="c1", account_id=ACCOUNT):
    body = {
        "conversation_id": conversation_id,
        "account_id": account_id,
        "messages": [{"role": "user", "content": message}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/chat", json=body)


def events(response):
    parsed = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


def hand_off(category="Supply", reading=None):
    return FakeLLM(
        lambda _m: Categorization(
            is_self_service=False, category=category, reason="fake", meter_reading=reading
        )
    )


async def test_bill_question_streams_tool_call_result_and_text(use, session_factory):
    use(
        fake_context(
            session_factory,
            FakeLLM(
                replies=[
                    AIMessage(
                        "", tool_calls=[{"id": "c1", "name": "show_bill_breakdown", "args": {}}]
                    ),
                    AIMessage("Your bill is **£169.60**."),
                ]
            ),
        )
    )

    response = await post_chat("Why is my bill so high?")

    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    (call, call_data), (result, result_data), (text, text_data), (done, _) = events(response)
    assert (call, call_data) == (
        "tool-call",
        {"id": "c1", "name": "show_bill_breakdown", "args": {}},
    )
    assert (result, result_data["id"], result_data["is_error"]) == ("tool-result", "c1", False)
    assert result_data["result"]["amount_due"] == 169.6
    assert (text, text_data, done) == ("text-delta", {"delta": "Your bill is **£169.60**."}, "done")


async def test_hand_off_streams_cards_with_results_then_text(use, session_factory):
    reading = MeterReadingMention(service=Service.ELECTRICITY, value=41213)
    use(fake_context(session_factory, hand_off(reading=reading)))

    response = await post_chat("My meter says 41213")

    streamed = events(response)
    assert [e for e, _ in streamed] == ["tool-call", "tool-call", "text-delta", "done"]
    receipt, case = streamed[0][1], streamed[1][1]
    assert (receipt["name"], receipt["result"]["value"]) == ("submit_meter_reading", 41213)
    assert (case["name"], case["result"]["category"]) == ("create_support_case", "Meter reading")
    assert receipt["id"] != case["id"]


async def test_an_accepted_reading_streams_its_receipt_then_text(use, session_factory):
    reading = MeterReadingMention(service=Service.ELECTRICITY, value=48213)
    use(fake_context(session_factory, hand_off(reading=reading)))

    response = await post_chat("My meter says 48213")

    (call, receipt), (text, data), (done, _) = events(response)
    assert (call, receipt["name"]) == ("tool-call", "submit_meter_reading")
    assert (receipt["result"]["status"], receipt["result"]["revised_amount_due"]) == (
        "accepted",
        132.01,
    )
    assert text == "text-delta" and "**£132.01**" in data["delta"] and done == "done"


@pytest.mark.parametrize("node", ["categorizer", "unified_desktop", "analyzer"])
def test_tokens_from_internal_llm_calls_never_reach_the_customer(node):
    assert from_message(node, AIMessageChunk("internal structured output")) == []


def test_the_widget_gets_the_tool_artifact_not_what_the_model_saw():
    message = ToolMessage("Bill shown.", tool_call_id="c1", artifact={"amount_due": 169.6})

    assert from_message("resolver_tools", message) == [
        ("tool-result", {"id": "c1", "result": {"amount_due": 169.6}, "is_error": False})
    ]


async def test_a_held_conversation_gets_the_acknowledgement(use, session_factory):
    use(fake_context(session_factory, hand_off()))
    await post_chat("My meter display is blank")

    response = await post_chat("Any update?")

    (text, data), (done, _) = events(response)
    assert text == "text-delta" and "is with our team" in data["delta"]
    assert done == "done"


async def test_a_failure_becomes_a_customer_safe_error_event(use, session_factory):
    def boom(_messages):
        raise RuntimeError("Gemini exploded: api key ABC123")

    use(fake_context(session_factory, FakeLLM(boom)))

    response = await post_chat("Why is my bill so high?")

    assert response.status_code == 200  # the stream had already started
    assert events(response) == [("error", {"message": CUSTOMER_SAFE_ERROR})]
    assert "ABC123" not in response.text


async def test_unknown_account_is_404_before_streaming(use, session_factory):
    use(fake_context(session_factory))

    response = await post_chat("Hi", account_id="ACC-000000")

    assert response.status_code == 404


async def test_a_request_without_a_user_message_is_rejected(use, session_factory):
    use(fake_context(session_factory))
    body = {
        "conversation_id": "c1",
        "account_id": ACCOUNT,
        "messages": [{"role": "assistant", "content": "Hi!"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/chat", json=body)

    assert response.status_code == 422
