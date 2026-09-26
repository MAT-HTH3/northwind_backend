from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.legacy import LegacySystems


@dataclass(frozen=True)
class GraphContext:
    """Dependencies handed to every node through LangGraph's runtime context.

    Passed on each invocation (not captured at build time) so tests can swap them freely.
    """

    session_factory: async_sessionmaker[AsyncSession]
    legacy: LegacySystems
    llm: BaseChatModel
