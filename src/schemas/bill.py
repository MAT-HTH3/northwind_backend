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


class RateChange(BaseModel):
    label: str  # "Electricity unit rate"
    unit: str  # "kWh"
    from_rate: float
    to_rate: float
    effective_date: date


class BillBalance(BaseModel):
    previous_balance: float
    payments_received: float
    last_payment_date: date | None = None
    current_balance: float


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
    # Optional extras the full breakdown shows.
    tariff_name: str | None = None
    rate_changes: list[RateChange] | None = None
    balance: BillBalance | None = None
