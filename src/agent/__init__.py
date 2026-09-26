"""The LangGraph support agent: decides whether the AI Assistant resolves a request or a
Human Agent takes it."""

from src.agent.context import GraphContext
from src.core.db import SessionLocal
from src.legacy import get_legacy_systems


def default_context() -> GraphContext:
    return GraphContext(session_factory=SessionLocal, legacy=get_legacy_systems())
