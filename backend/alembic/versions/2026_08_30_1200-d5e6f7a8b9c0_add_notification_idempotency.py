"""add notification event idempotency

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-30 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("source_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "uq_notifications_user_event_source",
        "notifications",
        ["user_id", "event_type", "source_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_notifications_user_event_source", table_name="notifications")
    op.drop_column("notifications", "source_id")
