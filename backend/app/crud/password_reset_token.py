"""PasswordResetToken CRUD operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, select

from app.models.password_reset_token import PasswordResetToken

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create(
    db: AsyncSession,
    *,
    user_id: str,
    token_hash: str,
    expires_at: datetime,
) -> PasswordResetToken:
    """Create a new password-reset token."""
    token = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(token)
    await db.flush()
    await db.refresh(token)
    return token


async def get_by_hash(db: AsyncSession, token_hash: str) -> PasswordResetToken | None:
    """Get a non-expired, non-used password-reset token by hash."""
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none()


async def mark_used(db: AsyncSession, token: PasswordResetToken) -> None:
    """Mark token as used."""
    token.used_at = datetime.now(UTC)
    db.add(token)
    await db.flush()


async def invalidate_unused_for_user(db: AsyncSession, user_id: str) -> int:
    """Mark all previously-issued, unused reset tokens for a user as used.

    Called before issuing a new reset token so that any prior unused (and
    potentially leaked) reset links immediately become invalid. Returns the
    number of tokens invalidated.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
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
    """Delete expired or used tokens. Returns number of rows deleted."""
    result = await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.expires_at < datetime.now(UTC),
        )
    )
    rowcount = cast("int", getattr(result, "rowcount", 0))
    return rowcount


async def cleanup_expired(db: AsyncSession, batch_size: int = 500) -> int:
    """Delete expired password reset tokens in batches to avoid long-held locks."""
    total_deleted = 0
    cutoff = datetime.now(UTC)
    while True:
        sub = (
            select(PasswordResetToken.id)
            .where(PasswordResetToken.expires_at < cutoff)
            .limit(batch_size)
        )
        result = await db.execute(delete(PasswordResetToken).where(PasswordResetToken.id.in_(sub)))
        await db.flush()
        count = cast("int", getattr(result, "rowcount", 0))
        total_deleted += count
        if count < batch_size:
            break
    return total_deleted
