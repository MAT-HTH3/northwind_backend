from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base
from src.models.types import UTCDateTime, utcnow


class ResolutionAnswer(Base):
    """The customer's answer to "Did this solve your problem?"."""

    __tablename__ = "resolution_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[str] = mapped_column(String(32), index=True)
    resolved: Mapped[bool]
    answered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
