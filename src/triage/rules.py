"""The Triage Rules: Urgency, queue and due date for a Support Case.

A port of the agent desk's src/lib/agent/triage.ts, so the widget's case card and the desk
always agree (see CONTEXT.md "Triage Rules"). A weighted scorecard: each rule that fires adds
points, and the total sets the Urgency. No AI. tests/fixtures/triage-golden.json, generated
from the desk's code, pins the two implementations together; keep them in step.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from src.triage.themes import ThemeMatch, is_information_request, match_themes

Category = Literal["Billing", "Meter reading", "Payments", "Supply", "Water quality", "Service"]
UrgencyCode = Literal["P1", "P2", "P3"]

SLA_DAYS: dict[str, int] = {"P1": 2, "P2": 10, "P3": 20}
THRESHOLDS = {"P1": 60, "P2": 30}
REPEAT_WINDOW = timedelta(days=30)

CATEGORY_BASE: dict[str, int] = {
    "Supply": 20,
    "Water quality": 20,
    "Billing": 10,
    "Payments": 10,
    "Meter reading": 5,
    "Service": 5,
}

ROUTE: dict[str, str] = {
    "Billing": "Billing specialists",
    "Payments": "Billing specialists",
    "Meter reading": "Metering",
    "Supply": "Field operations",
    "Water quality": "Field operations",
    "Service": "Customer relations",
}


@dataclass(frozen=True)
class TriageCase:
    """The facts about a case the rules read."""

    case_id: str
    account_id: str
    category: Category
    opened_at: datetime
    subject: str = ""
    description: str = ""
    vulnerable: bool = False
    disputed_amount: float | None = None
    transfers: int = 0
    reopened: bool = False
    source: Literal["direct", "assistant"] = "direct"
    priority_override: UrgencyCode | None = None


@dataclass(frozen=True)
class FiredRule:
    id: str
    label: str
    points: int


@dataclass(frozen=True)
class Triage:
    score: int
    computed: UrgencyCode  # from the rules, before any manual override
    priority: UrgencyCode  # what is used: the override if set, otherwise the rules
    overridden: bool
    rules: list[FiredRule]
    queue: str
    route_reason: str
    sla_days: int
    due_at: datetime
    themes: list[ThemeMatch] = field(default_factory=list)
    information_request: bool = False
    repeat_contact: bool = False


def _js_round(value: float) -> int:
    """JavaScript's Math.round (halves go up), not Python's banker's rounding."""
    return math.floor(value + 0.5)


def repeat_contact_index(cases: list[TriageCase]) -> dict[str, int]:
    """For each case, how many other cases the same account opened in the 30 days before it."""
    by_account: dict[str, list[datetime]] = {}
    for c in cases:
        by_account.setdefault(c.account_id, []).append(c.opened_at)
    return {
        c.case_id: sum(
            1
            for t in by_account[c.account_id]
            if t < c.opened_at and c.opened_at - t <= REPEAT_WINDOW
        )
        for c in cases
    }


def triage_case(c: TriageCase, earlier_contacts: int = 0) -> Triage:
    text = f"{c.subject}. {c.description}"
    themes = match_themes(text)
    theme_ids = {t.id for t in themes}
    rules: list[FiredRule] = []

    def add(id: str, label: str, points: int) -> None:
        rules.append(FiredRule(id, label, points))

    add("category", f"{c.category} complaint", CATEGORY_BASE[c.category])
    if "no_supply" in theme_ids:
        add("no_supply", "Customer reports no supply", 40)
    if "water_quality" in theme_ids:
        add("health", "Possible health risk (water quality)", 40)
    if c.vulnerable:
        add("vulnerable", "Customer is on the Priority Services Register", 35)
    if "regulator" in theme_ids:
        add("regulator", "Mentions the regulator or ombudsman", 25)

    repeat_contact = c.reopened or earlier_contacts > 0 or "chasing" in theme_ids
    if c.reopened:
        add("reopened", "Case was reopened", 20)
    elif earlier_contacts > 0:
        plural = "s" if earlier_contacts > 1 else ""
        add("repeat", f"Repeat contact: {earlier_contacts} other case{plural} in 30 days", 20)
    elif "chasing" in theme_ids:
        add("chasing", "Customer is chasing an earlier contact", 15)

    if c.disputed_amount is not None and c.disputed_amount >= 500:
        add("amount", f"£{_js_round(c.disputed_amount)} in dispute", 25)
    elif c.disputed_amount is not None and c.disputed_amount >= 150:
        add("amount", f"£{_js_round(c.disputed_amount)} in dispute", 15)

    if c.transfers > 0:
        add("transfers", f"Already moved between teams {c.transfers}×", 10)
    if c.source == "assistant":
        add("assistant", "Asked for a person after using the assistant", 10)

    # Not for cases the assistant already tried and couldn't settle.
    information_request = (
        c.source != "assistant"
        and is_information_request(text)
        and "no_supply" not in theme_ids
        and "water_quality" not in theme_ids
    )
    if information_request:
        add("information", "Information request the assistant can answer", -10)

    score = sum(rule.points for rule in rules)
    computed: UrgencyCode = (
        "P1" if score >= THRESHOLDS["P1"] else "P2" if score >= THRESHOLDS["P2"] else "P3"
    )
    priority = c.priority_override or computed
    sla_days = SLA_DAYS[priority]

    queue = ROUTE[c.category]
    route_reason = f"{c.category} cases go to {queue}"
    if c.category == "Billing" and "estimated_reading" in theme_ids:
        route_reason = (
            "Billing case about an estimated reading: Billing specialists, "
            "with the meter history attached"
        )
    if "regulator" in theme_ids or (c.reopened and c.transfers >= 2):
        queue = "Customer relations"
        route_reason = (
            "Mentions the regulator or ombudsman, so it goes straight to Customer relations"
            if "regulator" in theme_ids
            else "Reopened after two or more transfers, so one team owns it end to end"
        )

    return Triage(
        score=score,
        computed=computed,
        priority=priority,
        overridden=c.priority_override is not None and c.priority_override != computed,
        rules=rules,
        queue=queue,
        route_reason=route_reason,
        sla_days=sla_days,
        due_at=c.opened_at + timedelta(days=sla_days),
        themes=themes,
        information_request=information_request,
        repeat_contact=repeat_contact,
    )


def triage_all(cases: list[TriageCase]) -> dict[str, Triage]:
    repeats = repeat_contact_index(cases)
    return {c.case_id: triage_case(c, repeats[c.case_id]) for c in cases}
