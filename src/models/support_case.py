from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db import Base
from src.models.types import UTCDateTime, str_enum, utcnow


class Priority(StrEnum):
    HIGH = "high"
    MID = "mid"
    LOW = "low"


class CaseStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class SupportCase(Base):
    """A Hand-off request handed to a Human Agent. See CONTEXT.md and ADR 0001."""

    __tablename__ = "support_cases"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # "NW-231904"
    account_id: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(64))
    priority: Mapped[Priority] = mapped_column(str_enum(Priority, "priority"))
    sla_days: Mapped[int]
    queue: Mapped[str] = mapped_column(String(64))
    expected_response_by: Mapped[date]
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[CaseStatus] = mapped_column(
        str_enum(CaseStatus, "case_status"), default=CaseStatus.OPEN, index=True
    )
    outcome: Mapped[str | None] = mapped_column(Text)  # the Case Outcome, set on close
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

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
