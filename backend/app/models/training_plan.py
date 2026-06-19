"""TrainingPlanModel ORM model — AI-generated training plans."""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TrainingPlanModel(TimestampMixin, Base):
    """AI-generated training plan linked to a user and optionally a session."""

    __tablename__ = "training_plans"

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
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    items: Mapped[dict] = mapped_column(JSON)  # array of TrainingPlanItem objects
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    focus_subscore: Mapped[str | None] = mapped_column(String(50), nullable=True)
