"""The Unified Customer History, shared by the AI Assistant and the Human Agent's view."""

from src.history.builder import UnknownCustomerError, build_history
from src.history.models import UnifiedCustomerHistory

__all__ = ["UnifiedCustomerHistory", "UnknownCustomerError", "build_history"]
