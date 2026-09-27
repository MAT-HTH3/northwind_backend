"""Builds the Unified Customer History: the memory bridge across the Legacy Systems.

CRM is read first because only it knows the other systems' ids. Everything else is fetched
concurrently, then normalised.
"""

import asyncio
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.history.models import (
    Bill,
    Billing,
    BillLine,
    Contact,
    CustomerDetails,
    LegacyCase,
    Meter,
    MeterRead,
    SubmittedReading,
    SupportCaseSummary,
    Tariff,
    UnifiedCustomerHistory,
    UsageMonth,
)
from src.legacy import LegacySystems, crm
from src.legacy import billing as lb
from src.legacy import casetrack as ct
from src.legacy import metering as mt
from src.models import CustomerReading, SupportCase
from src.repositories import ReadingRepository, SupportCaseRepository

USAGE_MONTHS = 6


class UnknownCustomerError(LookupError):
    pass


async def build_history(
    account_id: str,
    legacy: LegacySystems,
    session_factory: async_sessionmaker[AsyncSession],
) -> UnifiedCustomerHistory:
    customer = await legacy.crm.get_customer(account_id)
    if customer is None:
        raise UnknownCustomerError(account_id)
    refs = customer.cross_references

    async def our_records() -> tuple[list[SupportCase], list[CustomerReading]]:
        async with session_factory() as session:
            cases = await SupportCaseRepository(session).list_for_account(account_id)
            readings = await ReadingRepository(session).list_for_account(account_id)
            return cases, readings

    account, cases_ct, (cases, readings), *points = await asyncio.gather(
        legacy.billing.get_account(refs.legacy_billing_account),
        legacy.casetrack.get_cases(refs.case_track_customer),
        our_records(),
        *(legacy.metering.get_meter_point(mpxn) for mpxn in refs.meter_points),
    )

    unavailable = [
        system
        for system, found in (("Legacy Billing", account), ("CaseTrack", cases_ct))
        if found is None
    ]
    if any(point is None for point in points):
        unavailable.append("Metering")
    meters = [_meter(point) for point in points if point is not None]

    return UnifiedCustomerHistory(
        customer=_customer(customer),
        billing=_billing(account) if account else None,
        meters=meters,
        usage_history=_usage_history(meters),
        contacts=sorted(
            (_contact(i) for i in customer.interactions), key=lambda c: c.occurred_at, reverse=True
        ),
        past_cases=sorted(
            (_legacy_case(c) for c in cases_ct or []), key=lambda c: c.opened_on, reverse=True
        ),
        support_cases=[_support_case(c) for c in cases],
        submitted_readings=[_reading(r) for r in readings],
        unavailable=unavailable,
    )


# --- CRM -------------------------------------------------------------------------------------


def _customer(c: crm.CrmCustomer) -> CustomerDetails:
    return CustomerDetails(
        account_id=c.customer_id,
        first_name=c.name.given,
        last_name=c.name.family,
        region=c.region,
        vulnerable=c.vulnerable,
        email=c.contact.email,
        phone=c.contact.phone,
        preferred_channel=c.contact.preferred_channel,
        services=[s.type for s in c.services if s.status == "active"],
    )


def _contact(i: crm.CrmInteraction) -> Contact:
    return Contact(
        occurred_at=i.occurred_at, channel=i.channel, handled_by=i.handled_by, summary=i.summary
    )


# --- Legacy Billing --------------------------------------------------------------------------

_SERVICES = {"ELEC": "electricity", "WATR": "water", "TAX": "other"}
_UNITS = {"KWH": "kWh", "M3": "m³", "DAY": "days"}
_PAYMENT_METHODS = {"DD": "Direct Debit", "CARD": "Card", "CHEQUE": "Cheque"}
_LINE_LABELS = {
    "ELECTRICITY UNITS": "Electricity used",
    "ELEC STANDING CHG": "Electricity standing charge",
    "WATER SUPPLY+WASTE": "Water supply & wastewater",
    "WATER STANDING CHG": "Water standing charge",
    "VAT 5% ENERGY": "VAT (5% on energy)",
}


def _ddmmyyyy(value: str) -> date:
    return datetime.strptime(value, "%d%m%Y").date()


def _pounds(pence: float) -> float:
    return round(pence / 100, 2)


def _billing(a: lb.BillingAccount) -> Billing:
    return Billing(
        payment_method=_PAYMENT_METHODS[a.pay_method],
        direct_debit_day=a.dd_day,
        bills=[_bill(invoice) for invoice in a.invoices],
        tariffs=[
            Tariff(
                service=_SERVICES[t.svc],
                component="unit" if t.component == "UNIT" else "standing",
                effective_from=_ddmmyyyy(t.effective),
                rate=round(t.rate_pence / 100, 4),
            )
            for t in a.tariff_history
        ],
    )


