"""Builds the BillBreakdown card from the Unified Customer History.

The reasons a bill changed are worked out here, in code, so the figures the customer sees are
never the LLM's arithmetic.
"""

from datetime import date, timedelta

from src.history.models import Bill, UnifiedCustomerHistory
from src.schemas.bill import BillBalance, BillBreakdown, BillLine, RateChange, UsageMonth

TYPICAL_WINDOW = 3  # actual months averaged for "typical" usage ("last three" in the text)
RATE_CHANGE_WINDOW = timedelta(days=90)  # "time-adjusted rates" shown on the full breakdown
COMPONENT_LABELS = {"unit": "unit rate", "standing": "standing charge"}


class BillNotFoundError(LookupError):
    pass


def build_bill_breakdown(
    history: UnifiedCustomerHistory, month: str | None = None
) -> BillBreakdown:
    """The latest bill, or the one whose period ends in `month` ("YYYY-MM")."""
    if history.billing is None or not history.billing.bills:
        raise BillNotFoundError("There are no bills to show.")
    bills = history.billing.bills  # newest first
    if not month:  # Gemini sometimes sends "" for "the latest"
        index = 0
    else:
        index = next((i for i, b in enumerate(bills) if f"{b.period_end:%Y-%m}" == month), None)
    if index is None:
        # The model reads this, so it names no bills (ADR 0003).
        raise BillNotFoundError(
            "There is no bill for that month. Call again without a month to show the latest bill."
        )
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
        tariff_name=history.billing.tariff_name,
        rate_changes=rate_changes(history, bill),
        balance=balance(bill, previous),
    )


def rate_changes(history: UnifiedCustomerHistory, bill: Bill) -> list[RateChange]:
    """Rate changes in the 90 days up to the end of the bill period, with the rate they replaced."""
    tariffs = sorted(
        history.billing.tariffs if history.billing else [], key=lambda t: t.effective_from
    )
    changes = []
    for i, tariff in enumerate(tariffs):
        if not (bill.period_end - RATE_CHANGE_WINDOW <= tariff.effective_from <= bill.period_end):
            continue
        before = next(
            (
                t
                for t in reversed(tariffs[:i])
                if t.service == tariff.service and t.component == tariff.component
            ),
            None,
        )
        if before and before.rate != tariff.rate:
            unit = (
                ("kWh" if tariff.service == "electricity" else "m³")
                if tariff.component == "unit"
                else "day"
            )
            label = f"{tariff.service.capitalize()} {COMPONENT_LABELS[tariff.component]}"
            changes.append(
                RateChange(
                    label=label,
                    unit=unit,
                    from_rate=before.rate,
                    to_rate=tariff.rate,
                    effective_date=tariff.effective_from,
                )
            )
    return changes


def balance(bill: Bill, previous: Bill | None) -> BillBalance:
    """What was owed from the previous bill, what was paid, and what is owed now."""
    previous_balance = previous.amount_due if previous else 0.0
    paid = previous_balance if previous and previous.paid else 0.0
    return BillBalance(
        previous_balance=previous_balance,
        payments_received=paid,
        last_payment_date=previous.due_date if previous and previous.paid else None,
        current_balance=round(previous_balance - paid + bill.amount_due, 2),
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
