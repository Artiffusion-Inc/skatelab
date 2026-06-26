"""VerificationToken CRUD operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, select

from app.models.verification_token import VerificationToken

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create(
    db: AsyncSession,
    *,
    user_id: str,
    token_hash: str,
    expires_at: datetime,
) -> VerificationToken:
    token = VerificationToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(token)
    await db.flush()
    await db.refresh(token)
    return token


async def get_by_hash(db: AsyncSession, token_hash: str) -> VerificationToken | None:
    result = await db.execute(
        select(VerificationToken).where(
            VerificationToken.token_hash == token_hash,
            VerificationToken.used_at.is_(None),
            VerificationToken.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none()


async def mark_used(db: AsyncSession, token: VerificationToken) -> None:
    token.used_at = datetime.now(UTC)
    db.add(token)
    await db.flush()


async def invalidate_unused_for_user(db: AsyncSession, user_id: str) -> int:
    """Mark all previously-issued, unused verification tokens for a user as used.

    Called before issuing a new verification token so that any prior unused
    (and potentially leaked) verification links immediately become invalid.
    Returns the number of tokens invalidated.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        select(VerificationToken)
        .where(
            VerificationToken.user_id == user_id,
            VerificationToken.used_at.is_(None),
        )
        .with_for_update(skip_locked=True)
    )
    tokens = result.scalars().all()
    for token in tokens:
        token.used_at = now
        db.add(token)
    if tokens:
        await db.flush()
    return len(tokens)


async def delete_expired(db: AsyncSession) -> int:
    result = await db.execute(
        delete(VerificationToken).where(
            VerificationToken.expires_at < datetime.now(UTC),
        )
    )
    rowcount = cast("int", getattr(result, "rowcount", 0))
    return rowcount
