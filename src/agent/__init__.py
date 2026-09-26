"""The LangGraph support agent: decides whether the AI Assistant resolves a request or a
Human Agent takes it."""

from langchain_google_genai import ChatGoogleGenerativeAI

from src.agent.context import GraphContext
from src.core.config import get_settings
from src.core.db import SessionLocal
from src.legacy import get_legacy_systems


def gemini(model: str) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model, api_key=get_settings().gemini_api_key.get_secret_value()
    )


def default_context() -> GraphContext:
    settings = get_settings()
    return GraphContext(
        session_factory=SessionLocal,
        legacy=get_legacy_systems(),
        categorizer_llm=gemini(settings.gemini_model),
        resolver_llm=gemini(settings.gemini_resolver_model),
    )
