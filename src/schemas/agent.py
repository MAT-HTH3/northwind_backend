"""The agent desk's shapes (the frontend's docs/api-contract.md, sections 4–8). The desk works out
triage and statistics itself; these are raw records."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.schemas.bill import BillBreakdown
from src.schemas.customer import CustomerProfile

CaseStatusName = Literal["new", "in_progress", "waiting_customer", "resolved"]
Resolution = Literal[
    "information_only", "explained_bill", "bill_corrected", "refund_issued", "field_visit", "other"
]
UrgencyCode = Literal["P1", "P2", "P3"]


class AgentCase(BaseModel):
    case_id: str
    account_id: str
    customer_name: str
    region: str
    vulnerable: bool
    channel: Literal["chat", "phone", "email", "web", "letter"]
    category: Literal["Billing", "Meter reading", "Payments", "Supply", "Water quality", "Service"]
    subject: str
    description: str
    opened_at: datetime
    closed_at: datetime | None
    status: CaseStatusName
    assignee: str | None
    resolution: Resolution | None
    disputed_amount: float | None
    transfers: int
    reopened: bool
    priority_override: UrgencyCode | None
    source: Literal["direct", "assistant"]


class AssistantConversation(BaseModel):
    conversation_id: str
    account_id: str
    customer_name: str
    started_at: datetime
    resolved: bool  # Auto-resolved (CONTEXT.md): an explicit Yes and no Support Case
    topic: str
    case_id: str | None


class FeedbackEntry(BaseModel):
    tags: list[str]
    note: str
    author: str
    at: datetime


class QueueFeedback(FeedbackEntry):
    case_id: str


class QueueSnapshot(BaseModel):
    cases: list[AgentCase]
    conversations: list[AssistantConversation]
    feedback: list[QueueFeedback]
    generated_at: datetime


class TranscriptEntry(BaseModel):
    role: Literal["customer", "assistant", "system"]
    text: str
    at: datetime


class MeterRead(BaseModel):
    date: date
    value: float
    unit: Literal["kWh", "m³"]
    type: Literal["actual", "estimated", "customer"]


class AccountCustomer(CustomerProfile):
    vulnerable: bool
    phone: str | None = None
    email: str | None = None


class AccountSnapshot(BaseModel):
    customer: AccountCustomer
    bill: BillBreakdown | None
    meter_reads: list[MeterRead]


class TimelineEntry(BaseModel):
    at: datetime
    label: str
    actor: str


class CaseDetail(BaseModel):
    case: AgentCase
    transcript: list[TranscriptEntry] | None
    account: AccountSnapshot | None
    timeline: list[TimelineEntry]
    feedback: list[FeedbackEntry]


class ConversationDetail(BaseModel):
    conversation: AssistantConversation
    transcript: list[TranscriptEntry]


class CaseUpdate(BaseModel):
    """PATCH body: any of these. A field sent as null clears it (assignee, urgency override)."""

    status: CaseStatusName | None = None
    assignee: str | None = None
    priority_override: UrgencyCode | None = None
    resolution: Resolution | None = None


class FeedbackRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)
    note: str
    author: str = Field(min_length=1)
