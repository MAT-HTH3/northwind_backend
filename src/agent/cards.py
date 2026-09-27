"""Cards produced by code (not chosen by the model). They ride on a reply's
AIMessage.additional_kwargs["ui_cards"], and the chat stream sends each one as a tool-call event
that carries its result."""

from typing import Any

from src.models import CustomerReading, SupportCase
from src.schemas.cards import MeterReadingReceipt, SupportCaseCard

UI_CARDS = "ui_cards"


def receipt_card(reading: CustomerReading, revised_amount_due: float | None) -> dict[str, Any]:
    return {
        "name": "submit_meter_reading",
        "args": {"service": reading.service.value, "value": reading.value},
        "result": MeterReadingReceipt(
            reading_id=reading.id,
            service=reading.service.value,
            value=reading.value,
            unit=reading.unit,
            read_date=reading.read_date,
            status=reading.status.value,
            revised_amount_due=revised_amount_due,
        ).model_dump(mode="json"),
    }


def case_card(case: SupportCase) -> dict[str, Any]:
    return {
        "name": "create_support_case",
        "args": {},
        "result": SupportCaseCard(
            case_id=case.id,
            category=case.category,
            priority=case.priority.value,
            sla_days=case.sla_days,
            queue=case.queue,
            expected_response_by=case.expected_response_by,
            summary=case.summary,
        ).model_dump(mode="json"),
    }
