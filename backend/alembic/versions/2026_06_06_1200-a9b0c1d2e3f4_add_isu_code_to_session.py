"""add isu_code to session

Revision ID: a9b0c1d2e3f4
Revises: c3d4e5f6a7b8
Create Date: 2026-06-06 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9b0c1d2e3f4"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("isu_code", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "isu_code")
