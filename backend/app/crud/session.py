"""Session CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from app.models.session import Session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create(db: AsyncSession, *, user_id: str, element_type: str, **kwargs: Any) -> Session:
    session = Session(user_id=user_id, element_type=element_type, **kwargs)
    db.add(session)
    await db.flush()
    await db.refresh(session, attribute_names=["metrics"])
    return session


async def get_by_id(db: AsyncSession, session_id: str) -> Session | None:
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.metrics), selectinload(Session.elements))
        .where(Session.id == session_id)
    )
    return result.scalar_one_or_none()


async def list_by_user(
    db: AsyncSession,
    user_id: str,
    *,
    element_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "created_at",
) -> list[Session]:
    query = select(Session).options(selectinload(Session.metrics)).where(Session.user_id == user_id)
    if element_type:
        query = query.where(Session.element_type == element_type)
    if sort == "overall_score":
        query = query.order_by(desc(Session.overall_score))
    else:
        query = query.order_by(desc(Session.created_at))
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def count_by_user(
    db: AsyncSession,
    user_id: str,
    *,
    element_type: str | None = None,
) -> int:
    query = select(func.count()).select_from(Session).where(Session.user_id == user_id)
    if element_type:
        query = query.where(Session.element_type == element_type)
    result = await db.execute(query)
    return result.scalar_one()


async def update(db: AsyncSession, session: Session, **kwargs: Any) -> Session:
    for key, value in kwargs.items():
        if value is not None:
            setattr(session, key, value)
    db.add(session)
    await db.flush()
    await db.refresh(session, attribute_names=["metrics"])
    return session


async def soft_delete(db: AsyncSession, session: Session) -> None:
    session.status = "deleted"
    db.add(session)
    await db.flush()


async def update_session_analysis(
    db: AsyncSession,
    session_id: str,
    pose_data: dict[str, object] | None,
    frame_metrics: dict[str, object] | None,
    phases: dict[str, object] | None,
) -> Session:
    """Update session with JSON pose data and metrics.

    Args:
        db: Async database session
        session_id: ID of the Session row
        pose_data: Sampled pose data (frames, poses, fps)
        frame_metrics: Frame-by-frame biomechanics metrics
        phases: Element phase markers (takeoff, peak, landing)

    Returns:
        Updated Session object
    """
    stmt = (
        sa.update(Session)
        .where(Session.id == session_id)
        .values(
            pose_data=pose_data,
            frame_metrics=frame_metrics,
            phases=phases,
            status="completed",
            processed_at=func.now(),
        )
        .returning(Session)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def batch_insert_elements(
    db: AsyncSession,
    session_id: str,
    segments: list[dict],
    segmentation_confidence: float | None = None,
) -> list[SessionElement]:
    """Batch insert timeline segments in a single transaction."""
    from app.models.session import SessionElement

    elements = []
    for seg in segments:
        element = SessionElement(
            session_id=session_id,
            element_type=seg["element_type"],
            element_name=seg.get("element_name"),
            start_frame=seg["start"],
            end_frame=seg["end"],
            confidence=seg["confidence"],
            phases_json=seg.get("phases_json"),
        )
        db.add(element)
        elements.append(element)
    await db.flush()
    return elements
