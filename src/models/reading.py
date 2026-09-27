from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base
from src.models.types import UTCDateTime, str_enum, utcnow


class Service(StrEnum):
    ELECTRICITY = "electricity"
    WATER = "water"


class ReadingStatus(StrEnum):
    ACCEPTED = "accepted"  # plausible: the bill was re-priced from it (ADR 0004)
    NEEDS_REVIEW = "needs_review"  # implausible: a Human Agent checks it


UNITS = {Service.ELECTRICITY: "kWh", Service.WATER: "m³"}


class CustomerReading(Base):
    """A Customer Reading typed in chat. Accepted if plausible, otherwise reviewed (ADR 0004)."""

    __tablename__ = "customer_readings"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # "MR-583201"
    account_id: Mapped[str] = mapped_column(String(32), index=True)
    # Only readings that need review belong to a Support Case.
    case_id: Mapped[str | None] = mapped_column(ForeignKey("support_cases.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(64))
    service: Mapped[Service] = mapped_column(str_enum(Service, "service"))
    value: Mapped[int]  # meter displays are whole numbers; digits after a decimal point are ignored
    read_date: Mapped[date]
    status: Mapped[ReadingStatus] = mapped_column(str_enum(ReadingStatus, "reading_status"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    @property
    def unit(self) -> str:
        return UNITS[self.service]
