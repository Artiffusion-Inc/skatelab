"""nullable element_type on sessions

Revision ID: e1d2c3b4a5f6
Revises: 0e5a9f25728f
Create Date: 2026-06-26 12:00:00.000000

"""

from alembic import op

revision = "e1d2c3b4a5f6"
down_revision = "0e5a9f25728f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("sessions", "element_type", nullable=True)


def downgrade() -> None:
    op.alter_column("sessions", "element_type", nullable=False)
