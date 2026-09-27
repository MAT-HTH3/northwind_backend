"""Data access for the records this service owns, so the graph and routes never touch SQLAlchemy."""

from src.repositories.conversations import ConversationOutcome, ConversationRepository
from src.repositories.ids import IdSpaceExhaustedError
from src.repositories.readings import ReadingRepository
from src.repositories.resolutions import ResolutionRepository
from src.repositories.support_cases import (
    AI_ASSISTANT,
    CaseAlreadyClosedError,
    CaseChanges,
    SupportCaseRepository,
)

__all__ = [
    "AI_ASSISTANT",
    "CaseAlreadyClosedError",
    "CaseChanges",
    "ConversationOutcome",
    "ConversationRepository",
    "IdSpaceExhaustedError",
    "ReadingRepository",
    "ResolutionRepository",
    "SupportCaseRepository",
]
