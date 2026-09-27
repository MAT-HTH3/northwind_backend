"""Turns one graph run into the widget's Server-Sent Events (docs/api-contract.md).

    text-delta   Auto-Resolver tokens, and the fixed text from the Unified Desktop and Acknowledge
    tool-call    Auto-Resolver tool calls; hand-off cards carry their result directly
    tool-result  results of the Auto-Resolver's tools: the ToolMessage's artifact (ADR 0003)
    done / error end of the reply

Only the nodes listed here reach the customer. Other LLM calls (the Categorizer's structured
output, the case summary) also stream tokens through LangGraph, and must stay internal.
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from src.agent.context import GraphContext
from src.agent.turns import thread_config, turn_input
from src.agent.unified_desktop import UI_CARDS
from src.repositories import ConversationRepository

logger = logging.getLogger(__name__)

STREAMED_LLM_NODE = "auto_resolver"
FIXED_TEXT_NODES = {"unified_desktop", "acknowledge", "accept_reading", "case_status"}
TOOL_NODE = "resolver_tools"

CUSTOMER_SAFE_ERROR = (
    "Sorry, something went wrong on our side. Please try again in a moment, "
    "or ask to speak to a person."
)

Event = tuple[str, dict[str, Any]]


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def from_message(node: str, message: Any) -> list[Event]:
    """Events for one item of LangGraph's "messages" stream."""
    if node == STREAMED_LLM_NODE and isinstance(message, AIMessage):
        # Tokens (AIMessageChunk), or the whole reply if the model didn't stream.
        return [("text-delta", {"delta": message.text})] if message.text else []

    if node in FIXED_TEXT_NODES and type(message) is AIMessage:  # not a summary token chunk
        events: list[Event] = [
            ("tool-call", {"id": f"card_{uuid.uuid4().hex[:12]}", **card})
            for card in message.additional_kwargs.get(UI_CARDS, [])
        ]
        if message.text:
            events.append(("text-delta", {"delta": message.text}))
        return events

    if node == TOOL_NODE and isinstance(message, ToolMessage):
        # The widget gets the full record (the artifact); the model only saw a short status.
        is_error = message.status == "error" or message.artifact is None
        result = {"error": message.text} if is_error else message.artifact
        return [
            ("tool-result", {"id": message.tool_call_id, "result": result, "is_error": is_error})
        ]

    return []


def from_update(update: dict[str, Any]) -> list[Event]:
    """Events for one item of LangGraph's "updates" stream: complete Auto-Resolver tool calls."""
    node_update = update.get(STREAMED_LLM_NODE) or {}
    events: list[Event] = []
    for message in node_update.get("messages", []):
        for call in getattr(message, "tool_calls", None) or []:
            events.append(
                ("tool-call", {"id": call["id"], "name": call["name"], "args": call["args"]})
            )
    return events


async def stream_turn(
    graph: CompiledStateGraph,
    context: GraphContext,
    *,
    conversation_id: str,
    account_id: str,
    message: str,
) -> AsyncIterator[str]:
    try:
        force_handoff = await _start_turn(context, conversation_id, account_id)
        payload = await turn_input(
            graph,
            conversation_id=conversation_id,
            account_id=account_id,
            message=message,
            force_handoff=force_handoff,
        )
        async for mode, data in graph.astream(
            payload,
            thread_config(conversation_id),
            context=context,
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                chunk, metadata = data
                events = from_message(metadata.get("langgraph_node", ""), chunk)
            else:
                events = from_update(data)
            for event, event_data in events:
                yield sse(event, event_data)
        await _finish_turn(graph, context, conversation_id)
        yield sse("done", {})
    except Exception:
        logger.exception("Chat turn failed for conversation %s", conversation_id)
        yield sse("error", {"message": CUSTOMER_SAFE_ERROR})


async def _start_turn(context: GraphContext, conversation_id: str, account_id: str) -> bool:
    """Records the conversation; returns whether this message must go to a Human Agent because
    the customer just answered "No" (applies once)."""
    customer = await context.legacy.crm.get_customer(account_id)
    name = f"{customer.name.given} {customer.name.family}" if customer else account_id
    async with context.session_factory() as session:
        conversations = ConversationRepository(session)
        conversation = await conversations.start(conversation_id, account_id, name)
        force_handoff = await conversations.take_pending_handoff(conversation)
        await session.commit()
    return force_handoff


async def _finish_turn(
    graph: CompiledStateGraph, context: GraphContext, conversation_id: str
) -> None:
    """Records what answered the message and any Support Case, for the agent desk."""
    state = (await graph.aget_state(thread_config(conversation_id))).values
    async with context.session_factory() as session:
        conversations = ConversationRepository(session)
        conversation = await conversations.get(conversation_id)
        await conversations.record_turn(
            conversation, topic=state.get("topic"), case_id=state.get("case_id")
        )
        await session.commit()
