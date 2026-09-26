"""Builds the BillBreakdown card from the Unified Customer History.

The reasons a bill changed are worked out here, in code, so the figures the customer sees are
never the LLM's arithmetic.
"""

from datetime import date

from src.history.models import Bill, UnifiedCustomerHistory
from src.schemas.bill import BillBreakdown, BillLine, UsageMonth

TYPICAL_WINDOW = 3  # actual months averaged for "typical" usage ("last three" in the text)


class BillNotFoundError(LookupError):
    pass


def build_bill_breakdown(
    history: UnifiedCustomerHistory, bill_id: str | None = None
) -> BillBreakdown:
    if history.billing is None or not history.billing.bills:
        raise BillNotFoundError("No bills in Legacy Billing for this customer")
    bills = history.billing.bills  # newest first
    if not bill_id:  # Gemini sometimes sends "" for "the latest"
        index = 0
    else:
        index = next((i for i, b in enumerate(bills) if b.bill_id == bill_id), None)
    if index is None:
        available = ", ".join(f"{b.bill_id} ({b.period_end:%B %Y})" for b in bills)
        raise BillNotFoundError(f"There is no bill {bill_id}. Available bills: {available}.")
    bill = bills[index]
    previous = bills[index + 1] if index + 1 < len(bills) else None

    return BillBreakdown(
        bill_id=bill.bill_id,
        period_start=bill.period_start,
        period_end=bill.period_end,
        due_date=bill.due_date,
        amount_due=bill.amount_due,
        previous_amount=previous.amount_due if previous else None,
        payment_method=history.billing.payment_method,
        reading_type=bill.reading_type,
        last_actual_read_date=_last_actual_read(history, "electricity"),
        lines=[BillLine(**line.model_dump()) for line in bill.lines],
        usage_history=[
            UsageMonth(**u.model_dump())
            for u in history.usage_history
            if u.month <= bill.period_end.strftime("%Y-%m")
        ],
        change_reasons=change_reasons(history, bill, previous),
    )


def change_reasons(history: UnifiedCustomerHistory, bill: Bill, previous: Bill | None) -> list[str]:
    reasons = []
    if bill.reading_type == "estimated":
        last_read = _last_actual_read(history, "electricity")
        since = f" since {_day_month(last_read)}" if last_read else ""
        reasons.append(
            f"It uses an estimated electricity reading. We haven't had an actual reading{since}."
        )
        billed = next((line.quantity for line in bill.lines if line.unit == "kWh"), None)
        typical = _typical_kwh(history)
        if billed is not None and typical is not None:
            reasons.append(
                f"We estimated {billed:,.0f} kWh. Your last three actual readings "
                f"averaged {typical:,.0f} kWh."
            )

    # Tariff changes since the previous bill began (or within this bill, if it's the first).
    window_start = previous.period_start if previous else bill.period_start
    tariffs = sorted(
        history.billing.tariffs if history.billing else [], key=lambda t: t.effective_from
    )
    for i, tariff in enumerate(tariffs):
        if not (window_start < tariff.effective_from <= bill.period_end):
            continue
        before = next(
            (
                t
                for t in reversed(tariffs[:i])
                if t.service == tariff.service and t.component == tariff.component
            ),
            None,
        )
        if before and tariff.component == "unit" and tariff.rate != before.rate:
            direction = "rose" if tariff.rate > before.rate else "fell"
            unit = "kWh" if tariff.service == "electricity" else "m³"
            when = _day_month(tariff.effective_from)
            reasons.append(
                f"The {tariff.service} unit rate {direction} on {when}, "
                f"from {before.rate * 100:.2f}p to {tariff.rate * 100:.2f}p per {unit}."
            )
    return reasons


def _last_actual_read(history: UnifiedCustomerHistory, service: str) -> date | None:
    meter = next((m for m in history.meters if m.service == service), None)
    return meter.last_actual_read_on if meter else None


def _typical_kwh(history: UnifiedCustomerHistory) -> float | None:
    actual = [u.electricity_kwh for u in history.usage_history if not u.estimated]
    recent = actual[-TYPICAL_WINDOW:]
    return sum(recent) / len(recent) if len(recent) == TYPICAL_WINDOW else None


def _day_month(value: date) -> str:
    return f"{value.day} {value:%B}"
