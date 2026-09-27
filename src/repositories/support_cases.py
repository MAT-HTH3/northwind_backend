from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import CaseConversation, CaseStatus, HeldMessage, SupportCase, Urgency
from src.models.types import utcnow
from src.repositories.ids import IdFactory, new_case_id, unique_id


class CaseAlreadyClosedError(RuntimeError):
    pass


class SupportCaseRepository:
    """Support Cases and the conversations they gather. Methods flush; the caller commits."""

    def __init__(self, session: AsyncSession, id_factory: IdFactory = new_case_id) -> None:
        self.session = session
        self.id_factory = id_factory

    async def create(
        self,
        *,
        account_id: str,
        conversation_id: str,
        category: str,
        priority: Urgency,
        sla_days: int,
        queue: str,
        expected_response_by: date,
        summary: str,
    ) -> SupportCase:
        case = SupportCase(
            id=await unique_id(self.session, SupportCase, self.id_factory),
            account_id=account_id,
            category=category,
            priority=priority,
            sla_days=sla_days,
            queue=queue,
            expected_response_by=expected_response_by,
            summary=summary,
            status=CaseStatus.OPEN,
            conversations=[CaseConversation(conversation_id=conversation_id)],
        )
        self.session.add(case)
        await self.session.flush()
        return case

    async def get(self, case_id: str) -> SupportCase | None:
        return await self.session.get(SupportCase, case_id)

    async def list_all(self, status: CaseStatus | None = None) -> list[SupportCase]:
        query = select(SupportCase).order_by(SupportCase.created_at.desc())
        if status is not None:
            query = query.where(SupportCase.status == status)
        return list(await self.session.scalars(query))

    async def list_for_account(self, account_id: str) -> list[SupportCase]:
        query = (
            select(SupportCase)
            .where(SupportCase.account_id == account_id)
            .order_by(SupportCase.created_at.desc())
        )
        return list(await self.session.scalars(query))

    async def open_case_for_conversation(self, conversation_id: str) -> SupportCase | None:
        """The case holding this conversation, if any. A closed case no longer holds it."""
        query = (
            select(SupportCase)
            .join(CaseConversation)
            .where(
                CaseConversation.conversation_id == conversation_id,
                SupportCase.status == CaseStatus.OPEN,
            )
        )
        return await self.session.scalar(query)

    async def open_case_for_category(self, account_id: str, category: str) -> SupportCase | None:
        """An open case a new hand-off on the same topic should join instead of duplicating."""
        query = (
            select(SupportCase)
            .where(
                SupportCase.account_id == account_id,
                SupportCase.category == category,
                SupportCase.status == CaseStatus.OPEN,
            )
            .order_by(SupportCase.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(query)

    async def attach_conversation(self, case: SupportCase, conversation_id: str) -> None:
        if any(link.conversation_id == conversation_id for link in case.conversations):
            return
        case.conversations.append(CaseConversation(conversation_id=conversation_id))
        await self.session.flush()

    async def add_held_message(
        self, case: SupportCase, conversation_id: str, content: str
    ) -> HeldMessage:
        message = HeldMessage(conversation_id=conversation_id, content=content)
        case.held_messages.append(message)
        await self.session.flush()
        return message

    async def close(self, case: SupportCase, outcome: str) -> list[str]:
        """Record the Case Outcome and return every linked conversation, so each paused
        thread can be resumed."""
        if case.status == CaseStatus.CLOSED:
            raise CaseAlreadyClosedError(case.id)
        case.status = CaseStatus.CLOSED
        case.outcome = outcome
        case.closed_at = utcnow()
        await self.session.flush()
        return [link.conversation_id for link in case.conversations]
