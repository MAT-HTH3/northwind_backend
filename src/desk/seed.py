"""The agent desk's invented demo data: loaded at start-up and by "Reset demo data".

desk-seed.json.gz is exported from the frontend's seed generator
(northwind-frontend: npx tsx scripts/export-desk-seed.ts). Every date-time is shifted by
(now - generated_at), so the data never ages. Urgency, SLA and queue come from our Triage Rules
port, exactly as the desk will work them out.
"""

import gzip
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agent.unified_desktop import UK
from src.models import (
    CaseConversation,
    CaseSource,
    CaseStatus,
    Channel,
    Conversation,
    CustomerReading,
    FeedbackNote,
    HeldMessage,
    ResolutionAnswer,
    SeedExtra,
    SupportCase,
    TimelineEvent,
    Urgency,
)
from src.models.types import utcnow
from src.triage import TriageCase, triage_all

logger = logging.getLogger(__name__)

SEED_FILE = Path(__file__).parent / "desk-seed.json.gz"

# Children before parents, so foreign keys hold while clearing.
TABLES = [
    FeedbackNote,
    TimelineEvent,
    HeldMessage,
    CaseConversation,
    CustomerReading,
    ResolutionAnswer,
    Conversation,
    SeedExtra,
    SupportCase,
]


def read_seed(path: Path = SEED_FILE) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


async def seed_if_empty(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    """Loads the seed unless it's already there. Returns whether it loaded."""
    async with session_factory() as session:
        if await session.scalar(select(SeedExtra.record_id).limit(1)) is not None:
            return False
    await load_seed(session_factory)
    return True


async def reset_demo(
    session_factory: async_sessionmaker[AsyncSession], checkpointer: BaseCheckpointSaver
) -> None:
    """Back to the starting state: all chat memory and every record removed, seed reloaded.

    Chat memory goes first, and the records are replaced in one transaction, so a failure part
    way never leaves the desk empty.
    """
    async with session_factory() as session:
        threads = set(await session.scalars(select(Conversation.id)))
        threads |= set(await session.scalars(select(CaseConversation.conversation_id)))
    for thread_id in threads:
        await checkpointer.adelete_thread(thread_id)
    async with session_factory() as session:
        for table in TABLES:
            await session.execute(delete(table))
        await _add_seed(session, read_seed(), utcnow())
        await session.commit()


async def load_seed(
    session_factory: async_sessionmaker[AsyncSession],
    data: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> None:
    async with session_factory() as session:
        await _add_seed(session, data or read_seed(), now or utcnow())
        await session.commit()


async def _add_seed(session: AsyncSession, data: dict[str, Any], now: datetime) -> None:
    shift = now - datetime.fromisoformat(data["generated_at"])

    def at(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) + shift if value else None

    raw_cases = [entry["case"] for entry in data["cases"]]
    triage = triage_all(
        [
            TriageCase(
                case_id=c["case_id"],
                account_id=c["account_id"],
                category=c["category"],
                opened_at=at(c["opened_at"]),
                subject=c["subject"],
                description=c["description"],
                vulnerable=c["vulnerable"],
                disputed_amount=c["disputed_amount"],
                transfers=c["transfers"],
                reopened=c["reopened"],
                source=c["source"],
                priority_override=c["priority_override"],
            )
            for c in raw_cases
        ]
    )

    for entry in data["cases"]:
        c, t = entry["case"], triage[entry["case"]["case_id"]]
        session.add(
            SupportCase(
                id=c["case_id"],
                account_id=c["account_id"],
                category=c["category"],
                priority=Urgency(t.priority),
                sla_days=t.sla_days,
                queue=t.queue,
                expected_response_by=t.due_at.astimezone(UK).date(),
                summary=c["description"],
                status=CaseStatus(c["status"]),
                outcome=c["resolution"],
                created_at=at(c["opened_at"]),
                closed_at=at(c["closed_at"]),
                customer_name=c["customer_name"],
                region=c["region"],
                vulnerable=c["vulnerable"],
                channel=Channel(c["channel"]),
                source=CaseSource(c["source"]),
                subject=c["subject"],
                description=c["description"],
                disputed_amount=c["disputed_amount"],
                transfers=c["transfers"],
                reopened=c["reopened"],
                assignee=c["assignee"],
                priority_override=Urgency(c["priority_override"])
                if c["priority_override"]
                else None,
                timeline=[
                    TimelineEvent(at=at(e["at"]), label=e["label"], actor=e["actor"])
                    for e in entry["timeline"]
                ],
            )
        )
        session.add(
            SeedExtra(
                kind="case",
                record_id=c["case_id"],
                transcript=_shift_transcript(entry["transcript"], at),
                account=entry["account"],
            )
        )
    await session.flush()  # cases exist before anything points at them

    for entry in data["conversations"]:
        conv = entry["conversation"]
        started = at(conv["started_at"])
        session.add(
            Conversation(
                id=conv["conversation_id"],
                account_id=conv["account_id"],
                customer_name=conv["customer_name"],
                started_at=started,
                updated_at=started,
                topic=conv["topic"],
                case_id=conv["case_id"],
            )
        )
        if conv["case_id"]:
            session.add(
                CaseConversation(
                    case_id=conv["case_id"],
                    conversation_id=conv["conversation_id"],
                    linked_at=started,
                )
            )
        if conv["resolved"]:
            session.add(
                ResolutionAnswer(
                    conversation_id=conv["conversation_id"],
                    account_id=conv["account_id"],
                    resolved=True,
                    answered_at=started,
                )
            )
        session.add(
            SeedExtra(
                kind="conversation",
                record_id=conv["conversation_id"],
                transcript=_shift_transcript(entry["transcript"], at),
                account=None,
            )
        )

    for note in data["feedback"]:
        session.add(
            FeedbackNote(
                case_id=note["case_id"],
                tags=note["tags"],
                note=note["note"],
                author=note["author"],
                created_at=at(note["at"]),
            )
        )
    logger.info(
        "Loaded the desk seed: %d cases, %d conversations, %d feedback notes",
        len(data["cases"]),
        len(data["conversations"]),
        len(data["feedback"]),
    )


def _shift_transcript(transcript: list[dict] | None, at) -> list[dict] | None:
    if transcript is None:
        return None
    return [entry | {"at": at(entry["at"]).isoformat()} for entry in transcript]
