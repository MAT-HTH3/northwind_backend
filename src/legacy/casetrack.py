"""CaseTrack: past support cases from the legacy case system.

Read-only. New Support Cases live in our own database and are never written here.
Dates are YYYY/MM/DD strings; status and category are codes.
"""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from src.legacy._fixtures import load_fixture


class CaseTrackCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_no: int
    opened: str  # YYYY/MM/DD
    closed: str | None = None
    stat: Literal["OPEN", "CLSD"]
    cat_cd: str  # e.g. "BILL-EST", "PAY-DD"
    queue: str
    reopened: int
    notes: list[str]


class CaseTrack(Protocol):
    async def get_cases(self, customer: str) -> list[CaseTrackCase] | None:
        """None when CaseTrack has no record of the customer."""
        ...


class MockCaseTrack:
    def __init__(self, fixture: str = "casetrack.json") -> None:
        self._customers = {
            customer: [CaseTrackCase.model_validate(c) for c in record["cases"]]
            for customer, record in load_fixture(fixture)["CUSTOMERS"].items()
        }

    async def get_cases(self, customer: str) -> list[CaseTrackCase] | None:
        return self._customers.get(customer)
