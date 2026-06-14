"""add analyzer tables (user_levels, skill_progress, session_scores, session_phases, training_plans)

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-06-08 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. user_levels
    op.create_table(
        "user_levels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("level", sa.Integer(), server_default="1", nullable=False),
        sa.Column("total_xp", sa.Integer(), server_default="0", nullable=False),
        sa.Column("xp_to_next", sa.Integer(), server_default="100", nullable=False),
        sa.Column("title", sa.String(50), server_default="Новичок", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 2. skill_progress
    op.create_table(
        "skill_progress",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("skill_id", sa.String(50), index=True, nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("tier", sa.String(10), nullable=False),
        sa.Column("unlocked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_sessions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("best_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("xp_reward", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 3. session_scores
    op.create_table(
        "session_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id", ondelete="CASCADE"), index=True, unique=True, nullable=False),
        sa.Column("subscores", sa.JSON(), nullable=False),
        sa.Column("overall", sa.Float(), nullable=False),
        sa.Column("data_quality", sa.String(20), server_default="good", nullable=False),
        sa.Column("skeleton_reliability", sa.String(20), server_default="reliable", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 4. session_phases
    op.create_table(
        "session_phases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id", ondelete="CASCADE"), index=True, unique=True, nullable=False),
        sa.Column("phases", sa.JSON(), nullable=False),
        sa.Column("overall_confidence", sa.Float(), nullable=False),
        sa.Column("element_type", sa.String(50), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 5. training_plans
    op.create_table(
        "training_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id", ondelete="SET NULL"), index=True, nullable=True),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("focus_subscore", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("training_plans")
    op.drop_table("session_phases")
    op.drop_table("session_scores")
    op.drop_table("skill_progress")
    op.drop_table("user_levels")