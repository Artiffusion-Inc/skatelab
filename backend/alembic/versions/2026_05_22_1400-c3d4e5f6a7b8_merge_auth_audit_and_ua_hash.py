"""merge auth_audit_log and ua_hash heads.

Revision ID: c3d4e5f6a7b8
Revises: a2b3c4d5e6f7, b2c3d4e5f6a7
Create Date: 2026-05-22 14:00:00.000000

"""

from collections.abc import Sequence

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = ("a2b3c4d5e6f7", "b2c3d4e5f6a7")
branch_labels: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
