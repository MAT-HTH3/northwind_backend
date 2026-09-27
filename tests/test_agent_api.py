import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.agent.categorizer import Categorization
from src.agent.graph import build_graph
from src.agent.turns import is_held
from src.api.deps import get_graph, get_graph_context
from src.main import app
from tests.fakes import FakeLLM, fake_context

ACCOUNT = "ACC-DEMO01"
AGENT = "Priya Anand"


def says(**fields):
    defaults = dict(is_self_service=True, category="Billing", reason="fake")
    return lambda _messages: Categorization(**(defaults | fields))


HAND_OFF = says(is_self_service=False, category="Supply", subject="Power cut with no updates")


@pytest.fixture
def desk(session_factory):
    graph = build_graph(InMemorySaver())

    def install(llm=None):
        app.dependency_overrides[get_graph] = lambda: graph
        app.dependency_overrides[get_graph_context] = lambda: fake_context(
            session_factory, llm or FakeLLM(HAND_OFF)
        )
        return graph

    yield install
    app.dependency_overrides.clear()


async def call(method, path, json=None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        return await http.request(method, path, json=json)


async def chat(message, conversation_id="c1"):
    body = {
        "conversation_id": conversation_id,
        "account_id": ACCOUNT,
        "messages": [{"role": "user", "content": message}],
    }
    return await call("POST", "/api/chat", body)


async def open_case(conversation_id="c1", message="We have no power since this morning"):
    await chat(message, conversation_id)
    [case] = [c for c in (await call("GET", "/api/agent/queue")).json()["cases"]]
    return case


async def test_the_queue_shows_chat_cases_and_resolved_chats(desk):
    desk(FakeLLM(says()))
    await chat("When is my payment due?", "c0")
    await call(
        "POST", "/api/conversations/c0/resolution", {"account_id": ACCOUNT, "resolved": True}
    )
    desk()

    case = await open_case()

    snapshot = (await call("GET", "/api/agent/queue")).json()
    assert {k: case[k] for k in ("account_id", "customer_name", "region", "channel", "source")} == {
        "account_id": ACCOUNT,
        "customer_name": "Sarah Whitfield",
        "region": "North",
        "channel": "chat",
        "source": "assistant",
    }
    assert (case["category"], case["subject"], case["status"]) == (
        "Supply",
        "Power cut with no updates",
        "new",
    )
    assert case["description"] == "We have no power since this morning"  # the customer's words
    by_id = {c["conversation_id"]: c for c in snapshot["conversations"]}
    assert (by_id["c0"]["resolved"], by_id["c0"]["case_id"]) == (True, None)
    assert (by_id["c1"]["resolved"], by_id["c1"]["case_id"]) == (False, case["case_id"])
    assert snapshot["generated_at"]


async def test_case_detail_is_one_screen_instead_of_four(desk):
    desk()
    case = await open_case()

    detail = (await call("GET", f"/api/agent/cases/{case['case_id']}")).json()

    lines = [(e["role"], e["text"]) for e in detail["transcript"]]
    assert lines[0] == ("customer", "We have no power since this morning")
    assert lines[1] == ("system", f"Case {case['case_id']} opened")  # the card, written by code
    assert lines[2][0] == "assistant" and case["case_id"] in lines[2][1]
    account = detail["account"]
    assert account["customer"]["vulnerable"] is False
    assert account["bill"]["amount_due"] == 169.6
    assert {r["type"] for r in account["meter_reads"]} == {"actual", "customer", "estimated"}
    assert detail["timeline"][0]["label"] == "Opened (chat)"


async def test_assign_and_override_urgency(desk):
    desk()
    case_id = (await open_case())["case_id"]

    assigned = (await call("PATCH", f"/api/agent/cases/{case_id}", {"assignee": AGENT})).json()
    overridden = (
        await call("PATCH", f"/api/agent/cases/{case_id}", {"priority_override": "P1"})
    ).json()
    cleared = (
        await call("PATCH", f"/api/agent/cases/{case_id}", {"priority_override": None})
    ).json()

    assert assigned["assignee"] == AGENT
    assert (overridden["priority_override"], cleared["priority_override"]) == ("P1", None)
    assert cleared["assignee"] == AGENT  # untouched by the other changes
    labels = [
        e["label"] for e in (await call("GET", f"/api/agent/cases/{case_id}")).json()["timeline"]
    ]
    assert labels[1:] == [
        f"Assigned to {AGENT}",
        "Urgency set to P1",
        "Urgency back to the Triage Rules",
    ]


async def test_feedback_is_stored_verbatim_and_shown_on_the_desk(desk):
    desk()
    case_id = (await open_case())["case_id"]
    note = "Customer is on a home dialysis machine — check the PSR flag!"

    saved = (
        await call(
            "POST",
            f"/api/agent/cases/{case_id}/feedback",
            {"tags": ["Vulnerable customer"], "note": note, "author": AGENT},
        )
    ).json()

    assert (saved["note"], saved["tags"], saved["author"]) == (note, ["Vulnerable customer"], AGENT)
    snapshot = (await call("GET", "/api/agent/queue")).json()
    shown = snapshot["feedback"][0]
    assert (shown["case_id"], shown["note"], shown["author"]) == (case_id, note, AGENT)


async def test_resolving_releases_every_held_conversation(desk):
    graph = desk()
    case_id = (await open_case("c1"))["case_id"]
    await chat("The power is still off, any news?", "c2")  # same topic: joins the open case
    assert await is_held(graph, "c1") and await is_held(graph, "c2")

    resolved = (
        await call(
            "PATCH",
            f"/api/agent/cases/{case_id}",
            {"status": "resolved", "resolution": "field_visit"},
        )
    ).json()

    assert (resolved["status"], resolved["resolution"]) == ("resolved", "field_visit")
    assert resolved["closed_at"] is not None
    assert not await is_held(graph, "c1") and not await is_held(graph, "c2")

    desk(FakeLLM(says(case_status_request=True)))
    reply = await chat("What happened with my case?", "c1")
    assert "was resolved" in reply.text and "one of our engineers visited" in reply.text


async def test_reopening_does_not_hold_the_conversations_again(desk):
    graph = desk()
    case_id = (await open_case())["case_id"]
    await call(
        "PATCH", f"/api/agent/cases/{case_id}", {"status": "resolved", "resolution": "other"}
    )

    reopened = (
        await call("PATCH", f"/api/agent/cases/{case_id}", {"status": "in_progress"})
    ).json()

    assert (reopened["status"], reopened["reopened"], reopened["closed_at"]) == (
        "in_progress",
        True,
        None,
    )
    assert not await is_held(graph, "c1")


async def test_conversation_detail_has_the_transcript(desk):
    desk(
        FakeLLM(
            says(),
            replies=[
                AIMessage("", tool_calls=[{"id": "t1", "name": "show_bill_breakdown", "args": {}}]),
                AIMessage("Here's your latest bill."),
            ],
        )
    )
    await chat("Why is my bill so high?")

    detail = (await call("GET", "/api/agent/conversations/c1")).json()

    assert detail["conversation"]["topic"] == "Bill explained"
    assert [(e["role"], e["text"]) for e in detail["transcript"]] == [
        ("customer", "Why is my bill so high?"),
        ("system", "Bill breakdown shown"),
        ("assistant", "Here's your latest bill."),
    ]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/agent/cases/NW-000000", None),
        ("PATCH", "/api/agent/cases/NW-000000", {"status": "resolved"}),
        ("POST", "/api/agent/cases/NW-000000/feedback", {"note": "x", "author": AGENT}),
        ("GET", "/api/agent/conversations/nope", None),
    ],
)
async def test_unknown_records_are_404(desk, method, path, body):
    desk()

    assert (await call(method, path, body)).status_code == 404
