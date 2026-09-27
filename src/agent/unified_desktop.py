"""The Unified Desktop: hands a Hand-off request to a Human Agent (ADR 0001, ADR 0002).

Joins the customer's open case on the same topic, or opens a new Support Case with the Urgency,
queue and due date from the Triage Rules (the same rules the agent desk runs) and a summary
written by code (ADR 0003). Saves any meter reading, then replies with fixed text and the
receipt and case cards.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import get_args
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agent.cards import UI_CARDS, case_card, receipt_card
from src.agent.categories import FALLBACK, Category, subject_for, team_for
from src.agent.transcript import written_by_code
from src.history import UnifiedCustomerHistory
from src.models import CustomerReading, ReadingStatus, Service, SupportCase, Urgency
from src.repositories import ReadingRepository, SupportCaseRepository
from src.triage import Triage, TriageCase, triage_all

UK = ZoneInfo("Europe/London")  # the customer's calendar, for "reply by" dates
NEW_CASE = "new"


@dataclass(frozen=True)
class HandOff:
    case: SupportCase
    joined: bool  # True when the conversation joined an already-open case
    reading: CustomerReading | None


async def hand_off(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    account_id: str,
    conversation_id: str,
    category: str | None,
    subject: str | None,
    disputed_amount: float | None,
    meter_reading: dict | None,
    messages: list[AnyMessage],
    history: UnifiedCustomerHistory,
    now: datetime,
) -> HandOff:
    category = category if category in get_args(Category) else FALLBACK
    subject = subject_for(category, subject)
    today = now.astimezone(UK).date()

    async with session_factory() as session:
        cases = SupportCaseRepository(session)
        case = await cases.open_case_for_category(account_id, category)
        joined = case is not None
        if case is not None:
            await cases.attach_conversation(case, conversation_id)
        else:
            triage = triage_new_case(
                account_id, category, subject, disputed_amount, messages, history, now
            )
            case = await cases.create(
                account_id=account_id,
                conversation_id=conversation_id,
                category=category,
                priority=Urgency(triage.priority),
                sla_days=triage.sla_days,
                queue=triage.queue,
                expected_response_by=triage.due_at.astimezone(UK).date(),
                summary=case_summary(subject, meter_reading, messages, history),
            )
        reading = None
        if meter_reading:
            reading = await ReadingRepository(session).create(
                account_id=account_id,
                case_id=case.id,
                conversation_id=conversation_id,
                service=Service(meter_reading["service"]),
                value=meter_reading["value"],
                read_date=today,
                status=ReadingStatus.NEEDS_REVIEW,
            )
        await session.commit()
    return HandOff(case=case, joined=joined, reading=reading)


def triage_new_case(
    account_id: str,
    category: Category,
    subject: str,
    disputed_amount: float | None,
    messages: list[AnyMessage],
    history: UnifiedCustomerHistory,
    now: datetime,
) -> Triage:
    """Runs the Triage Rules on the case about to open, with the customer's earlier Support
    Cases counted as repeat contacts, exactly as the desk will see it."""
    earlier = [
        TriageCase(
            case_id=c.case_id, account_id=account_id, category=FALLBACK, opened_at=c.opened_at
        )
        for c in history.support_cases
    ]
    new = TriageCase(
        case_id=NEW_CASE,
        account_id=account_id,
        category=category,
        opened_at=now,
        subject=subject,
        description=customer_words(messages),
        disputed_amount=disputed_amount,
        vulnerable=history.customer.vulnerable,
        source="assistant",
    )
    return triage_all([*earlier, new])[NEW_CASE]


def customer_words(messages: list[AnyMessage]) -> str:
    """The customer's own messages, verbatim: the case description the Triage Rules scan."""
    return "\n".join(m.text for m in messages if isinstance(m, HumanMessage))


def case_summary(
    subject: str,
    reading: dict | None,
    messages: list[AnyMessage],
    history: UnifiedCustomerHistory,
) -> str:
    """The summary for the Human Agent, written by code from the case facts (ADR 0003)."""
    last = next((m.text for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    parts = [f"{subject}, raised in chat. The customer said: “{last}”."]
    if reading:
        unit = "kWh" if reading["service"] == "electricity" else "m³"
        parts.append(f"Meter reading given: {reading['value']:,} {unit} ({reading['service']}).")
    if history.billing and history.billing.bills:
        bill = history.billing.bills[0]
        parts.append(
            f"Latest bill {bill.bill_id}: £{bill.amount_due:,.2f}, {bill.reading_type} reading, "
            f"due {bill.due_date:%-d %B}."
        )
    for past in [c for c in history.past_cases if c.times_reopened][:1]:
        parts.append(
            f"Earlier case {past.reference}: {past.category}, {past.status}, "
            f"reopened {past.times_reopened}×."
        )
    for ours in history.support_cases[:1]:
        parts.append(f"Previous Support Case {ours.case_id}: {ours.category}, {ours.status}.")
    return " ".join(parts)


def reply(result: HandOff) -> AIMessage:
    """Fixed customer text (no LLM) plus the cards, receipt first."""
    case, team = result.case, team_for(result.case.queue)
    due = _long_date(case.expected_response_by)
    parts, cards = [], []

    if result.reading is not None:
        r = result.reading
        parts.append(
            f"Thanks for your {r.service.value} reading of **{r.value:,} {r.unit}**. It doesn't "
            f"match what we'd expect from your meter, so a person needs to check it before it "
            f"changes your bill."
        )
        cards.append(receipt_card(r, revised_amount_due=None))

    if result.joined:
        parts.append(
            f"I've added this to your open case **{case.id}**, so our {team} will see it. "
            f"They'll reply by **{due}**."
        )
    else:
        parts.append(
            f"I've passed this to our {team} with our conversation attached, so you won't "
            f"need to explain it again. Your case number is **{case.id}** and they'll reply by "
            f"**{due}**."
        )
    cards.append(case_card(case))
    return written_by_code("\n\n".join(parts), **{UI_CARDS: cards})


def _long_date(value: date) -> str:
    return f"{value:%A} {value.day} {value:%B}"  # "Tuesday 6 October"
