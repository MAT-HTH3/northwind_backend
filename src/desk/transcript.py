"""A chat conversation as the Human Agent reads it, rebuilt from the checkpointer.

Messages carry no timestamps, so each one takes the time of the first checkpoint it appears in.
Cards shown to the customer become "system" lines written by code.
"""

from datetime import datetime

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from src.agent.cards import UI_CARDS
from src.agent.turns import thread_config
from src.schemas.agent import TranscriptEntry

CARD_LINES = {
    "show_bill_breakdown": lambda result: "Bill breakdown shown",
    "submit_meter_reading": lambda result: (
        f"Meter reading {result['value']:,} {result['unit']} "
        + ("accepted" if result["status"] == "accepted" else "sent for review")
    ),
    "create_support_case": lambda result: f"Case {result['case_id']} opened",
}


async def transcript(graph: CompiledStateGraph, conversation_id: str) -> list[TranscriptEntry]:
    first_seen: dict[str, datetime] = {}
    messages: list[AnyMessage] = []
    async for snapshot in graph.aget_state_history(thread_config(conversation_id)):  # newest first
        at = datetime.fromisoformat(snapshot.created_at)
        state_messages = snapshot.values.get("messages", [])
        if not messages:
            messages = state_messages
        for message in state_messages:
            first_seen[message.id] = at  # overwritten by older checkpoints
    return [entry for m in messages for entry in _entries(m, first_seen.get(m.id))]


def _entries(message: AnyMessage, at: datetime | None) -> list[TranscriptEntry]:
    if at is None:
        return []
    if isinstance(message, HumanMessage):
        return [TranscriptEntry(role="customer", text=message.text, at=at)]
    if isinstance(message, ToolMessage):
        if message.artifact is None:
            return []
        line = CARD_LINES.get(message.name or "")
        return [TranscriptEntry(role="system", text=line(message.artifact), at=at)] if line else []
    if isinstance(message, AIMessage):
        entries = [
            TranscriptEntry(role="system", text=CARD_LINES[card["name"]](card["result"]), at=at)
            for card in message.additional_kwargs.get(UI_CARDS, [])
            if card["name"] in CARD_LINES
        ]
        if message.text:
            entries.append(TranscriptEntry(role="assistant", text=message.text, at=at))
        return entries
    return []
