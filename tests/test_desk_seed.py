from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select

from src.agent.categorizer import Categorization
from src.agent.graph import build_graph
from src.agent.turns import thread_config
from src.api.deps import get_graph, get_graph_context
from src.desk.seed import read_seed, seed_if_empty
from src.main import app
from src.models import Conversation, SupportCase
from src.models.types import utcnow
from tests.fakes import FakeLLM, fake_context

SEED = read_seed()
HAND_OFF = FakeLLM(
    lambda _m: Categorization(is_self_service=False, category="Supply", reason="fake")
)


@pytest.fixture
async def seeded(session_factory):
    assert await seed_if_empty(session_factory)
    return session_factory


@pytest.fixture
def desk(seeded):
    graph = build_graph(InMemorySaver())
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_graph_context] = lambda: fake_context(seeded, HAND_OFF)
    yield graph
    app.dependency_overrides.clear()


async def call(method, path, json=None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        return await http.request(method, path, json=json)


async def count(session_factory, model, *where):
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model).where(*where))


async def test_the_seed_loads_once_with_times_moved_to_now(seeded):
    assert await count(seeded, SupportCase) == len(SEED["cases"])
    assert await count(seeded, Conversation) == len(SEED["conversations"])
    assert not await seed_if_empty(seeded)  # already there

    async with seeded() as session:
        newest = await session.scalar(select(func.max(SupportCase.created_at)))
        case = await session.get(SupportCase, SEED["cases"][0]["case"]["case_id"])
    assert utcnow() - newest < timedelta(days=1)  # generated "now", loaded now
    assert case.priority is not None and case.queue and case.sla_days in (2, 10, 20)


async def test_the_queue_serves_the_seed(desk):
    snapshot = (await call("GET", "/api/agent/queue")).json()

    open_cases = [c for c in snapshot["cases"] if c["status"] != "resolved"]
    assert len(open_cases) == sum(1 for c in SEED["cases"] if c["case"]["status"] != "resolved")
    assert {c["source"] for c in snapshot["cases"]} == {"direct", "assistant"}
    assert any(c["resolved"] for c in snapshot["conversations"])  # "Resolved by AI"
    assert snapshot["feedback"]


async def test_seeded_cases_show_their_transcript_and_account(desk):
    chat_case = next(c["case"] for c in SEED["cases"] if c["case"]["channel"] == "chat")
    phone_case = next(c["case"] for c in SEED["cases"] if c["case"]["channel"] == "phone")

    chat = (await call("GET", f"/api/agent/cases/{chat_case['case_id']}")).json()
    phone = (await call("GET", f"/api/agent/cases/{phone_case['case_id']}")).json()

    assert chat["transcript"][0] == chat["transcript"][0] | {
        "role": "customer",
        "text": chat_case["description"],
    }
    assert phone["transcript"] is None
    assert phone["account"]["customer"]["account_id"] == phone_case["account_id"]
    assert phone["account"]["bill"]["amount_due"] > 0
    assert phone["timeline"][0]["label"].startswith("Opened via")


async def test_seeded_conversations_show_their_transcript(desk):
    resolved = next(
        c["conversation"] for c in SEED["conversations"] if c["conversation"]["resolved"]
    )

    detail = (await call("GET", f"/api/agent/conversations/{resolved['conversation_id']}")).json()

    assert detail["conversation"]["resolved"] is True
    assert detail["transcript"][0]["role"] == "customer"


async def test_reset_clears_live_cases_and_chat_memory_then_restores_the_seed(desk, seeded):
    body = {
        "conversation_id": "live-1",
        "account_id": "ACC-DEMO01",
        "messages": [{"role": "user", "content": "The power is off"}],
    }
    await call("POST", "/api/chat", body)
    assert await count(seeded, SupportCase) == len(SEED["cases"]) + 1

    response = await call("POST", "/api/agent/demo/reset")

    assert response.json() == {"ok": True}
    assert await count(seeded, SupportCase) == len(SEED["cases"])
    assert await count(seeded, Conversation, Conversation.id == "live-1") == 0
    assert (await desk.aget_state(thread_config("live-1"))).values == {}  # chat memory gone


async def test_reset_works_on_a_fresh_checkpoint_file(seeded, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from src.agent import checkpointer as module
    from src.desk.seed import reset_demo

    path = str(tmp_path / "fresh-checkpoints.db")
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(checkpoint_db_path=path))

    async with module.open_checkpointer() as saver:  # nobody has chatted: no tables yet
        await reset_demo(seeded, saver)

    assert await count(seeded, SupportCase) == len(SEED["cases"])


async def test_a_failed_reset_leaves_the_desk_as_it_was(seeded):
    from src.desk.seed import reset_demo

    class BrokenCheckpointer:
        async def adelete_thread(self, thread_id):
            raise RuntimeError("checkpoint store unavailable")

    with pytest.raises(RuntimeError):
        await reset_demo(seeded, BrokenCheckpointer())

    assert await count(seeded, SupportCase) == len(SEED["cases"])
