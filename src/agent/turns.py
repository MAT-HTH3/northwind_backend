"""What to feed the graph for one chat message, and how the Human Agent resumes it."""

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from src.agent.state import CaseClosed, CustomerMessage


def thread_config(conversation_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": conversation_id}}


async def is_held(graph: CompiledStateGraph, conversation_id: str) -> bool:
    """True while the thread is paused at Wait, i.e. a Support Case holds the conversation."""
    snapshot = await graph.aget_state(thread_config(conversation_id))
    return bool(snapshot.interrupts)


async def turn_input(
    graph: CompiledStateGraph,
    *,
    conversation_id: str,
    account_id: str,
    message: str,
) -> dict | Command:
    """A held conversation gets the message as a resume; otherwise it starts a new run.

    Starting a new run on a held thread would silently discard the pause (ADR 0001).
    """
    if await is_held(graph, conversation_id):
        return Command(resume=CustomerMessage(kind="customer_message", content=message))
    return {
        "messages": [HumanMessage(message)],
        "account_id": account_id,
        "conversation_id": conversation_id,
    }


def close_input(outcome: str) -> Command:
    return Command(resume=CaseClosed(kind="case_closed", outcome=outcome))
