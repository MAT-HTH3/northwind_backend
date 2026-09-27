"""Turns stored records into the agent desk's shapes."""

from src.agent.bill_breakdown import BillNotFoundError, build_bill_breakdown
from src.history import UnifiedCustomerHistory
from src.models import Conversation, FeedbackNote, SupportCase
from src.repositories import ConversationOutcome
from src.schemas.agent import (
    AccountCustomer,
    AccountSnapshot,
    AgentCase,
    AssistantConversation,
    FeedbackEntry,
    MeterRead,
    TimelineEntry,
)

READ_TYPES = {"customer": "customer", "agent": "actual", "estimate": "estimated"}


def agent_case(case: SupportCase) -> AgentCase:
    return AgentCase(
        case_id=case.id,
        account_id=case.account_id,
        customer_name=case.customer_name,
        region=case.region,
        vulnerable=case.vulnerable,
        channel=case.channel.value,
        category=case.category,
        subject=case.subject,
        description=case.description,
        opened_at=case.created_at,
        closed_at=case.closed_at,
        status=case.status.value,
        assignee=case.assignee,
        resolution=case.outcome,
        disputed_amount=case.disputed_amount,
        transfers=case.transfers,
        reopened=case.reopened,
        priority_override=case.priority_override.value if case.priority_override else None,
        source=case.source.value,
    )


def assistant_conversation(
    conversation: Conversation, outcome: ConversationOutcome
) -> AssistantConversation:
    return AssistantConversation(
        conversation_id=conversation.id,
        account_id=conversation.account_id,
        customer_name=conversation.customer_name,
        started_at=conversation.started_at,
        resolved=outcome == ConversationOutcome.AUTO_RESOLVED,
        topic=conversation.topic or "Chat",
        case_id=conversation.case_id,
    )


def feedback_entry(note: FeedbackNote) -> FeedbackEntry:
    return FeedbackEntry(tags=note.tags, note=note.note, author=note.author, at=note.created_at)


def timeline(case: SupportCase) -> list[TimelineEntry]:
    return [TimelineEntry(at=e.at, label=e.label, actor=e.actor) for e in case.timeline]


def account_snapshot(history: UnifiedCustomerHistory) -> AccountSnapshot:
    """One screen instead of four: CRM, Legacy Billing and Metering together."""
    c = history.customer
    try:
        bill = build_bill_breakdown(history)
    except BillNotFoundError:
        bill = None
    reads = [
        MeterRead(date=r.read_on, value=r.value, unit=m.unit, type=READ_TYPES[r.source])
        for m in history.meters
        for r in m.reads
    ]
    reads += [
        MeterRead(date=r.read_date, value=r.value, unit=r.unit, type="customer")
        for r in history.submitted_readings
    ]
    return AccountSnapshot(
        customer=AccountCustomer(
            account_id=c.account_id,
            first_name=c.first_name,
            last_name=c.last_name,
            region=c.region,
            services=c.services,
            vulnerable=c.vulnerable,
            phone=c.phone,
            email=c.email,
        ),
        bill=bill,
        meter_reads=sorted(reads, key=lambda r: r.date, reverse=True),
    )
