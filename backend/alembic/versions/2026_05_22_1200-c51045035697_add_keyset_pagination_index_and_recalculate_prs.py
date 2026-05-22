"""add keyset pagination index and recalculate prs

Revision ID: c51045035697
Revises: f1a2b3c4d5e6
Create Date: 2026-05-22 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
<<<<<<<< HEAD:backend/alembic/versions/2026_05_22_1200-c51045035697_add_keyset_pagination_index_and_recalculate_prs.py
revision: str = "c51045035697"
========
revision: str = "f1a2b3c4d5e7"
>>>>>>>> 20c826cd (feat(auth): make RefreshRequest.refresh_token optional + backfill email verified):backend/alembic/versions/2026_05_22_1200-f1a2b3c4d5e7_add_keyset_pagination_index_and_recalculate_prs.py
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add composite index for keyset pagination
    op.create_index(
        "ix_sessions_user_element_created_id_desc",
        "sessions",
        ["user_id", "element_type", "created_at", "id"],
    )

    # Step 1: Reset all is_pr and prev_best
    op.execute("UPDATE session_metrics SET is_pr = FALSE, prev_best = NULL")

    # Step 2a: Mark best values as PRs for "higher is better" metrics
    op.execute("""
        WITH ranked AS (
            SELECT
                sm.id,
                ROW_NUMBER() OVER (
                    PARTITION BY s.user_id, s.element_type, sm.metric_name
                    ORDER BY sm.metric_value DESC, sm.id DESC
                ) AS rn
            FROM session_metrics sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE s.status = 'done'
                AND sm.metric_name NOT IN ('landing_knee_angle', 'knee_angle', 'trunk_lean')
        )
        UPDATE session_metrics sm
        SET is_pr = TRUE
        FROM ranked r
        WHERE sm.id = r.id AND r.rn = 1
    """)

    # Step 2b: Mark best values as PRs for "lower is better" metrics
    op.execute("""
        WITH ranked AS (
            SELECT
                sm.id,
                ROW_NUMBER() OVER (
                    PARTITION BY s.user_id, s.element_type, sm.metric_name
                    ORDER BY sm.metric_value ASC, sm.id DESC
                ) AS rn
            FROM session_metrics sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE s.status = 'done'
                AND sm.metric_name IN ('landing_knee_angle', 'knee_angle', 'trunk_lean')
        )
        UPDATE session_metrics sm
        SET is_pr = TRUE
        FROM ranked r
        WHERE sm.id = r.id AND r.rn = 1
    """)

    # Step 3a: Set prev_best for "higher" metrics (second-best value)
    op.execute("""
        WITH ranked AS (
            SELECT
                sm.id,
                sm.metric_value,
                s.user_id,
                s.element_type,
                sm.metric_name,
                ROW_NUMBER() OVER (
                    PARTITION BY s.user_id, s.element_type, sm.metric_name
                    ORDER BY sm.metric_value DESC, sm.id DESC
                ) AS rn
            FROM session_metrics sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE s.status = 'done'
                AND sm.metric_name NOT IN ('landing_knee_angle', 'knee_angle', 'trunk_lean')
        )
        UPDATE session_metrics sm
        SET prev_best = r2.metric_value
        FROM ranked r1
        JOIN ranked r2 ON r1.user_id = r2.user_id
            AND r1.element_type = r2.element_type
            AND r1.metric_name = r2.metric_name
            AND r2.rn = 2
        WHERE sm.id = r1.id AND r1.rn = 1
    """)

    # Step 3b: Set prev_best for "lower" metrics (second-best value)
    op.execute("""
        WITH ranked AS (
            SELECT
                sm.id,
                sm.metric_value,
                s.user_id,
                s.element_type,
                sm.metric_name,
                ROW_NUMBER() OVER (
                    PARTITION BY s.user_id, s.element_type, sm.metric_name
                    ORDER BY sm.metric_value ASC, sm.id DESC
                ) AS rn
            FROM session_metrics sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE s.status = 'done'
                AND sm.metric_name IN ('landing_knee_angle', 'knee_angle', 'trunk_lean')
        )
        UPDATE session_metrics sm
        SET prev_best = r2.metric_value
        FROM ranked r1
        JOIN ranked r2 ON r1.user_id = r2.user_id
            AND r1.element_type = r2.element_type
            AND r1.metric_name = r2.metric_name
            AND r2.rn = 2
        WHERE sm.id = r1.id AND r1.rn = 1
    """)


def downgrade() -> None:
    op.drop_index("ix_sessions_user_element_created_id_desc", table_name="sessions")
    # Note: is_pr/prev_best recalculation is not reversible without a backup
