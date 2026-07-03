"""UserLevel ORM model — gamification level tracking."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserLevel(TimestampMixin, Base):
    """User level and XP tracking."""

    __tablename__ = "user_levels"
    # #485: unique constraint on user_id — sibling of #459 (skill_progress).
    # Without this, two concurrent get_by_user_id calls for a new user both
    # see no existing row and both INSERT, creating 2 rows for one user.
    # The next get_by_user_id then raises MultipleResultsFound, permanently
    # crashing gamification for that user.
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_level_user"),)

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
    level: Mapped[int] = mapped_column(Integer, default=1)
    total_xp: Mapped[int] = mapped_column(Integer, default=0)
    xp_to_next: Mapped[int] = mapped_column(Integer, default=100)
    title: Mapped[str] = mapped_column(String(50), default="Новичок")
