"""customer readings accepted or needing review

Revision ID: 4999e290e323
Revises: dfdf0e366d8d
Create Date: 2026-09-26 20:57:28.558105

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4999e290e323"
down_revision: str | Sequence[str] | None = "dfdf0e366d8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """ADR 0004: readings are accepted or need review; only the latter belong to a case."""
    with op.batch_alter_table("customer_readings") as batch:
        batch.drop_constraint(op.f("ck_customer_readings_reading_status"), type_="check")
        batch.alter_column("case_id", existing_type=sa.String(length=16), nullable=True)
    op.execute(
        "UPDATE customer_readings SET status = 'needs_review' WHERE status = 'awaiting_review'"
    )
    with op.batch_alter_table("customer_readings") as batch:
        batch.create_check_constraint(
            op.f("ck_customer_readings_reading_status"), "status IN ('accepted', 'needs_review')"
        )


def downgrade() -> None:
    # Accepted readings have no case and no equivalent before ADR 0004, so they are removed.
    op.execute("DELETE FROM customer_readings WHERE status = 'accepted'")
    with op.batch_alter_table("customer_readings") as batch:
        batch.drop_constraint(op.f("ck_customer_readings_reading_status"), type_="check")
    op.execute(
        "UPDATE customer_readings SET status = 'awaiting_review' WHERE status = 'needs_review'"
    )
    with op.batch_alter_table("customer_readings") as batch:
        batch.alter_column("case_id", existing_type=sa.String(length=16), nullable=False)
        batch.create_check_constraint(
            op.f("ck_customer_readings_reading_status"), "status IN ('awaiting_review')"
        )
