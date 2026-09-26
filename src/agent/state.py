from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from src.history import UnifiedCustomerHistory


class SupportState(TypedDict, total=False):
    """One conversation's memory, checkpointed under thread_id = conversation_id."""

    messages: Annotated[list[AnyMessage], add_messages]
    account_id: str
    conversation_id: str

    # Unified Customer History, rebuilt by the Analyzer every turn. Stored as JSON, not as the
    # Pydantic model, so any checkpointer can reload it; read it with history_from(state).
    history: dict[str, Any] | None

    # Set when the customer answers "No" to "Did this solve your problem?"; forces a hand-off
    # for the next message only, then the Categorizer clears it.
    force_handoff: bool

    # The Categorizer's decision for the current message.
    is_self_service: bool
    category: str | None
    reason: str | None

    # The Support Case holding this conversation, and how the Human Agent closed it.
    case_id: str | None
    case_outcome: str | None


def history_from(state: SupportState) -> UnifiedCustomerHistory:
    return UnifiedCustomerHistory.model_validate(state["history"])


class CustomerMessage(TypedDict):
    """Resume value when the customer writes while the conversation is held."""

    kind: Literal["customer_message"]
    content: str


class CaseClosed(TypedDict):
    """Resume value when the Human Agent closes the Support Case."""

    kind: Literal["case_closed"]
    outcome: str


ResumeValue = CustomerMessage | CaseClosed
