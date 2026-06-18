"""Litestar dependency providers."""

from __future__ import annotations

from collections.abc import AsyncGenerator  # noqa: TC003

from litestar.di import Provide
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.auth.deps import get_current_user, get_verified_user
from app.config import Settings, get_settings
from app.database import async_session_factory


async def provide_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def provide_settings() -> Settings:
    """Provide cached app settings."""
    return get_settings()


dependencies = {
    "settings": Provide(provide_settings),
    "db": Provide(provide_db),
    "user": Provide(get_current_user),
    "verified_user": Provide(get_verified_user),
}
