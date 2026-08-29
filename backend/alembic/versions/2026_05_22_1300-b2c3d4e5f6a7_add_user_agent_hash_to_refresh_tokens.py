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

    # A single idempotent update works in both online and offline Alembic
    # modes. The previous ctid/rowcount loop crashed while rendering SQL
    # because offline execution has no result object.
    op.execute(
        sa.text(
            "UPDATE refresh_tokens SET user_agent_hash = 'legacy' "
            "WHERE user_agent_hash IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "user_agent_hash")
