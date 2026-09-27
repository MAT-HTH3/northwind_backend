"""CRM: customer profile, past contacts, and the cross-references to every other Legacy System.

The only system keyed by the account id the widget sends (e.g. "ACC-DEMO01").
"""

from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from src.legacy._fixtures import load_fixture


class _CrmRecord(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, frozen=True)


class CrmName(_CrmRecord):
    given: str
    family: str


class CrmContact(_CrmRecord):
    email: str
    phone: str
    preferred_channel: Literal["chat", "email", "phone"]


class CrmService(_CrmRecord):
    type: Literal["electricity", "water"]
    status: Literal["active", "closed"]
    since: date


class CrmCrossReferences(_CrmRecord):
    legacy_billing_account: str
    case_track_customer: str
    meter_points: list[str]


class CrmInteraction(_CrmRecord):
    id: str
    channel: Literal["phone", "email", "chat", "letter"]
    occurred_at: datetime
    handled_by: str
    summary: str


class CrmCustomer(_CrmRecord):
    customer_id: str
    name: CrmName
    region: str
    vulnerable: bool  # on the Priority Services Register
    contact: CrmContact
    services: list[CrmService]
    cross_references: CrmCrossReferences
    interactions: list[CrmInteraction]


class Crm(Protocol):
    async def get_customer(self, customer_id: str) -> CrmCustomer | None: ...


class MockCrm:
    def __init__(self, fixture: str = "crm.json") -> None:
        customers = [CrmCustomer.model_validate(c) for c in load_fixture(fixture)["customers"]]
        self._customers = {customer.customer_id: customer for customer in customers}

    async def get_customer(self, customer_id: str) -> CrmCustomer | None:
        return self._customers.get(customer_id)
