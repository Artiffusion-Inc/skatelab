"""nullable element_type on sessions

Revision ID: 2026_06_26_1200-e1d2c3b4a5f6
Revises: f0e1d2c3b4a5
Create Date: 2026-06-26 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "2026_06_26_1200-e1d2c3b4a5f6"
down_revision = "f0e1d2c3b4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("sessions", "element_type", nullable=True)


def downgrade() -> None:
    op.alter_column("sessions", "element_type", nullable=False)
