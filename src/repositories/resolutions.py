from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ResolutionAnswer


class ResolutionRepository:
    """Answers to "Did this solve your problem?". Methods flush; the caller commits."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self, *, conversation_id: str, account_id: str, resolved: bool
    ) -> ResolutionAnswer:
        answer = ResolutionAnswer(
            conversation_id=conversation_id, account_id=account_id, resolved=resolved
        )
        self.session.add(answer)
        await self.session.flush()
        return answer

    async def list_for_conversation(self, conversation_id: str) -> list[ResolutionAnswer]:
        query = (
            select(ResolutionAnswer)
            .where(ResolutionAnswer.conversation_id == conversation_id)
            .order_by(ResolutionAnswer.answered_at, ResolutionAnswer.id)
        )
        return list(await self.session.scalars(query))
