import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.categorizer import Categorization, MeterReadingMention
from src.agent.graph import build_graph
from src.api.deps import get_graph, get_graph_context
from src.main import app
from src.models import Service
from src.repositories import ConversationOutcome, ConversationRepository
from tests.fakes import FakeLLM, fake_context

ACCOUNT = "ACC-DEMO01"


def says(**fields):
    defaults = dict(is_self_service=True, category="Billing", reason="fake")
    return lambda _messages: Categorization(**(defaults | fields))


@pytest.fixture
def client(session_factory):
    graph = build_graph(InMemorySaver())

    def install(llm):
        app.dependency_overrides[get_graph] = lambda: graph
        app.dependency_overrides[get_graph_context] = lambda: fake_context(session_factory, llm)

    yield install
    app.dependency_overrides.clear()


async def chat(message, conversation_id="c1"):
    body = {
        "conversation_id": conversation_id,
        "account_id": ACCOUNT,
        "messages": [{"role": "user", "content": message}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        return await http.post("/api/chat", json=body)


async def answer(resolved, conversation_id="c1", account_id=ACCOUNT):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        return await http.post(
            f"/api/conversations/{conversation_id}/resolution",
            json={"account_id": account_id, "resolved": resolved},
        )


async def conversation(session_factory, conversation_id="c1"):
    async with session_factory() as session:
        repo = ConversationRepository(session)
        return await repo.get(conversation_id), await repo.outcome(conversation_id)


async def test_the_first_message_records_the_conversation_and_its_topic(client, session_factory):
    client(
        FakeLLM(
            says(),
            replies=[
                AIMessage("", tool_calls=[{"id": "c1", "name": "show_bill_breakdown", "args": {}}]),
                AIMessage("Here's your latest bill."),
            ],
        )
    )

    await chat("Why is my bill so high?")

    record, outcome = await conversation(session_factory)
    assert (record.account_id, record.customer_name, record.topic) == (
        ACCOUNT,
        "Sarah Whitfield",
        "Bill explained",
    )
    assert (record.case_id, outcome) == (None, ConversationOutcome.UNCONFIRMED)


@pytest.mark.parametrize(
    ("decision", "topic"),
    [
        (says(), "Question answered"),
        (says(case_status_request=True), "Case status checked"),
        (
            says(meter_reading=MeterReadingMention(service=Service.ELECTRICITY, value=48213)),
            "Reading accepted",
        ),
        (says(is_self_service=False, category="Supply"), "Handed to a person"),
    ],
)
async def test_the_topic_comes_from_what_answered(client, session_factory, decision, topic):
    client(FakeLLM(decision))

    await chat("Hello")

    record, _ = await conversation(session_factory)
    assert record.topic == topic


async def test_yes_is_auto_resolved(client, session_factory):
    client(FakeLLM(says()))
    await chat("When is my payment due?")

    response = await answer(True)

    assert response.json() == {"ok": True}
    _, outcome = await conversation(session_factory)
    assert outcome == ConversationOutcome.AUTO_RESOLVED


async def test_no_sends_the_next_message_to_a_person_once(client, session_factory):
    client(FakeLLM(says()))  # the model would keep everything self-service
    await chat("When is my payment due?")

    await answer(False)
    record, _ = await conversation(session_factory)
    assert record.pending_handoff is True
    await chat("I'd like to speak to a person")  # what the widget sends after a "No"

    record, outcome = await conversation(session_factory)
    assert record.case_id is not None and record.pending_handoff is False
    assert (record.topic, outcome) == ("Handed to a person", ConversationOutcome.HANDED_OFF)


async def test_yes_then_a_case_counts_as_handed_off(client, session_factory):
    client(FakeLLM(says()))
    await chat("When is my payment due?")
    await answer(True)

    client(FakeLLM(says(is_self_service=False, category="Supply")))
    await chat("Actually, the power is off")

    _, outcome = await conversation(session_factory)
    assert outcome == ConversationOutcome.HANDED_OFF


async def test_no_while_held_just_adds_the_message_to_the_case(client, session_factory):
    client(FakeLLM(says(is_self_service=False, category="Supply")))
    await chat("The power is off")
    record, _ = await conversation(session_factory)
    first_case = record.case_id

    await answer(False)
    response = await chat("I'd like to speak to a person")

    assert "is with our team" in response.text  # the acknowledgement, not a second case
    record, _ = await conversation(session_factory)
    assert record.case_id == first_case and record.pending_handoff is False


async def test_an_unknown_account_is_404(client):
    client(FakeLLM(says()))

    response = await answer(True, account_id="ACC-000000")

    assert response.status_code == 404
