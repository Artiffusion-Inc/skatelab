"""add_user_agent_hash_to_refresh_tokens

Revision ID: b2c3d4e5f6a7
Revises: a8f189382ae9
Create Date: 2026-05-22 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a8f189382ae9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("user_agent_hash", sa.String(64), nullable=True))

    # Batched backfill to avoid row-level lock contention
    conn = op.get_bind()
    while True:
        result = conn.execute(
            sa.text(
                "UPDATE refresh_tokens SET user_agent_hash = 'legacy' "
                "WHERE user_agent_hash IS NULL LIMIT 1000"
            )
        )
        if result.rowcount == 0:
            break


def downgrade() -> None:
    op.drop_column("refresh_tokens", "user_agent_hash")
