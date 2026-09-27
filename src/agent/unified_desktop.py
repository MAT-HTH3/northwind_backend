"""The Unified Desktop: hands a Hand-off request to a Human Agent (ADR 0001, ADR 0002).

Joins the customer's open case on the same topic, or opens a new Support Case with the Urgency,
queue and due date from the Triage Rules (the same rules the agent desk runs) and a summary for
the Human Agent. Saves any meter reading, then
replies with fixed text and the receipt and case cards.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import get_args
from zoneinfo import ZoneInfo

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agent.categories import FALLBACK, Category, team_for
from src.agent.transcript import recent_messages, transcript_text
from src.history import UnifiedCustomerHistory
from src.models import CustomerReading, Service, SupportCase, Urgency
from src.repositories import ReadingRepository, SupportCaseRepository
from src.schemas.cards import MeterReadingReceipt, SupportCaseCard
from src.triage import Triage, TriageCase, triage_all

logger = logging.getLogger(__name__)

UI_CARDS = "ui_cards"  # AIMessage.additional_kwargs key; #20 streams these as tool-call events
TRANSCRIPT_WINDOW = 20
UK = ZoneInfo("Europe/London")  # the customer's calendar, for "reply by" dates
NEW_CASE = "new"

SUMMARY_PROMPT = """\
Write a case summary for the Northwind Human Agent who will pick up this conversation, so the \
customer never has to explain it again. Two to four plain sentences, no greeting, no headings. \
Say what the customer wants, the relevant facts from their history (bill amounts, estimated \
reads, meter readings they gave, earlier contacts and cases), and anything already tried. \
Handed off as: {category}.

Unified Customer History (JSON):
{history}
"""


@dataclass(frozen=True)
class HandOff:
    case: SupportCase
    joined: bool  # True when the conversation joined an already-open case
    reading: CustomerReading | None


async def hand_off(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    llm: BaseChatModel,
    account_id: str,
    conversation_id: str,
    category: str | None,
    meter_reading: dict | None,
    messages: list[AnyMessage],
    history: UnifiedCustomerHistory,
    now: datetime,
) -> HandOff:
    category = category if category in get_args(Category) else FALLBACK
    today = now.astimezone(UK).date()

    async with session_factory() as session:
        cases = SupportCaseRepository(session)
        case = await cases.open_case_for_category(account_id, category)
        joined = case is not None
        if case is not None:
            await cases.attach_conversation(case, conversation_id)
        else:
            triage = triage_new_case(account_id, category, messages, history, now)
            case = await cases.create(
                account_id=account_id,
                conversation_id=conversation_id,
                category=category,
                priority=Urgency(triage.priority),
                sla_days=triage.sla_days,
                queue=triage.queue,
                expected_response_by=triage.due_at.astimezone(UK).date(),
                summary=await summarise(llm, category, messages, history),
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
            )
        await session.commit()
    return HandOff(case=case, joined=joined, reading=reading)


def triage_new_case(
    account_id: str,
    category: Category,
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
        description=customer_words(messages),
        vulnerable=history.customer.vulnerable,
        source="assistant",
    )
    return triage_all([*earlier, new])[NEW_CASE]


def customer_words(messages: list[AnyMessage]) -> str:
    """The customer's own messages, verbatim: the case description the Triage Rules scan."""
    return "\n".join(m.text for m in messages if isinstance(m, HumanMessage))


async def summarise(
    llm: BaseChatModel,
    category: Category,
    messages: list[AnyMessage],
    history: UnifiedCustomerHistory,
) -> str:
    """Gemini writes the summary; if it fails, a plain one is used so the hand-off still happens."""
    prompt = SystemMessage(
        SUMMARY_PROMPT.format(category=category, history=history.model_dump_json())
    )
    transcript = transcript_text(recent_messages(messages, TRANSCRIPT_WINDOW))
    try:
        reply = await llm.ainvoke([prompt, HumanMessage(f"Conversation so far:\n{transcript}")])
        if reply.text.strip():
            return reply.text.strip()
    except Exception:
        logger.exception("Case summary LLM failed; using the fallback summary")
    return fallback_summary(category, messages, history)


def fallback_summary(
    category: str, messages: list[AnyMessage], history: UnifiedCustomerHistory
) -> str:
    last = next((m.text for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    name = f"{history.customer.first_name} {history.customer.last_name}"
    return (
        f"{name} ({history.customer.region}) was handed off as {category}. Last message: {last!r}"
    )


def reply(result: HandOff) -> AIMessage:
    """Fixed customer text (no LLM) plus the cards, receipt first."""
    case, team = result.case, team_for(result.case.queue)
    due = _long_date(case.expected_response_by)
    parts, cards = [], []

    if result.reading is not None:
        r = result.reading
        parts.append(
            f"Thanks, I've recorded your {r.service.value} reading of **{r.value:,} {r.unit}**. "
            f"A billing specialist will check it and send you a corrected bill if one is needed."
        )
        cards.append(
            {
                "name": "submit_meter_reading",
                "args": {"service": r.service.value, "value": r.value},
                "result": MeterReadingReceipt(
                    reading_id=r.id,
                    service=r.service.value,
                    value=r.value,
                    unit=r.unit,
                    read_date=r.read_date,
                    status=r.status.value,
                ).model_dump(mode="json"),
            }
        )

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
    cards.append(
        {
            "name": "create_support_case",
            "args": {},
            "result": SupportCaseCard(
                case_id=case.id,
                category=case.category,
                priority=case.priority.value,
                sla_days=case.sla_days,
                queue=case.queue,
                expected_response_by=case.expected_response_by,
                summary=case.summary,
            ).model_dump(mode="json"),
        }
    )
    return AIMessage("\n\n".join(parts), additional_kwargs={UI_CARDS: cards})


def _long_date(value: date) -> str:
    return f"{value:%A} {value.day} {value:%B}"  # "Tuesday 6 October"
