"""Async database engine and session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database.url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=30,
    echo=settings.app.log_level == "DEBUG",
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
