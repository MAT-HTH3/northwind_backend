from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db import Base
from src.models.types import UTCDateTime, str_enum, utcnow


class Urgency(StrEnum):
    """Stored as the API's P1/P2/P3 (CONTEXT.md "Urgency")."""

    HIGH = "P1"
    MEDIUM = "P2"
    LOW = "P3"


class CaseStatus(StrEnum):
    """CONTEXT.md "Case Status". Everything but Resolved is open, and holds its conversations."""

    NEW = "new"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    RESOLVED = "resolved"


class Channel(StrEnum):
    CHAT = "chat"
    PHONE = "phone"
    EMAIL = "email"
    WEB = "web"
    LETTER = "letter"


class CaseSource(StrEnum):
    DIRECT = "direct"  # raised with a Human Agent (phone, email, …)
    ASSISTANT = "assistant"  # handed off by the AI Assistant in chat


class SupportCase(Base):
    """A Hand-off request handed to a Human Agent. See CONTEXT.md and ADR 0001."""

    __tablename__ = "support_cases"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # "NW-231904"
    account_id: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(64))
    # Urgency; the column keeps the API contract's name.
    priority: Mapped[Urgency] = mapped_column(str_enum(Urgency, "priority"))
    sla_days: Mapped[int]
    queue: Mapped[str] = mapped_column(String(64))
    expected_response_by: Mapped[date]
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[CaseStatus] = mapped_column(
        str_enum(CaseStatus, "case_status"), default=CaseStatus.NEW, index=True
    )
    outcome: Mapped[str | None] = mapped_column(Text)  # the Case Outcome (resolution code)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)  # opened
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # What the agent desk shows and its Triage Rules read.
    customer_name: Mapped[str] = mapped_column(String(128), default="")
    region: Mapped[str] = mapped_column(String(32), default="")
    vulnerable: Mapped[bool] = mapped_column(default=False)
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"), default=Channel.CHAT)
    source: Mapped[CaseSource] = mapped_column(
        str_enum(CaseSource, "case_source"), default=CaseSource.ASSISTANT
    )
    subject: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")  # the customer's own words
    disputed_amount: Mapped[float | None]  # GBP
    transfers: Mapped[int] = mapped_column(default=0)
    reopened: Mapped[bool] = mapped_column(default=False)
    assignee: Mapped[str | None] = mapped_column(String(128))
    priority_override: Mapped[Urgency | None] = mapped_column(
        str_enum(Urgency, "priority_override")
    )

    @property
    def is_open(self) -> bool:
        return self.status != CaseStatus.RESOLVED

    conversations: Mapped[list[CaseConversation]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="CaseConversation.linked_at",
        lazy="selectin",
    )
    held_messages: Mapped[list[HeldMessage]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="HeldMessage.received_at",
        lazy="selectin",
    )
    feedback: Mapped[list[FeedbackNote]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="FeedbackNote.created_at",
        lazy="selectin",
    )
    timeline: Mapped[list[TimelineEvent]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="TimelineEvent.at",
        lazy="selectin",
    )


class CaseConversation(Base):
    """Links a conversation to a Support Case. One case can gather many conversations."""

    __tablename__ = "case_conversations"

    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id"), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    linked_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[SupportCase] = relationship(back_populates="conversations")


class HeldMessage(Base):
    """A customer message received while the conversation was held by an open case."""

    __tablename__ = "held_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[SupportCase] = relationship(back_populates="held_messages")


class FeedbackNote(Base):
    """CONTEXT.md "Feedback Note": for Human Agents only; never sent to the model."""

    __tablename__ = "feedback_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id"), index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text)  # stored and shown verbatim
    author: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    case: Mapped[SupportCase] = relationship(back_populates="feedback")


class TimelineEvent(Base):
    """One thing that happened to a Support Case, for the desk's History tab."""

    __tablename__ = "timeline_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id"), index=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    label: Mapped[str] = mapped_column(String(256))
    actor: Mapped[str] = mapped_column(String(128))

    case: Mapped[SupportCase] = relationship(back_populates="timeline")
