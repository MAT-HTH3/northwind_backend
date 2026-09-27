from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base


class SeedExtra(Base):
    """Invented demo records the agent desk shows but no live system holds: transcripts of
    seeded chats and account snapshots for seeded (non-CRM) accounts."""

    __tablename__ = "seed_extras"

    kind: Mapped[str] = mapped_column(String(16), primary_key=True)  # "case" or "conversation"
    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transcript: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    account: Mapped[dict[str, Any] | None] = mapped_column(JSON)
