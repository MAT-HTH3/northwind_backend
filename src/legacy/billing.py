"""Legacy Billing (the Dunmoor platform): invoices, line items, tariffs, payment method.

Records mirror the legacy format: upper-case keys, money in pence, dates as DDMMYYYY strings.
Turning them into the Unified Customer History is the Analyzer's job.
"""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from src.legacy._fixtures import load_fixture


class _LegacyRecord(BaseModel):
    model_config = ConfigDict(alias_generator=str.upper, frozen=True)


class BillingLine(_LegacyRecord):
    svc: Literal["ELEC", "WATR", "TAX"]
    desc: str
    qty: float | None = None
    uom: Literal["KWH", "M3", "DAY"] | None = None
    rate_pence: float | None = None
    amt_pence: int


class BillingInvoice(_LegacyRecord):
    inv_ref: str
    period_from: str  # DDMMYYYY
    period_to: str
    issued: str
    due: str
    read_type: Literal["A", "E"]  # actual / estimated
    total_pence: int
    paid: Literal["Y", "N"]
    lines: list[BillingLine]


class TariffEntry(_LegacyRecord):
    svc: Literal["ELEC", "WATR"]
    component: Literal["UNIT", "STANDING"]
    effective: str  # DDMMYYYY
    rate_pence: float


class BillingAccount(_LegacyRecord):
    acct_no: str
    pay_method: Literal["DD", "CARD", "CHEQUE"]
    dd_day: int | None = None
    invoices: list[BillingInvoice]  # newest first
    tariff_history: list[TariffEntry]


class LegacyBilling(Protocol):
    async def get_account(self, acct_no: str) -> BillingAccount | None: ...


class MockLegacyBilling:
    def __init__(self, fixture: str = "legacy_billing.json") -> None:
        accounts = [BillingAccount.model_validate(a) for a in load_fixture(fixture)["ACCOUNTS"]]
        self._accounts = {account.acct_no: account for account in accounts}

    async def get_account(self, acct_no: str) -> BillingAccount | None:
        return self._accounts.get(acct_no)
