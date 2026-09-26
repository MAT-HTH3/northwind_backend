from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """A timezone-aware UTC timestamp on every backend.

    Postgres stores `timestamptz` natively, but SQLite drops the offset and hands back naive
    datetimes. This type rejects naive values on the way in and restores UTC on the way out,
    so code behaves the same before and after the move to Postgres.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Store a StrEnum as its value in a VARCHAR with a CHECK constraint.

    Not a native Postgres ENUM: adding a value later is then a plain migration, not an
    `ALTER TYPE`, and the column works the same on SQLite.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )
