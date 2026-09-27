from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    CaseConversation,
    CaseSource,
    CaseStatus,
    Channel,
    FeedbackNote,
    HeldMessage,
    SupportCase,
    TimelineEvent,
    Urgency,
)
from src.models.types import utcnow
from src.repositories.ids import IdFactory, new_case_id, unique_id

AI_ASSISTANT = "AI Assistant"
OUTCOME_LABELS = {
    "information_only": "gave information only",
    "explained_bill": "explained the bill",
    "bill_corrected": "corrected the bill",
    "refund_issued": "issued a refund",
    "field_visit": "booked a field visit",
    "other": "other",
}
STATUS_LABELS = {
    CaseStatus.NEW: "New",
    CaseStatus.IN_PROGRESS: "In progress",
    CaseStatus.WAITING_CUSTOMER: "Waiting for customer",
    CaseStatus.RESOLVED: "Resolved",
}


class CaseAlreadyClosedError(RuntimeError):
    pass


@dataclass
class CaseChanges:
    """What a Human Agent can change on the desk. None means "leave as it is"; `clear` names
    fields to set back to None (assignee, priority_override)."""

    status: CaseStatus | None = None
    assignee: str | None = None
    priority_override: Urgency | None = None
    resolution: str | None = None
    clear: set[str] = field(default_factory=set)


