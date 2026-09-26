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
    AWAITING_REVIEW = "awaiting_review"


UNITS = {Service.ELECTRICITY: "kWh", Service.WATER: "m³"}


class CustomerReading(Base):
    """A meter reading a customer submitted in chat. Always reviewed by a Human Agent (ADR 0002)."""

    __tablename__ = "customer_readings"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # "MR-583201"
    account_id: Mapped[str] = mapped_column(String(32), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(64))
    service: Mapped[Service] = mapped_column(str_enum(Service, "service"))
    value: Mapped[int]  # meter displays are whole numbers; digits after a decimal point are ignored
    read_date: Mapped[date]
    status: Mapped[ReadingStatus] = mapped_column(
        str_enum(ReadingStatus, "reading_status"), default=ReadingStatus.AWAITING_REVIEW
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    @property
    def unit(self) -> str:
        return UNITS[self.service]
