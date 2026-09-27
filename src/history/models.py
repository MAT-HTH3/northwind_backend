"""The Unified Customer History: one normalised view of everything known about a customer.

Money is GBP, dates are dates, units are kWh / m³ / days, and codes are plain English, whatever
format the Legacy System that supplied them used.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

ServiceName = Literal["electricity", "water"]


class CustomerDetails(BaseModel):
    account_id: str
    first_name: str
    last_name: str
    region: str
    vulnerable: bool
    email: str
    phone: str
    preferred_channel: str
    services: list[ServiceName]


class BillLine(BaseModel):
    service: ServiceName | Literal["other"]
    label: str
    amount: float
    quantity: float | None = None
    unit: Literal["kWh", "m³", "days"] | None = None
    unit_rate: float | None = None  # GBP per unit


class Bill(BaseModel):
    bill_id: str
    period_start: date
    period_end: date
    issued_on: date
    due_date: date
    amount_due: float
    reading_type: Literal["actual", "estimated"]
    paid: bool
    lines: list[BillLine]


class Tariff(BaseModel):
    service: ServiceName
    component: Literal["unit", "standing"]
    effective_from: date
    rate: float  # GBP per unit or per day


class Billing(BaseModel):
    payment_method: str  # "Direct Debit"
    direct_debit_day: int | None
    bills: list[Bill]  # newest first
    tariffs: list[Tariff]


class MeterRead(BaseModel):
    read_on: date
    value: float
    kind: Literal["actual", "estimated"]
    source: Literal["customer", "agent", "estimate"]


class Meter(BaseModel):
    service: ServiceName
    meter_point: str
    serial: str
    smart: bool
    unit: Literal["kWh", "m³"]
    reads: list[MeterRead]  # oldest first
    last_actual_read_on: date | None


class UsageMonth(BaseModel):
    month: str  # YYYY-MM, the month of the closing read
    electricity_kwh: float
    water_m3: float
    estimated: bool


class Contact(BaseModel):
    occurred_at: datetime
    channel: str
    handled_by: str
    summary: str


class LegacyCase(BaseModel):
    """A past case from CaseTrack."""

    reference: str  # "CT-88123"
    category: str
    status: Literal["open", "closed"]
    opened_on: date
    closed_on: date | None
    queue: str
    times_reopened: int
    notes: list[str]


class SubmittedReading(BaseModel):
    reading_id: str
    service: ServiceName
    value: int
    unit: str
    read_date: date
    status: str  # "awaiting_review"
    case_id: str


class SupportCaseSummary(BaseModel):
    """A Support Case from our own records, with its Case Outcome once closed."""

    case_id: str
    category: str
    priority: str
    status: Literal["open", "closed"]
    queue: str
    opened_at: datetime
    expected_response_by: date
    closed_at: datetime | None
    outcome: str | None


class UnifiedCustomerHistory(BaseModel):
    customer: CustomerDetails
    billing: Billing | None
    meters: list[Meter]
    usage_history: list[UsageMonth]  # last six months, oldest first
    contacts: list[Contact]  # newest first
    past_cases: list[LegacyCase]  # CaseTrack, newest first
    support_cases: list[SupportCaseSummary]  # ours, newest first
    submitted_readings: list[SubmittedReading]  # newest first
    unavailable: list[str]  # Legacy Systems that had no record for this customer
