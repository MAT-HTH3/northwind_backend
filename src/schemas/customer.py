from typing import Literal

from pydantic import BaseModel


class CustomerProfile(BaseModel):
    """GET /api/customers/{account_id}. Shape defined in the frontend's docs/api-contract.md."""

    account_id: str
    first_name: str
    last_name: str
    region: str
    services: list[Literal["electricity", "water"]]
