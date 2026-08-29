"""Coach comment persistence operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.comment import CoachComment

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create(
    db: AsyncSession,
    *,
    session_id: str,
    coach_id: str,
    content: str,
) -> CoachComment:
    """Create a comment after the route has verified coach access."""
    comment = CoachComment(
        session_id=session_id,
        coach_id=coach_id,
        content=content,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment)
    return comment
