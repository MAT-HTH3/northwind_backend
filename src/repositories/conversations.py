from datetime import datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import CaseConversation, Conversation, ResolutionAnswer


class ConversationOutcome(StrEnum):
    """CONTEXT.md "Conversation outcomes"."""

    AUTO_RESOLVED = "auto_resolved"  # explicit Yes, no Support Case
    HANDED_OFF = "handed_off"  # a Support Case was opened, whatever was said before
    UNCONFIRMED = "unconfirmed"  # the customer never answered


class ConversationRepository:
    """Chat conversations. Methods flush; the caller commits."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, conversation_id: str) -> Conversation | None:
        return await self.session.get(Conversation, conversation_id)

    async def start(
        self, conversation_id: str, account_id: str, customer_name: str
    ) -> Conversation:
        """The conversation, created on its first message."""
        conversation = await self.get(conversation_id)
        if conversation is None:
            conversation = Conversation(
                id=conversation_id, account_id=account_id, customer_name=customer_name
            )
            self.session.add(conversation)
            await self.session.flush()
        return conversation

    async def take_pending_handoff(self, conversation: Conversation) -> bool:
        """Whether the customer's last answer was "No", clearing it: it applies once."""
        pending, conversation.pending_handoff = conversation.pending_handoff, False
        await self.session.flush()
        return pending

    async def record_turn(
        self, conversation: Conversation, *, topic: str | None, case_id: str | None
    ) -> None:
        if topic:
            conversation.topic = topic
        if case_id:
            conversation.case_id = case_id
        await self.session.flush()

    async def list_since(self, since: datetime) -> list[Conversation]:
        query = (
            select(Conversation)
            .where(Conversation.started_at >= since)
            .order_by(Conversation.started_at.desc())
        )
        return list(await self.session.scalars(query))

    async def outcome(self, conversation_id: str) -> ConversationOutcome:
        handed_off = await self.session.scalar(
            select(CaseConversation.case_id)
            .where(CaseConversation.conversation_id == conversation_id)
            .limit(1)
        )
        if handed_off is not None:
            return ConversationOutcome.HANDED_OFF
        said_yes = await self.session.scalar(
            select(ResolutionAnswer.id)
            .where(
                ResolutionAnswer.conversation_id == conversation_id,
                ResolutionAnswer.resolved.is_(True),
            )
            .limit(1)
        )
        return ConversationOutcome.AUTO_RESOLVED if said_yes else ConversationOutcome.UNCONFIRMED
