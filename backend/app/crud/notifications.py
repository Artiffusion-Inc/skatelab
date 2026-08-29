"""Notification CRUD operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import sqlalchemy as sa
from sqlalchemy import func, select

from app.models.notifications import Notification

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create(
    db: AsyncSession,
    *,
    user_id: str,
    event_type: str,
    title: str,
    body: str,
    deep_link: str | None = None,
    payload: dict[str, object] | None = None,
    source_id: str | None = None,
) -> Notification:
    """Create an in-app notification for one user."""
    notification = Notification(
        user_id=user_id,
        event_type=event_type,
        source_id=source_id,
        title=title,
        body=body,
        deep_link=deep_link,
        payload=payload,
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)
    return notification


async def get_by_event_source(
    db: AsyncSession,
    *,
    user_id: str,
    event_type: str,
    source_id: str,
) -> Notification | None:
    """Find the notification emitted for one recipient and business event."""
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.event_type == event_type,
            Notification.source_id == source_id,
        )
    )
    return result.scalar_one_or_none()


async def list_by_user(
    db: AsyncSession,
    user_id: str,
    *,
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
) -> list[Notification]:
    """List a user's notifications, newest first."""
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    query = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def count_by_user(
    db: AsyncSession,
    user_id: str,
    *,
    unread_only: bool = False,
) -> int:
    """Count a user's notifications, optionally only unread rows."""
    query = select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    result = await db.execute(query)
    return int(result.scalar_one())


async def get_by_id_for_user(
    db: AsyncSession,
    notification_id: str,
    user_id: str,
) -> Notification | None:
    """Get a notification only when it belongs to the requesting user."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    return result.scalars().first()


async def mark_read(
    db: AsyncSession,
    notification: Notification,
) -> Notification:
    """Mark a notification read; repeated calls are idempotent."""
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(UTC)
        db.add(notification)
        await db.flush()
        await db.refresh(notification)
    return notification


async def mark_all_read(db: AsyncSession, user_id: str) -> int:
    """Mark all unread notifications for a user read and return the number changed."""
    result = await db.execute(
        sa.update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=func.now())
    )
    await db.flush()
    return cast("int", getattr(result, "rowcount", 0))
