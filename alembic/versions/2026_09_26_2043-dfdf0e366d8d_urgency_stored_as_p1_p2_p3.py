"""urgency stored as P1 P2 P3

Revision ID: dfdf0e366d8d
Revises: ee096bacd98b
Create Date: 2026-09-26 20:43:39.331502

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dfdf0e366d8d"
down_revision: str | Sequence[str] | None = "ee096bacd98b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_TO_NEW = {"high": "P1", "mid": "P2", "low": "P3"}


def _recode(mapping: dict[str, str], check: str) -> None:
    # Drop the old CHECK first, or recoding the rows would violate it.
    with op.batch_alter_table("support_cases") as batch:
        batch.drop_constraint(op.f("ck_support_cases_priority"), type_="check")
    for old, new in mapping.items():
        op.execute(
            sa.text("UPDATE support_cases SET priority = :new WHERE priority = :old").bindparams(
                old=old, new=new
            )
        )
    with op.batch_alter_table("support_cases") as batch:
        batch.create_check_constraint(op.f("ck_support_cases_priority"), check)


def upgrade() -> None:
    """Urgency is stored as the API's P1/P2/P3 (CONTEXT.md "Urgency")."""
    _recode(OLD_TO_NEW, "priority IN ('P1', 'P2', 'P3')")


def downgrade() -> None:
    _recode({v: k for k, v in OLD_TO_NEW.items()}, "priority IN ('high', 'mid', 'low')")
