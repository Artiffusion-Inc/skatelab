"""SessionScore ORM model — composite scoring per session."""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SessionScore(TimestampMixin, Base):
    """Composite scoring result for an analysis session."""

    __tablename__ = "session_scores"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        unique=True,
    )
    subscores: Mapped[dict] = mapped_column(JSON)  # array of SubScore objects
    overall: Mapped[float] = mapped_column(Float)
    data_quality: Mapped[str] = mapped_column(String(20), default="good")
    skeleton_reliability: Mapped[str] = mapped_column(String(20), default="reliable")
