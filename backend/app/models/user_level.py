"""UserLevel ORM model — gamification level tracking."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserLevel(TimestampMixin, Base):
    """User level and XP tracking."""

    __tablename__ = "user_levels"

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
