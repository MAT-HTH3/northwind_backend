"""Support Case categories: the agent desk's six. Gemini picks one; the Triage Rules
(src/triage) then set Urgency, queue and due date from it, never the LLM."""

from src.triage import Category

__all__ = ["FALLBACK", "METER_READING", "TEAM", "Category", "team_for"]

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
