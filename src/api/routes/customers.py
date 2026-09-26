from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.legacy import LegacySystems, get_legacy_systems
from src.schemas.customer import CustomerProfile

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/{account_id}", response_model=CustomerProfile)
async def get_customer(
    account_id: str,
    legacy: Annotated[LegacySystems, Depends(get_legacy_systems)],
) -> CustomerProfile:
    customer = await legacy.crm.get_customer(account_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return CustomerProfile(
        account_id=customer.customer_id,
        first_name=customer.name.given,
        last_name=customer.name.family,
        region=customer.region,
        services=[service.type for service in customer.services if service.status == "active"],
    )
