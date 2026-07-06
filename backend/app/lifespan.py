"""Lifespan context manager for Litestar app."""

from __future__ import annotations

import contextlib
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from litestar.stores.redis import RedisStore
from litestar.stores.registry import StoreRegistry

from app.config import get_settings
from app.task_manager import close_valkey_pool, init_valkey_pool

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from litestar import Litestar

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    """Initialize and tear down shared resources."""
    settings = get_settings()

    # 0. Security check: reject default JWT secret in production
    if settings.jwt.is_default_secret and not settings.app.skip_auth:
        logger.critical(
            "JWT_SECRET_KEY is set to the default value. "
            "Set JWT_SECRET_KEY env var to a random secret in production."
        )
        if settings.sentry.environment != "development":
            msg = "Refusing to start with default JWT secret in non-dev environment"
            raise RuntimeError(msg)

    # 1. Valkey pool — non-fatal: app starts in degraded mode if unavailable
    try:
        await init_valkey_pool(max_connections=20)
    except (ConnectionError, OSError) as e:
        logger.warning("Valkey pool init failed — task tracking disabled: %s", e)

    # 2. S3 async client — eager init to fail fast on bad credentials
    from app.storage import close_s3_clients, get_s3_async_client

    try:
        await get_s3_async_client()
    except Exception as e:
        logger.warning("S3 client init failed: %s", e)

    # 3. Response cache store (separate pool, decode_responses=False)
    url = settings.valkey.build_url()
    redis_client = aioredis.Redis.from_url(url, decode_responses=False)
    root_store = RedisStore(redis=redis_client)
    app.stores = StoreRegistry(default_factory=root_store.with_namespace)

    # 4. arq pool
    # #644: mirror the valkey pool pattern (line 43-46) — non-fatal.
    # If Valkey is down at startup, the app starts in degraded mode
    # (no task processing). Pre-fix: the finally block called
    # `app.state.arq_pool.close()` on an uninitialized attribute,
    # raising AttributeError AFTER the real ConnectionError, masking
    # the actual failure in logs.
    try:
        app.state.arq_pool = await create_pool(RedisSettings(**settings.valkey.redis_kwargs()))
    except (ConnectionError, OSError) as e:
        logger.warning("arq pool init failed — task processing disabled: %s", e)
        app.state.arq_pool = None

    try:
        yield
    finally:
        # Close in reverse order; use suppress to avoid cascade failures
        if app.state.arq_pool is not None:
            with contextlib.suppress(Exception):
                await app.state.arq_pool.close()
        with contextlib.suppress(Exception):
            await close_valkey_pool()
        with contextlib.suppress(Exception):
            await close_s3_clients()
        with contextlib.suppress(Exception):
            await redis_client.aclose()
