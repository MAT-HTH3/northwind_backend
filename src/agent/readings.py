"""Customer Readings (ADR 0004): the plausibility check and the re-priced bill.

All arithmetic is code; the model never sees a reading's effect on the bill (ADR 0003).
"""

from dataclasses import dataclass

from src.history.models import Bill, Meter, UnifiedCustomerHistory

# The most usage a single bill period can plausibly show. Demo values, to be tuned with the
# metering team.
MAX_USAGE = {"electricity": 2000, "water": 100}
ENERGY_VAT = 0.05


@dataclass(frozen=True)
class ReadingCheck:
    plausible: bool
    usage: float | None  # since the reading the current bill opened with


def check_reading(history: UnifiedCustomerHistory, service: str, value: int) -> ReadingCheck:
    """Plausible if above the last actual reading and the reading the current bill opened with,
    and the usage since that opening reading is no more than MAX_USAGE."""
    meter = _meter(history, service)
    bill = _latest_bill(history)
    if meter is None or bill is None:
        return ReadingCheck(False, None)
    opening = opening_read(meter, bill)
    last_actual = next((r.value for r in reversed(meter.reads) if r.kind == "actual"), None)
    if opening is None:
        return ReadingCheck(False, None)
    usage = round(value - opening, 3)
    plausible = (last_actual is None or value > last_actual) and 0 < usage <= MAX_USAGE[service]
    return ReadingCheck(plausible, usage)


def opening_read(meter: Meter, bill: Bill) -> float | None:
    """The reading the bill period opened with: the last read before the period started."""
    before = [r for r in meter.reads if r.read_on < bill.period_start]
    return before[-1].value if before else None


def reprice(bill: Bill, service: str, usage: float) -> Bill:
    """The bill recalculated with the actual usage for one service; VAT follows energy."""
    unit = "kWh" if service == "electricity" else "m³"
    lines = [
        line.model_copy(update={"quantity": usage, "amount": round(usage * line.unit_rate, 2)})
        if line.service == service and line.unit == unit and line.unit_rate is not None
        else line
        for line in bill.lines
    ]
    energy = sum(line.amount for line in lines if line.service == "electricity")
    lines = [
        line.model_copy(update={"amount": round(energy * ENERGY_VAT, 2)})
        if line.service == "other" and line.label.startswith("VAT")
        else line
        for line in lines
    ]
    return bill.model_copy(
        update={
            "lines": lines,
            "amount_due": round(sum(line.amount for line in lines), 2),
            "reading_type": "actual",
        }
    )


def with_accepted_readings(
    history: UnifiedCustomerHistory,
) -> tuple[UnifiedCustomerHistory, list[str]]:
    """The history with the latest bill re-priced by any accepted reading taken after it began,
    plus a plain-English reason for each re-pricing (for the bill card)."""
    bill = _latest_bill(history)
    if bill is None or bill.reading_type == "actual":
        return history, []
    reasons = []
    for service in ("electricity", "water"):
        reading = next(
            (
                r
                for r in history.submitted_readings  # newest first
                if r.service == service
                and r.status == "accepted"
                and r.read_date >= bill.period_start
            ),
            None,
        )
        meter = _meter(history, service)
        opening = opening_read(meter, bill) if meter else None
        if reading is None or opening is None:
            continue
        bill = reprice(bill, service, round(reading.value - opening, 3))
        reasons.append(
            f"Recalculated from your {service} meter reading of {reading.value:,} {reading.unit} "
            f"on {reading.read_date.day} {reading.read_date:%B}."
        )
    if not reasons:
        return history, []
    bills = [bill, *history.billing.bills[1:]]
    billing = history.billing.model_copy(update={"bills": bills})
    return history.model_copy(update={"billing": billing}), reasons


def revised_amount(history: UnifiedCustomerHistory, service: str, usage: float) -> float | None:
    bill = _latest_bill(history)
    return reprice(bill, service, usage).amount_due if bill else None


def _meter(history: UnifiedCustomerHistory, service: str) -> Meter | None:
    return next((m for m in history.meters if m.service == service), None)


def _latest_bill(history: UnifiedCustomerHistory) -> Bill | None:
    return history.billing.bills[0] if history.billing and history.billing.bills else None
