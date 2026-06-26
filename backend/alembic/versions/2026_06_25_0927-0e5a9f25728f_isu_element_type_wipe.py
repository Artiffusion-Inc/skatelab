"""isu element_type wipe

Revision ID: 0e5a9f25728f
Revises: f0e1d2c3b4a5
Create Date: 2026-06-25 09:27:26.793350

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0e5a9f25728f"
down_revision: str | Sequence[str] | None = "f0e1d2c3b4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Wipe legacy session rows whose element_type holds pre-ISU slugs.

    Dev-stage: no production users. Old element_type slugs ("axel", "toe_loop",
    ...) carry no rotation level and cannot map unambiguously to the new ISU
    codes (e.g. "1A", "1T"). Decision: wipe all sessions, do not backfill and do
    not introduce a nullable legacy field. Explicit DELETEs on each child table
    first (do not rely on FK ON DELETE CASCADE), then sessions. The
    element_type column stays String(50) — only values change (<=8-char ISU
    codes), no ALTER on the column.
    """
    op.execute("DELETE FROM session_metrics;")
    op.execute("DELETE FROM session_elements;")
    op.execute("DELETE FROM session_phases;")
    op.execute("DELETE FROM sessions;")


def downgrade() -> None:
    """No downgrade: wiped data is unrecoverable. Dev-stage accepted."""
    pass
