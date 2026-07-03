"""add unique constraint user_id to user_levels (#485)

Revision ID: 4857b5e8c9d0
Revises: d2c3b4a5f6a7
Create Date: 2026-07-03 21:00:00.000000

Sister migration to #459 (skill_progress). Guards the get_by_user_id
race: two concurrent award_session_xp for a user with no existing row
both read None and both INSERT. The unique constraint rejects the
duplicate insert; get_by_user_id uses ON CONFLICT DO NOTHING to turn
the rejection into a no-op re-read. Without this, 2 user_levels rows
materialize for one user; subsequent get_by_user_id raises
MultipleResultsFound and every gamification call for that user crashes
permanently until manual DB cleanup.
"""

from alembic import op

revision = "4857b5e8c9d0"
down_revision = "d2c3b4a5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dedupe any existing duplicate user_id rows before adding the
    # constraint, keeping the latest by updated_at, else the row with
    # the highest total_xp so XP progress is not lost.
    op.execute(
        """
        DELETE FROM user_levels
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id) id
            FROM user_levels
            ORDER BY user_id, updated_at DESC, total_xp DESC, id
        )
        """
    )
    op.create_unique_constraint(
        "uq_user_level_user",
        "user_levels",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_level_user", "user_levels", type_="unique")
