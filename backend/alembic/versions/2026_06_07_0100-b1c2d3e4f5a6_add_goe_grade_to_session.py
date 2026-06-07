"""add goe_grade to session

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f4
Create Date: 2026-06-07 01:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a9b0c1d2e3f4"
branch_labels: str | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("goe_grade", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "goe_grade")
