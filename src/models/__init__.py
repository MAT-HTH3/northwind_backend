"""ORM models for the records this service owns. Legacy System data is never stored here.

Importing this package registers every table on `Base.metadata` (Alembic relies on it).
"""

from src.models.conversation import Conversation
from src.models.reading import UNITS, CustomerReading, ReadingStatus, Service
from src.models.resolution import ResolutionAnswer
from src.models.support_case import (
    CaseConversation,
    CaseStatus,
    HeldMessage,
    SupportCase,
    Urgency,
)

__all__ = [
    "UNITS",
    "CaseConversation",
    "CaseStatus",
    "Conversation",
    "CustomerReading",
    "HeldMessage",
    "ReadingStatus",
    "ResolutionAnswer",
    "Service",
    "SupportCase",
    "Urgency",
]
