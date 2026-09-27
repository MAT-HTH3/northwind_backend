"""Case Status: answers "what's happening with my case?" with a reply written by code.

The model can't see cases (ADR 0003), so this route never calls it. It reads the Unified
Customer History: our open Support Cases first, then the latest resolved one with its Case
Outcome, then the latest legacy CaseTrack case.
"""

from datetime import date

from langchain_core.messages import AIMessage

from src.agent.categories import team_for
from src.agent.transcript import written_by_code
from src.history import UnifiedCustomerHistory

MAX_OPEN = 3

# Case Outcome (the desk's resolution codes) in the customer's words.
OUTCOME_PHRASES = {
    "information_only": "we gave you the information you needed",
    "explained_bill": "we explained your bill",
    "bill_corrected": "we corrected your bill",
    "refund_issued": "we issued a refund",
    "field_visit": "one of our engineers visited",
    "other": "our team resolved it",
}


def case_status_reply(history: UnifiedCustomerHistory) -> AIMessage:
    return written_by_code(case_status_text(history))


def case_status_text(history: UnifiedCustomerHistory) -> str:
    open_cases = [c for c in history.support_cases if c.status == "open"]
    if open_cases:
        lines = [
            f"Your case **{c.case_id}** is with our {team_for(c.queue)}. They'll reply by "
            f"**{_long_date(c.expected_response_by)}**."
            for c in open_cases[:MAX_OPEN]
        ]
        return "\n\n".join(lines)

    resolved = next((c for c in history.support_cases if c.status == "closed"), None)
    if resolved is not None:
        outcome = OUTCOME_PHRASES.get(resolved.outcome or "", "our team closed it")
        when = f" on **{_long_date(resolved.closed_at.date())}**" if resolved.closed_at else ""
        return f"Your case **{resolved.case_id}** was resolved{when}: {outcome}."

    legacy = history.past_cases[0] if history.past_cases else None  # newest first
    if legacy is not None:
        state = (
            f"was closed on **{_long_date(legacy.closed_on)}**"
            if legacy.status == "closed" and legacy.closed_on
            else "is still open with our team"
        )
        return (
            f"I can't see an open case for you. Your most recent one, **{legacy.reference}** "
            f"({legacy.category.lower()}), {state}. If you need more help, I can put you through "
            f"to a person."
        )

    return "I can't see any cases for you. If you'd like, I can put you through to a person."


def _long_date(value: date) -> str:
    return f"{value:%A} {value.day} {value:%B}"  # "Tuesday 6 October"