def _bill(i: lb.BillingInvoice) -> Bill:
    return Bill(
        bill_id=i.inv_ref,
        period_start=_ddmmyyyy(i.period_from),
        period_end=_ddmmyyyy(i.period_to),
        issued_on=_ddmmyyyy(i.issued),
        due_date=_ddmmyyyy(i.due),
        amount_due=_pounds(i.total_pence),
        reading_type="actual" if i.read_type == "A" else "estimated",
        paid=i.paid == "Y",
        lines=[
            BillLine(
                service=_SERVICES[line.svc],
                label=_LINE_LABELS.get(line.desc, line.desc.capitalize()),
                amount=_pounds(line.amt_pence),
                quantity=line.qty,
                unit=_UNITS[line.uom] if line.uom else None,
                unit_rate=round(line.rate_pence / 100, 4) if line.rate_pence is not None else None,
            )
            for line in i.lines
        ],
    )


# --- Metering --------------------------------------------------------------------------------


def _meter(p: mt.MeterPoint) -> Meter:
    scale = 1000 if p.register_unit == "litres" else 1  # water is billed in m³
    reads = [
        MeterRead(
            read_on=r.read_at.date(),
            value=r.value / scale,
            kind="estimated" if r.source == "ESTIMATE" else "actual",
            source=r.source.lower(),
        )
        for r in sorted(p.reads, key=lambda r: r.read_at)
    ]
    actual = [r.read_on for r in reads if r.kind == "actual"]
    return Meter(
        service=p.service,
        meter_point=p.mpxn,
        serial=p.meter_serial,
        smart=p.smart,
        unit="kWh" if p.service == "electricity" else "m³",
        reads=reads,
        last_actual_read_on=actual[-1] if actual else None,
    )


def _consumption(meter: Meter) -> dict[str, tuple[float, bool]]:
    """Usage between consecutive reads, keyed by the month of the closing read."""
    return {
        closing.read_on.strftime("%Y-%m"): (
            round(closing.value - opening.value, 3),
            closing.kind == "estimated",
        )
        for opening, closing in zip(meter.reads, meter.reads[1:], strict=False)
    }


def _usage_history(meters: list[Meter]) -> list[UsageMonth]:
    by_service = {meter.service: _consumption(meter) for meter in meters}
    electricity = by_service.get("electricity", {})
    water = by_service.get("water", {})
    months = sorted(set(electricity) | set(water))[-USAGE_MONTHS:]
    return [
        UsageMonth(
            month=month,
            electricity_kwh=electricity.get(month, (0.0, False))[0],
            water_m3=water.get(month, (0.0, False))[0],
            estimated=electricity.get(month, (0, False))[1] or water.get(month, (0, False))[1],
        )
        for month in months
    ]


# --- CaseTrack -------------------------------------------------------------------------------

_CASE_CATEGORIES = {
    "BILL-EST": "Query about an estimated bill",
    "BILL-DSP": "Bill dispute",
    "PAY-DD": "Direct Debit change",
    "MTR-FLT": "Faulty meter",
}


def _slashed(value: str) -> date:
    return datetime.strptime(value, "%Y/%m/%d").date()


def _legacy_case(c: ct.CaseTrackCase) -> LegacyCase:
    return LegacyCase(
        reference=f"CT-{c.case_no}",
        category=_CASE_CATEGORIES.get(c.cat_cd, c.cat_cd),
        status="open" if c.stat == "OPEN" else "closed",
        opened_on=_slashed(c.opened),
        closed_on=_slashed(c.closed) if c.closed else None,
        queue=c.queue,
        times_reopened=c.reopened,
        notes=c.notes,
    )


# --- Our records -----------------------------------------------------------------------------


def _support_case(c: SupportCase) -> SupportCaseSummary:
    return SupportCaseSummary(
        case_id=c.id,
        category=c.category,
        priority=c.priority.value,
        status=c.status.value,
        queue=c.queue,
        opened_at=c.created_at,
        expected_response_by=c.expected_response_by,
        closed_at=c.closed_at,
        outcome=c.outcome,
    )


def _reading(r: CustomerReading) -> SubmittedReading:
    return SubmittedReading(
        reading_id=r.id,
        service=r.service.value,
        value=r.value,
        unit=r.unit,
        read_date=r.read_date,
        status=r.status.value,
        case_id=r.case_id,
    )
