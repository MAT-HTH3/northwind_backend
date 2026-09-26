import secrets
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import Base

IdFactory = Callable[[], str]
MAX_ATTEMPTS = 10


def random_id(prefix: str) -> IdFactory:
    """Customer-facing reference like "NW-231904": short enough to read out on the phone."""
    return lambda: f"{prefix}-{secrets.randbelow(900_000) + 100_000}"


class IdSpaceExhaustedError(RuntimeError):
    pass


async def unique_id(session: AsyncSession, model: type[Base], factory: IdFactory) -> str:
    for _ in range(MAX_ATTEMPTS):
        candidate = factory()
        if await session.get(model, candidate) is None:
            return candidate
    raise IdSpaceExhaustedError(f"No free {model.__name__} id after {MAX_ATTEMPTS} attempts")


new_case_id = random_id("NW")
new_reading_id = random_id("MR")
