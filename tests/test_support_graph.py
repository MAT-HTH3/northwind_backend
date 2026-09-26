import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.agent.context import GraphContext
from src.agent.graph import build_graph
from src.agent.nodes import acknowledgement
from src.agent.turns import close_input, is_held, thread_config, turn_input
from src.legacy import get_legacy_systems
from src.models import CaseStatus
from src.repositories import SupportCaseRepository

ACCOUNT = "ACC-372876"


@pytest.fixture
def context(session_factory) -> GraphContext:
    return GraphContext(session_factory=session_factory, legacy=get_legacy_systems())


@pytest.fixture
def graph():
    return build_graph(InMemorySaver())


async def send(graph, context, conversation_id, message, *, force_handoff=False):
    payload = await turn_input(
        graph, conversation_id=conversation_id, account_id=ACCOUNT, message=message
    )
    if force_handoff:
        payload["force_handoff"] = True
    return await graph.ainvoke(payload, thread_config(conversation_id), context=context)


async def hand_off(graph, context, conversation_id="conv-1"):
    return await send(graph, context, conversation_id, "I want a person", force_handoff=True)


async def cases(session_factory):
    async with session_factory() as session:
        return await SupportCaseRepository(session).list_all()


async def test_self_service_goes_to_the_auto_resolver_and_ends(graph, context):
    state = await send(graph, context, "conv-1", "Why is my bill so high?")

    assert state["is_self_service"] is True
    assert "Auto-Resolver" in state["messages"][-1].content
    assert not await is_held(graph, "conv-1")


async def test_hand_off_opens_a_case_and_holds_the_conversation(graph, context, session_factory):
    state = await hand_off(graph, context)

    [case] = await cases(session_factory)
    assert state["case_id"] == case.id
    assert [link.conversation_id for link in case.conversations] == ["conv-1"]
    assert await is_held(graph, "conv-1")
    assert state["force_handoff"] is False  # the "No" override applies once


async def test_message_while_held_is_acknowledged_and_the_pause_survives(
    graph, context, session_factory
):
    await hand_off(graph, context)

    state = await send(graph, context, "conv-1", "Any update?")

    [case] = await cases(session_factory)  # no second case
    assert [m.content for m in case.held_messages] == ["Any update?"]
    assert [m.content for m in state["messages"][-2:]] == ["Any update?", acknowledgement(case.id)]
    assert await is_held(graph, "conv-1")


async def test_closing_resumes_to_the_end_and_the_conversation_is_live_again(
    graph, context, session_factory
):
    await hand_off(graph, context)
    await send(graph, context, "conv-1", "Any update?")

    state = await graph.ainvoke(
        close_input("Reading verified, corrected bill sent."),
        thread_config("conv-1"),
        context=context,
    )

    assert state["case_outcome"] == "Reading verified, corrected bill sent."
    assert state["case_id"] is None
    assert not await is_held(graph, "conv-1")

    state = await send(graph, context, "conv-1", "Thanks, when is my payment due?")
    assert "Auto-Resolver" in state["messages"][-1].content
    assert state["case_outcome"] == "Reading verified, corrected bill sent."


async def test_a_paused_thread_survives_a_restart(context, session_factory, tmp_path):
    path = str(tmp_path / "checkpoints.db")
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        await hand_off(build_graph(saver), context)

    async with AsyncSqliteSaver.from_conn_string(path) as saver:  # a fresh process, in effect
        graph = build_graph(saver)
        assert await is_held(graph, "conv-1")
        state = await graph.ainvoke(close_input("Done."), thread_config("conv-1"), context=context)

    assert state["case_outcome"] == "Done."
    assert [m.type for m in state["messages"]] == ["human", "ai"]
    assert (await cases(session_factory))[
        0
    ].status == CaseStatus.OPEN  # closing the case is the API's job