class SupportCaseRepository:
    """Support Cases and the conversations they gather. Methods flush; the caller commits."""

    def __init__(self, session: AsyncSession, id_factory: IdFactory = new_case_id) -> None:
        self.session = session
        self.id_factory = id_factory

    async def create(
        self,
        *,
        account_id: str,
        category: str,
        priority: Urgency,
        sla_days: int,
        queue: str,
        expected_response_by: date,
        summary: str,
        conversation_id: str | None = None,
        customer_name: str = "",
        region: str = "",
        vulnerable: bool = False,
        channel: Channel = Channel.CHAT,
        source: CaseSource = CaseSource.ASSISTANT,
        subject: str = "",
        description: str = "",
        disputed_amount: float | None = None,
        opened_at: datetime | None = None,
        opened_by: str = AI_ASSISTANT,
    ) -> SupportCase:
        opened_at = opened_at or utcnow()
        case = SupportCase(
            id=await unique_id(self.session, SupportCase, self.id_factory),
            account_id=account_id,
            category=category,
            priority=priority,
            sla_days=sla_days,
            queue=queue,
            expected_response_by=expected_response_by,
            summary=summary,
            status=CaseStatus.NEW,
            created_at=opened_at,
            customer_name=customer_name,
            region=region,
            vulnerable=vulnerable,
            channel=channel,
            source=source,
            subject=subject,
            description=description,
            disputed_amount=disputed_amount,
            conversations=(
                [CaseConversation(conversation_id=conversation_id, linked_at=opened_at)]
                if conversation_id
                else []
            ),
            timeline=[
                TimelineEvent(at=opened_at, label=f"Opened ({channel.value})", actor=opened_by)
            ],
        )
        self.session.add(case)
        await self.session.flush()
        return case

    async def get(self, case_id: str) -> SupportCase | None:
        return await self.session.get(SupportCase, case_id)

    async def list_all(self, *, open_only: bool = False) -> list[SupportCase]:
        query = select(SupportCase).order_by(SupportCase.created_at.desc())
        if open_only:
            query = query.where(SupportCase.status != CaseStatus.RESOLVED)
        return list(await self.session.scalars(query))

    async def list_for_queue(self, closed_since: datetime) -> list[SupportCase]:
        """Every open case, plus cases closed since the given time (the desk's snapshot)."""
        query = (
            select(SupportCase)
            .where(
                or_(
                    SupportCase.status != CaseStatus.RESOLVED,
                    SupportCase.closed_at >= closed_since,
                )
            )
            .order_by(SupportCase.created_at.desc())
        )
        return list(await self.session.scalars(query))

    async def list_for_account(self, account_id: str) -> list[SupportCase]:
        query = (
            select(SupportCase)
            .where(SupportCase.account_id == account_id)
            .order_by(SupportCase.created_at.desc())
        )
        return list(await self.session.scalars(query))

    async def open_case_for_conversation(self, conversation_id: str) -> SupportCase | None:
        """The case holding this conversation, if any. A resolved case no longer holds it."""
        query = (
            select(SupportCase)
            .join(CaseConversation)
            .where(
                CaseConversation.conversation_id == conversation_id,
                SupportCase.status != CaseStatus.RESOLVED,
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
                SupportCase.status != CaseStatus.RESOLVED,
            )
            .order_by(SupportCase.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(query)

    async def attach_conversation(self, case: SupportCase, conversation_id: str) -> None:
        if any(link.conversation_id == conversation_id for link in case.conversations):
            return
        case.conversations.append(CaseConversation(conversation_id=conversation_id))
        case.timeline.append(
            TimelineEvent(label="Customer wrote again in another chat", actor=AI_ASSISTANT)
        )
        await self.session.flush()

    async def add_held_message(
        self, case: SupportCase, conversation_id: str, content: str
    ) -> HeldMessage:
        message = HeldMessage(conversation_id=conversation_id, content=content)
        case.held_messages.append(message)
        case.timeline.append(TimelineEvent(label="Customer added a message", actor=AI_ASSISTANT))
        await self.session.flush()
        return message

    async def close(self, case: SupportCase, outcome: str, actor: str = AI_ASSISTANT) -> list[str]:
        """Resolve the case with its Case Outcome and return every linked conversation, so each
        held thread can be resumed."""
        if not case.is_open:
            raise CaseAlreadyClosedError(case.id)
        case.status = CaseStatus.RESOLVED
        case.outcome = outcome
        case.closed_at = utcnow()
        label = f"Resolved: {OUTCOME_LABELS.get(outcome, outcome)}"
        case.timeline.append(TimelineEvent(label=label, actor=actor))
        await self.session.flush()
        return [link.conversation_id for link in case.conversations]

    async def update(self, case: SupportCase, changes: CaseChanges, actor: str) -> list[str]:
        """Apply a Human Agent's changes. Returns the conversations to release if the case was
        just resolved (empty otherwise)."""
        released: list[str] = []
        if changes.assignee is not None or "assignee" in changes.clear:
            case.assignee = None if "assignee" in changes.clear else changes.assignee
            label = f"Assigned to {case.assignee}" if case.assignee else "Unassigned"
            case.timeline.append(TimelineEvent(label=label, actor=actor))
        if changes.priority_override is not None or "priority_override" in changes.clear:
            case.priority_override = (
                None if "priority_override" in changes.clear else changes.priority_override
            )
            label = (
                f"Urgency set to {case.priority_override.value}"
                if case.priority_override
                else "Urgency back to the Triage Rules"
            )
            case.timeline.append(TimelineEvent(label=label, actor=actor))
        if changes.resolution is not None and changes.status is None and not case.is_open:
            case.outcome = changes.resolution
        if changes.status is not None and changes.status != case.status:
            if changes.status == CaseStatus.RESOLVED:
                released = await self.close(case, changes.resolution or "other", actor)
            else:
                if not case.is_open:  # leaving Resolved reopens the case
                    case.reopened = True
                    case.closed_at = None
                case.status = changes.status
                case.timeline.append(
                    TimelineEvent(label=f"Status: {STATUS_LABELS[changes.status]}", actor=actor)
                )
        await self.session.flush()
        return released

    async def add_feedback(
        self, case: SupportCase, *, tags: list[str], note: str, author: str
    ) -> FeedbackNote:
        entry = FeedbackNote(tags=tags, note=note, author=author)
        case.feedback.append(entry)
        case.timeline.append(TimelineEvent(label="Feedback added", actor=author))
        await self.session.flush()
        return entry

    async def feedback_since(self, since: datetime) -> list[FeedbackNote]:
        query = (
            select(FeedbackNote)
            .where(FeedbackNote.created_at >= since)
            .order_by(FeedbackNote.created_at.desc())
        )
        return list(await self.session.scalars(query))
