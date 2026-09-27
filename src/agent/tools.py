"""Tools the AI Assistant can call. Tools named in the widget contract render as cards.

Each returns (status for the model, record for the widget): the model sees only the short
status, never the record (ADR 0003). The record rides on the ToolMessage as `artifact`, and the
chat stream sends it to the widget as the tool-result.
"""

from typing import Annotated, Any

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from src.agent.bill_breakdown import build_bill_breakdown
from src.agent.state import history_from

BILL_SHOWN = "The bill is now shown to the customer on a card."


@tool(response_format="content_and_artifact")
def show_bill_breakdown(
    state: Annotated[dict[str, Any], InjectedState],
    month: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Show the customer a card with one bill: charges line by line, rates, the due date, the
    balance, six months of usage, and why it changed. Use it when the customer asks about a
    bill, its charges, its due date or why it went up or down. Do not use it for complaints,
    cases or contact history. Leave month empty for the latest bill; otherwise the month the
    bill period ended, as YYYY-MM."""
    breakdown = build_bill_breakdown(history_from(state), month)
    return BILL_SHOWN, breakdown.model_dump(mode="json")


AUTO_RESOLVER_TOOLS = [show_bill_breakdown]
