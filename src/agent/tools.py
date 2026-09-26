"""Tools the AI Assistant can call. Tools named in the widget contract render as cards."""

from typing import Annotated, Any

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from src.agent.bill_breakdown import build_bill_breakdown
from src.agent.state import history_from


@tool
def show_bill_breakdown(
    state: Annotated[dict[str, Any], InjectedState],
    bill_id: str | None = None,
) -> dict[str, Any]:
    """Show the customer a card breaking down one bill: charges line by line, rates, six months
    of usage, and why it changed. Use it only when the customer asks about a bill's charges or
    why a bill went up or down. Do not use it for payment dates, complaints, cases or contact
    history. Leave bill_id empty for the latest bill."""
    return build_bill_breakdown(history_from(state), bill_id).model_dump(mode="json")


AUTO_RESOLVER_TOOLS = [show_bill_breakdown]
