from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import CustomerReading, ReadingStatus, Service
from src.repositories.ids import IdFactory, new_reading_id, unique_id


class ReadingRepository:
    """Customer Readings submitted in chat. Methods flush; the caller commits."""

    def __init__(self, session: AsyncSession, id_factory: IdFactory = new_reading_id) -> None:
        self.session = session
        self.id_factory = id_factory

    async def create(
        self,
        *,
        account_id: str,
        case_id: str,
        conversation_id: str,
        service: Service,
        value: int,
        read_date: date,
    ) -> CustomerReading:
        reading = CustomerReading(
            id=await unique_id(self.session, CustomerReading, self.id_factory),
            account_id=account_id,
            case_id=case_id,
            conversation_id=conversation_id,
            service=service,
            value=value,
            read_date=read_date,
            status=ReadingStatus.AWAITING_REVIEW,
        )
        self.session.add(reading)
        await self.session.flush()
        return reading

    async def list_for_case(self, case_id: str) -> list[CustomerReading]:
        query = (
            select(CustomerReading)
            .where(CustomerReading.case_id == case_id)
            .order_by(CustomerReading.created_at)
        )
        return list(await self.session.scalars(query))

    async def list_for_account(self, account_id: str) -> list[CustomerReading]:
        query = (
            select(CustomerReading)
            .where(CustomerReading.account_id == account_id)
            .order_by(CustomerReading.created_at.desc())
        )
        return list(await self.session.scalars(query))
