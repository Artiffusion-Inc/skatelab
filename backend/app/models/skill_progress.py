"""SkillProgress ORM model — skill unlock tracking."""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SkillProgress(TimestampMixin, Base):
    """Per-skill progress tracking (jumps, spins, control across tiers)."""

    __tablename__ = "skill_progress"
    # ponytail: DB-level guard against the get_or_create race (#459) — two
    # concurrent check_skill_unlocks both read None and both insert; this
    # unique constraint rejects the second insert so only one row per
    # (user_id, skill_id) survives. get_or_create uses ON CONFLICT DO NOTHING
    # to turn the rejection into a no-op re-read.
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_skill_progress_user_skill"),)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    skill_id: Mapped[str] = mapped_column(String(50), index=True)
    category: Mapped[str] = mapped_column(String(20))  # "jumps" | "spins" | "control"
    tier: Mapped[str] = mapped_column(String(10))  # "bronze" | "silver" | "gold"
    unlocked: Mapped[bool] = mapped_column(Boolean, default=False)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_sessions: Mapped[int] = mapped_column(Integer, default=0)
    best_score: Mapped[float] = mapped_column(Float, default=0.0)
    xp_reward: Mapped[int] = mapped_column(Integer, default=0)
