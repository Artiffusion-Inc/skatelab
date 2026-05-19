"""Litestar dependency providers."""

from __future__ import annotations

from collections.abc import AsyncGenerator  # noqa: TC003
from contextlib import asynccontextmanager

from litestar.di import Provide
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.auth.deps import get_current_user, get_verified_user
from app.config import Settings, get_settings
from app.database import async_session_factory


class DbSessionProxy:
    """Mutable proxy so tests can inject a test session."""

    _session: AsyncSession | None = None

    async def __call__(self) -> AsyncGenerator[AsyncSession, None]:
        if DbSessionProxy._session is not None:
            yield DbSessionProxy._session
            return
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except (OSError, RuntimeError, ValueError):
                await session.rollback()
                raise


db_proxy = DbSessionProxy()
db_session_proxy = DbSessionProxy()


async def provide_settings() -> Settings:
    """Provide cached app settings."""
    return get_settings()


@asynccontextmanager
async def provide_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async SQLAlchemy session with auto-commit/rollback."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except (OSError, RuntimeError, ValueError):
            await session.rollback()
            raise


@asynccontextmanager
async def provide_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Alias for provide_db to satisfy Litestar duplicate-callable detection."""
    async with provide_db() as session:
        yield session


dependencies = {
    "settings": Provide(provide_settings),
    "db": Provide(db_proxy),
    "db_session": Provide(db_session_proxy),
    "user": Provide(get_current_user),
    "verified_user": Provide(get_verified_user),
}
