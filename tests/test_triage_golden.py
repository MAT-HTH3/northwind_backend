"""The Python Triage Rules must decide exactly what the desk's triage.ts decides.

tests/fixtures/triage-golden.json is generated from the desk's code
(northwind-frontend: npx tsx scripts/export-triage-golden.ts).
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest

from src.triage import TriageCase, triage_all

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "triage-golden.json").read_text())


def to_case(raw: dict) -> TriageCase:
    return TriageCase(
        case_id=raw["case_id"],
        account_id=raw["account_id"],
        category=raw["category"],
        opened_at=datetime.fromisoformat(raw["opened_at"]),
        subject=raw["subject"],
        description=raw["description"],
        vulnerable=raw["vulnerable"],
        disputed_amount=raw["disputed_amount"],
        transfers=raw["transfers"],
        reopened=raw["reopened"],
        source=raw["source"],
        priority_override=raw["priority_override"],
    )


RESULTS = triage_all([to_case(entry["input"]) for entry in GOLDEN])


@pytest.mark.parametrize("entry", GOLDEN, ids=lambda e: e["input"]["case_id"])
def test_matches_the_desk(entry):
    got = RESULTS[entry["input"]["case_id"]]
    expected = entry["expected"]

    assert {
        "score": got.score,
        "computed": got.computed,
        "priority": got.priority,
        "overridden": got.overridden,
        "rules": [asdict(rule) for rule in got.rules],
        "queue": got.queue,
        "route_reason": got.route_reason,
        "sla_days": got.sla_days,
        "due_at": got.due_at,
        "themes": [{"id": t.id, "phrase": t.phrase} for t in got.themes],
        "information_request": got.information_request,
        "repeat_contact": got.repeat_contact,
    } == expected | {"due_at": datetime.fromisoformat(expected["due_at"])}


def test_the_golden_file_covers_every_rule():
    fired = {rule["id"] for entry in GOLDEN for rule in entry["expected"]["rules"]}
    assert fired == {
        "category", "no_supply", "health", "vulnerable", "regulator", "reopened", "repeat",
        "chasing", "amount", "transfers", "assistant", "information",
    }  # fmt: skip
