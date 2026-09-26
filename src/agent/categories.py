"""Support Case categories and how each one is routed. Gemini picks the category from this
closed list; Priority, SLA and queue are fixed here, never chosen by the LLM."""

from dataclasses import dataclass
from typing import Literal

from src.models import Priority

Category = Literal[
    "Supply fault - repair needed",
    "Meter fault",
    "Meter reading review",
    "Billing - estimated read",
    "Billing - dispute or refund",
    "Billing - payment arrangement",
    "General enquiry",
]

METER_READING_REVIEW: Category = "Meter reading review"
FALLBACK: Category = "General enquiry"


@dataclass(frozen=True)
class Routing:
    priority: Priority
    sla_days: int
    queue: str
    team: str  # how the AI Assistant names the queue to the customer


ROUTING: dict[Category, Routing] = {
    "Supply fault - repair needed": Routing(Priority.HIGH, 5, "Field engineers", "engineers"),
    "Meter fault": Routing(Priority.MID, 10, "Metering team", "metering team"),
    "Meter reading review": Routing(Priority.MID, 10, "Billing specialists", "billing team"),
    "Billing - estimated read": Routing(Priority.MID, 10, "Billing specialists", "billing team"),
    "Billing - dispute or refund": Routing(Priority.MID, 10, "Billing specialists", "billing team"),
    "Billing - payment arrangement": Routing(
        Priority.LOW, 20, "Billing specialists", "billing team"
    ),
    "General enquiry": Routing(Priority.LOW, 20, "Customer care", "customer care team"),
}
