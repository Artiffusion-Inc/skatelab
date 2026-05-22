"""set_existing_users_email_verified

Revision ID: a8f189382ae9
Revises: f1a2b3c4d5e7
Create Date: 2026-05-22 11:36:29.696183

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8f189382ae9"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE users SET is_verified = TRUE WHERE is_verified = FALSE")


def downgrade() -> None:
    pass  # No-op downgrade — cannot un-verify users
