"""Result of the show_bill_breakdown tool. Shape defined in the frontend's docs/api-contract.md."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class BillLine(BaseModel):
    service: Literal["electricity", "water", "other"]
    label: str
    amount: float
    quantity: float | None = None
    unit: str | None = None
    unit_rate: float | None = None


class UsageMonth(BaseModel):
    month: str
    electricity_kwh: float
    water_m3: float
    estimated: bool


class BillBreakdown(BaseModel):
    bill_id: str
    period_start: date
    period_end: date
    due_date: date
    amount_due: float
    previous_amount: float | None
    payment_method: str
    reading_type: Literal["actual", "estimated"]
    last_actual_read_date: date | None
    lines: list[BillLine]
    usage_history: list[UsageMonth]
    change_reasons: list[str]
