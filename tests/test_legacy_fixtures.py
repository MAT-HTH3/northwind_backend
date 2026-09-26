"""The mock Legacy Systems must agree with each other, or the AI Assistant will explain a bill
that contradicts the meter readings."""

from src.legacy import get_legacy_systems

ACCOUNT = "ACC-372876"


async def test_every_crm_cross_reference_resolves():
    legacy = get_legacy_systems()
    refs = (await legacy.crm.get_customer(ACCOUNT)).cross_references

    assert await legacy.billing.get_account(refs.legacy_billing_account) is not None
    assert await legacy.casetrack.get_cases(refs.case_track_customer) is not None
    services = {(await legacy.metering.get_meter_point(m)).service for m in refs.meter_points}
    assert services == {"electricity", "water"}


async def test_invoice_lines_add_up_and_the_demo_bill_is_169_60():
    legacy = get_legacy_systems()
    account = await legacy.billing.get_account("0372876")

    for invoice in account.invoices:
        assert sum(line.amt_pence for line in invoice.lines) == invoice.total_pence
    assert account.invoices[0].total_pence == 16960


async def test_billed_usage_matches_the_meter_reads_for_each_period():
    legacy = get_legacy_systems()
    account = await legacy.billing.get_account("0372876")
    reads = {
        read.read_at.strftime("%d%m%Y"): read.value
        for read in (await legacy.metering.get_meter_point("1900012345678")).reads
    }

    for invoice in account.invoices:
        units = next(line for line in invoice.lines if line.uom == "KWH")
        # A period runs from the day after the opening read to the day of the closing read.
        day, month, year = (
            invoice.period_from[:2],
            invoice.period_from[2:4],
            invoice.period_from[4:],
        )
        opening = reads[f"{int(day) - 1:02d}{month}{year}"]
        closing = reads[invoice.period_to]
        assert units.qty == closing - opening, invoice.inv_ref
