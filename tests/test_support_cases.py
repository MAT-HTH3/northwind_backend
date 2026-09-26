from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text

from src.models import CaseStatus, Priority, SupportCase
from src.repositories import CaseAlreadyClosedError, IdSpaceExhaustedError, SupportCaseRepository

ACCOUNT = "ACC-372876"


def case_fields(**overrides):
    fields = dict(
        account_id=ACCOUNT,
        conversation_id="conv-1",
        category="Meter reading review",
        priority=Priority.MID,
        sla_days=10,
        queue="Billing specialists",
        expected_response_by=date(2026, 10, 6),
        summary="Customer submitted a reading of 48,213 kWh.",
    )
    return fields | overrides


def sequence(*ids: str):
    it = iter(ids)
    return lambda: next(it)


async def test_case_id_retries_past_a_collision(session):
    repo = SupportCaseRepository(
        session, id_factory=sequence("NW-100001", "NW-100001", "NW-100002")
    )
    first = await repo.create(**case_fields())
    second = await repo.create(**case_fields(conversation_id="conv-2"))

    assert (first.id, second.id) == ("NW-100001", "NW-100002")


async def test_case_id_gives_up_when_every_candidate_is_taken(session):
    repo = SupportCaseRepository(session, id_factory=lambda: "NW-100001")
    await repo.create(**case_fields())

    with pytest.raises(IdSpaceExhaustedError):
        await repo.create(**case_fields(conversation_id="conv-2"))


async def test_second_conversation_joins_the_open_case(session):
    repo = SupportCaseRepository(session)
    case = await repo.create(**case_fields(conversation_id="conv-1"))

    await repo.attach_conversation(case, "conv-2")
    await repo.attach_conversation(case, "conv-2")  # idempotent

    assert [link.conversation_id for link in case.conversations] == ["conv-1", "conv-2"]
    assert (await repo.open_case_for_conversation("conv-1")).id == case.id
    assert (await repo.open_case_for_conversation("conv-2")).id == case.id


async def test_closing_releases_every_linked_conversation(session):
    repo = SupportCaseRepository(session)
    case = await repo.create(**case_fields(conversation_id="conv-1"))
    await repo.attach_conversation(case, "conv-2")

    released = await repo.close(case, "Reading verified, corrected bill of £132.01 issued.")

    assert released == ["conv-1", "conv-2"]
    assert case.status == CaseStatus.CLOSED and case.closed_at is not None
    assert await repo.open_case_for_conversation("conv-1") is None
    assert await repo.open_case_for_conversation("conv-2") is None
    with pytest.raises(CaseAlreadyClosedError):
        await repo.close(case, "again")


async def test_a_closed_conversation_can_be_held_by_a_new_case(session):
    repo = SupportCaseRepository(session)
    old = await repo.create(**case_fields(conversation_id="conv-1"))
    await repo.close(old, "Done.")

    new = await repo.create(**case_fields(conversation_id="conv-1", category="Meter fault"))

    assert (await repo.open_case_for_conversation("conv-1")).id == new.id


async def test_open_case_for_category_matches_account_category_and_status(session):
    repo = SupportCaseRepository(session)
    readings = await repo.create(**case_fields())
    await repo.create(**case_fields(category="Supply fault - repair needed"))
    await repo.create(**case_fields(account_id="ACC-000001"))
    closed = await repo.create(**case_fields(category="Meter fault"))
    await repo.close(closed, "Done.")

    assert (await repo.open_case_for_category(ACCOUNT, "Meter reading review")).id == readings.id
    assert await repo.open_case_for_category(ACCOUNT, "Meter fault") is None


async def test_timestamps_come_back_timezone_aware_from_sqlite(session):
    repo = SupportCaseRepository(session)
    case = await repo.create(**case_fields())
    await session.commit()
    session.expunge_all()

    reloaded = await session.scalar(select(SupportCase).where(SupportCase.id == case.id))

    assert reloaded.created_at.tzinfo is UTC


async def test_naive_timestamps_are_rejected(session):
    repo = SupportCaseRepository(session)
    case = await repo.create(**case_fields())
    case.closed_at = datetime(2026, 9, 28, 9, 0)  # no tzinfo

    with pytest.raises(Exception, match="timezone-aware"):
        await session.flush()


async def test_unknown_priority_is_rejected_by_the_database(session):
    await SupportCaseRepository(session).create(**case_fields())

    with pytest.raises(Exception, match="CHECK constraint"):
        await session.execute(text("UPDATE support_cases SET priority = 'P1'"))
