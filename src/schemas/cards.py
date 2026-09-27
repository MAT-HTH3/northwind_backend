"""Results of the card tools the widget draws. Shapes defined in the frontend's
docs/api-contract.md (as updated for ADR 0002)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class MeterReadingReceipt(BaseModel):
    """submit_meter_reading. Every reading is reviewed by a Human Agent, so there is no
    revised amount."""

    reading_id: str
    service: Literal["electricity", "water"]
    value: int
    unit: str
    read_date: date
    status: Literal["awaiting_review"]


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
