from datetime import date

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.agent.graph import build_graph
from src.agent.state import history_from
from src.agent.turns import thread_config, turn_input
from src.history import UnknownCustomerError, build_history
from src.legacy import get_legacy_systems
from src.models import Priority, Service
from src.repositories import ReadingRepository, SupportCaseRepository
from tests.fakes import fake_context

ACCOUNT = "ACC-DEMO01"


async def history(session_factory):
    return await build_history(ACCOUNT, get_legacy_systems(), session_factory)


async def test_legacy_formats_are_normalised(session_factory):
    h = await history(session_factory)
    [current, previous] = h.billing.bills

    assert (current.period_start, current.period_end, current.due_date) == (
        date(2026, 8, 14),
        date(2026, 9, 13),
        date(2026, 10, 5),
    )
    assert (current.amount_due, previous.amount_due) == (169.6, 118.39)
    assert current.reading_type == "estimated" and not current.paid
    units = current.lines[0]
    assert (units.label, units.quantity, units.unit, units.unit_rate, units.amount) == (
        "Electricity used",
        486,
        "kWh",
        0.2486,
        120.82,
    )
    assert h.billing.payment_method == "Direct Debit"
    water = next(m for m in h.meters if m.service == "water")
    assert (water.unit, water.reads[-1].value) == ("m³", 612.4)  # litres in Metering
    assert h.past_cases[0].reference == "CT-88123"
    assert h.past_cases[0].category == "Query about an estimated bill"
    assert h.past_cases[0].times_reopened == 1


async def test_usage_history_comes_from_meter_reads(session_factory):
    h = await history(session_factory)

    assert [(u.month, u.electricity_kwh, u.water_m3, u.estimated) for u in h.usage_history] == [
        ("2026-04", 352, 8.8, False),
        ("2026-05", 331, 9.1, False),
        ("2026-06", 330, 9.0, False),
        ("2026-07", 340, 9.4, True),
        ("2026-08", 289, 9.3, True),
        ("2026-09", 486, 9.2, True),
    ]
    assert {m.last_actual_read_on for m in h.meters} == {date(2026, 6, 12)}


async def test_our_support_cases_and_readings_are_included(session_factory):
    async with session_factory() as session:
        cases = SupportCaseRepository(session)
        fields = dict(
            account_id=ACCOUNT,
            priority=Priority.MID,
            sla_days=10,
            queue="Billing specialists",
            expected_response_by=date(2026, 10, 6),
            summary="…",
        )
        closed = await cases.create(conversation_id="c1", category="Meter fault", **fields)
        await cases.close(closed, "Meter replaced.")
        open_ = await cases.create(conversation_id="c2", category="Meter reading review", **fields)
        await ReadingRepository(session).create(
            account_id=ACCOUNT,
            case_id=open_.id,
            conversation_id="c2",
            service=Service.ELECTRICITY,
            value=48213,
            read_date=date(2026, 9, 26),
        )
        await session.commit()

    h = await history(session_factory)

    by_id = {c.case_id: c for c in h.support_cases}
    assert (by_id[closed.id].status, by_id[closed.id].outcome) == ("closed", "Meter replaced.")
    assert (by_id[open_.id].status, by_id[open_.id].outcome) == ("open", None)
    [reading] = h.submitted_readings
    assert (reading.value, reading.unit, reading.status, reading.case_id) == (
        48213,
        "kWh",
        "awaiting_review",
        open_.id,
    )


async def test_unknown_customer_raises(session_factory):
    with pytest.raises(UnknownCustomerError):
        await build_history("ACC-000000", get_legacy_systems(), session_factory)


async def test_the_analyzer_puts_a_reloadable_history_in_state(session_factory, tmp_path):
    context = fake_context(session_factory)
    path = str(tmp_path / "checkpoints.db")
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        graph = build_graph(saver)
        payload = await turn_input(graph, conversation_id="c1", account_id=ACCOUNT, message="Hi")
        await graph.ainvoke(payload, thread_config("c1"), context=context)

    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        state = (await build_graph(saver).aget_state(thread_config("c1"))).values

    assert history_from(state).billing.bills[0].amount_due == 169.6
