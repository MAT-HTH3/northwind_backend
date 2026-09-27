"""Support Case categories: the agent desk's six. Gemini picks one; the Triage Rules
(src/triage) then set Urgency, queue and due date from it, never the LLM."""

from typing import Literal

from src.triage import Category

__all__ = [
    "FALLBACK",
    "METER_READING",
    "SUBJECTS",
    "TEAM",
    "Category",
    "Subject",
    "subject_for",
    "team_for",
]

METER_READING: Category = "Meter reading"
FALLBACK: Category = "Service"

# How the AI Assistant names each queue to the customer.
TEAM: dict[str, str] = {
    "Billing specialists": "billing team",
    "Metering": "metering team",
    "Field operations": "field team",
    "Customer relations": "customer relations team",
}


def team_for(queue: str) -> str:
    return TEAM.get(queue, "team")


# The desk's case titles (its seed subjects), plus a few for chat cases. Gemini picks one; it
# never writes a title.
SUBJECTS: dict[str, list[str]] = {
    "Billing": [
        "Bill much higher than usual",
        "Estimated bill disputed",
        "Wants the charges explained",
        "Tariff change not explained",
        "Charged after moving out",
        "Other billing query",
    ],
    "Meter reading": [
        "Reading not accepted",
        "Reading needs checking",
        "Smart meter not sending readings",
        "Meter reader missed appointment",
        "Other meter reading query",
    ],
    "Payments": [
        "Direct Debit increased",
        "Refund not received",
        "Payment plan request",
        "Other payments query",
    ],
    "Supply": [
        "Power cut with no updates",
        "Low water pressure",
        "Leak or supply fault",
        "Other supply problem",
    ],
    "Water quality": ["Discoloured water", "Other water quality concern"],
    "Service": [
        "No reply to earlier complaint",
        "Had to explain the problem again",
        "Asked for a person",
        "Other service query",
    ],
}

Subject = Literal[
    "Bill much higher than usual",
    "Estimated bill disputed",
    "Wants the charges explained",
    "Tariff change not explained",
    "Charged after moving out",
    "Other billing query",
    "Reading not accepted",
    "Reading needs checking",
    "Smart meter not sending readings",
    "Meter reader missed appointment",
    "Other meter reading query",
    "Direct Debit increased",
    "Refund not received",
    "Payment plan request",
    "Other payments query",
    "Power cut with no updates",
    "Low water pressure",
    "Leak or supply fault",
    "Other supply problem",
    "Discoloured water",
    "Other water quality concern",
    "No reply to earlier complaint",
    "Had to explain the problem again",
    "Asked for a person",
    "Other service query",
]


def subject_for(category: str, subject: str | None) -> str:
    """The subject if it belongs to the category, otherwise the category's catch-all."""
    options = SUBJECTS.get(category, SUBJECTS[FALLBACK])
    return subject if subject in options else options[-1]
