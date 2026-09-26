from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.core.config import get_settings


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[AsyncSqliteSaver]:
    """Durable conversation memory. Paused threads must survive a restart, or a Human Agent
    could never resume them. Swap for AsyncPostgresSaver when moving to Postgres."""
    async with AsyncSqliteSaver.from_conn_string(get_settings().checkpoint_db_path) as saver:
        yield saver
