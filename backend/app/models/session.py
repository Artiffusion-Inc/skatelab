"""Session and SessionMetric ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Session(TimestampMixin, Base):
    """Analysis session for a single video upload."""

    __tablename__ = "sessions"

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
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    element_type: Mapped[str] = mapped_column(String(50), index=True)
    video_key: Mapped[str | None] = mapped_column(String(500))
    video_url: Mapped[str | None] = mapped_column(String(500))
    processed_video_key: Mapped[str | None] = mapped_column(String(500))
    processed_video_url: Mapped[str | None] = mapped_column(String(500))
    # Deprecated: poses_url and csv_url replaced by pose_data and frame_metrics
    poses_url: Mapped[str | None] = mapped_column(String(500))
    csv_url: Mapped[str | None] = mapped_column(String(500))
    # New JSON columns for direct pose data storage
    pose_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    frame_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="uploading")
    error_message: Mapped[str | None] = mapped_column(Text)
    phases: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommendations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    process_task_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    imu_left_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    imu_right_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manifest_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    metrics: Mapped[list[SessionMetric]] = relationship(
        "SessionMetric",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    elements: Mapped[list[SessionElement]] = relationship(
        "SessionElement",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    segmentation_status: Mapped[str] = mapped_column(
        String(20),
        server_default="pending",
        nullable=False,
    )

    __table_args__ = (
        Index("ix_sessions_user_element_created", "user_id", "element_type", "created_at"),
        Index(
            "ix_sessions_user_element_created_id_desc",
            "user_id",
            "element_type",
            "created_at",
            "id",
        ),
    )


class SessionMetric(TimestampMixin, Base):
    """Individual biomechanics metric for a session."""

    __tablename__ = "session_metrics"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(100), index=True)
    metric_value: Mapped[float] = mapped_column(Float)
    is_pr: Mapped[bool] = mapped_column(default=False)
    prev_best: Mapped[float | None] = mapped_column(Float)
    reference_value: Mapped[float | None] = mapped_column(Float)
    is_in_range: Mapped[bool | None] = mapped_column()

    # Relationship back to session
    session: Mapped[Session] = relationship(
        "Session",
        back_populates="metrics",
    )

    __table_args__ = (
        # Unique constraint on (session_id, metric_name)
        Index("uq_session_metric_name", "session_id", "metric_name", unique=True),
    )


class SessionElement(TimestampMixin, Base):
    """Detected skating element from automatic timeline segmentation."""

    __tablename__ = "session_elements"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
    )
    element_type: Mapped[str] = mapped_column(String(50))
    element_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_frame: Mapped[int] = mapped_column()
    end_frame: Mapped[int] = mapped_column()
    confidence: Mapped[float] = mapped_column(Float)
    phases_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session: Mapped[Session] = relationship("Session", back_populates="elements")
