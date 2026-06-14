"""SessionPhase ORM model — extended phase detection per session."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SessionPhase(TimestampMixin, Base):
    """Extended phase detection result for an analysis session."""

    __tablename__ = "session_phases"

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
    phases: Mapped[dict] = mapped_column(JSON)  # array of PhaseExtended objects
    overall_confidence: Mapped[float] = mapped_column(Float)
    element_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)