"""The LangGraph support agent: decides whether the AI Assistant resolves a request or a
Human Agent takes it."""

from langchain_google_genai import ChatGoogleGenerativeAI

from src.agent.context import GraphContext
from src.core.config import get_settings
from src.core.db import SessionLocal
from src.legacy import get_legacy_systems


def default_context() -> GraphContext:
    settings = get_settings()
    return GraphContext(
        session_factory=SessionLocal,
        legacy=get_legacy_systems(),
        llm=ChatGoogleGenerativeAI(
            model=settings.gemini_model, api_key=settings.gemini_api_key.get_secret_value()
        ),
    )
