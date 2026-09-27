"""ORM models for the records this service owns. Legacy System data is never stored here.

Importing this package registers every table on `Base.metadata` (Alembic relies on it).
"""

from src.models.conversation import Conversation
from src.models.reading import UNITS, CustomerReading, ReadingStatus, Service
from src.models.resolution import ResolutionAnswer
from src.models.seed import SeedExtra
from src.models.support_case import (
    CaseConversation,
    CaseSource,
    CaseStatus,
    Channel,
    FeedbackNote,
    HeldMessage,
    SupportCase,
    TimelineEvent,
    Urgency,
)

__all__ = [
    "UNITS",
    "CaseConversation",
    "CaseSource",
    "CaseStatus",
    "Channel",
    "Conversation",
    "CustomerReading",
    "FeedbackNote",
    "HeldMessage",
    "ReadingStatus",
    "ResolutionAnswer",
    "SeedExtra",
    "Service",
    "SupportCase",
    "TimelineEvent",
    "Urgency",
]
