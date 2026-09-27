"""Results of the card tools the widget draws. Shapes defined in the frontend's
docs/api-contract.md (as updated for ADR 0002)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class MeterReadingReceipt(BaseModel):
    """submit_meter_reading. A plausible reading is accepted and re-prices the bill; an
    implausible one needs review and has no revised amount (ADR 0004)."""

    reading_id: str
    service: Literal["electricity", "water"]
    value: int
    unit: str
    read_date: date
    status: Literal["accepted", "needs_review"]
    revised_amount_due: float | None = None


class SupportCaseCard(BaseModel):
    """create_support_case."""

    case_id: str
    category: str
    priority: Literal["P1", "P2", "P3"]  # Urgency: High, Medium, Low
    sla_days: int
    queue: str
    expected_response_by: date
    summary: str
    history_attached: bool = True
