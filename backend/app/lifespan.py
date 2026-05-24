"""Lifespan context manager for Litestar app."""

from __future__ import annotations

import contextlib
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from urllib.parse import urlparse

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


def _parse_redis_url(url: str) -> dict:
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 6379,
        "database": int((parsed.path or "/0").lstrip("/") or 0),
        "password": parsed.password or None,
    }


@asynccontextmanager
async def app_lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    """Initialize and tear down shared resources."""
    settings = get_settings()

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
    arq_cfg = _parse_redis_url(url)
    app.state.arq_pool = await create_pool(
        RedisSettings(
            host=arq_cfg["host"],
            port=arq_cfg["port"],
            database=arq_cfg["database"],
            password=arq_cfg["password"],
        )
    )

    try:
        yield
    finally:
        # Close in reverse order; use suppress to avoid cascade failures
        with contextlib.suppress(Exception):
            await app.state.arq_pool.close()
        with contextlib.suppress(Exception):
            await close_valkey_pool()
        with contextlib.suppress(Exception):
            await close_s3_clients()
        with contextlib.suppress(Exception):
            await redis_client.aclose()
