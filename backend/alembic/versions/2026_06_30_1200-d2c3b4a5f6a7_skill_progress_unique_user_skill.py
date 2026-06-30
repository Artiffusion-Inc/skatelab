"""add unique constraint (user_id, skill_id) to skill_progress (#459)

Revision ID: d2c3b4a5f6a7
Revises: e1d2c3b4a5f6
Create Date: 2026-06-30 12:00:00.000000

Guards the get_or_create race: two concurrent check_skill_unlocks for the same
(user_id, skill_id) both read None and both insert. The unique constraint
rejects the duplicate insert; get_or_create uses ON CONFLICT DO NOTHING to
turn the rejection into a no-op re-read. Without this, duplicate skill_progress
rows materialize (duplicate UI entries, second-unlock re-flips
unlocked/best_score, per-row xp_reward double-awards if awarded).
"""

from alembic import op

revision = "d2c3b4a5f6a7"
down_revision = "e1d2c3b4a5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dedupe any existing duplicate (user_id, skill_id) rows before adding the
    # constraint, keeping the latest by updated_at, else the row with the
    # highest unlocked/best_score so an unlocked skill is not lost.
    op.execute(
        """
        DELETE FROM skill_progress
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id, skill_id) id
            FROM skill_progress
            ORDER BY user_id, skill_id, updated_at DESC, unlocked DESC, best_score DESC, id
        )
        """
    )
    op.create_unique_constraint(
        "uq_skill_progress_user_skill",
        "skill_progress",
        ["user_id", "skill_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_skill_progress_user_skill", "skill_progress", type_="unique")
