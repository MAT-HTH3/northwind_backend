from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base
from src.models.types import UTCDateTime, utcnow


class Conversation(Base):
    """One chat conversation, for the agent desk's "Resolved by AI" group and figures."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # the widget's conversation_id
    account_id: Mapped[str] = mapped_column(String(32), index=True)
    customer_name: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    # Set by code from what answered the latest message, e.g. "Bill explained".
    topic: Mapped[str | None] = mapped_column(String(64))
    # The latest Support Case this conversation was part of.
    case_id: Mapped[str | None] = mapped_column(ForeignKey("support_cases.id"))
    # The customer answered "No" to "Did this solve your problem?": their next message goes to a
    # Human Agent. Cleared when that message is handled.
    pending_handoff: Mapped[bool] = mapped_column(default=False)
