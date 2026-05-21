"""Valkey-backed task state management for video processing jobs.

Two pools per process:
- Task pool (decode_responses=True): task state, rate limiting, pub/sub PUBLISH
- Store pool (decode_responses=False): Litestar RedisStore (managed in lifespan)

Event loop safety: aioredis.Redis is bound to the event loop where created.
asyncio.to_thread() does NOT change the event loop — Redis calls stay on the
original loop. Do not create Redis instances inside to_thread callbacks.
"""

from __future__ import annotations

import json
import logging
import socket
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import redis.asyncio as aioredis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

from app.config import get_settings

logger = logging.getLogger(__name__)

TASK_KEY_PREFIX = "task:"
TASK_CANCEL_PREFIX = "task_cancel:"
TASK_EVENTS_PREFIX = "task_events:"

_pool: aioredis.Redis | None = None
_test_pool: aioredis.Redis | None = None


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _create_redis(max_connections: int = 20) -> aioredis.Redis:
    settings = get_settings()
    url = settings.valkey.url
    common: dict[str, Any] = {
        "decode_responses": True,
        "max_connections": max_connections,
        "health_check_interval": 30,
        "socket_keepalive": True,
        "socket_keepalive_options": {
            socket.TCP_KEEPIDLE: 60,
            socket.TCP_KEEPINTVL: 10,
            socket.TCP_KEEPCNT: 3,
        },
        "retry_on_timeout": True,
        "retry": Retry(retries=3, backoff=ExponentialBackoff(base=1, cap=10)),
    }
    if url:
        return aioredis.Redis.from_url(url, **common)
    return aioredis.Redis(
        host=settings.valkey.host,
        port=settings.valkey.port,
        db=settings.valkey.db,
        password=settings.valkey.password.get_secret_value() or None,
        **common,
    )


async def init_valkey_pool(max_connections: int = 20) -> None:
    global _pool  # noqa: PLW0603
    if _pool is not None:
        return
    client = _create_redis(max_connections=max_connections)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        raise
    _pool = client


def get_valkey() -> aioredis.Redis:
    if _test_pool is not None:
        return _test_pool
    if _pool is None:
        raise RuntimeError("Call init_valkey_pool() before get_valkey()")
    return _pool


def _set_test_pool(pool: aioredis.Redis | None) -> None:  # pyright: ignore[reportUnusedFunction]
    global _test_pool  # noqa: PLW0603
    _test_pool = pool


async def close_valkey_pool() -> None:
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def create_task_state(
    task_id: str,
    video_key: str,
    user_id: str | None = None,
) -> None:
    valkey = get_valkey()
    ttl = get_settings().app.task_ttl_seconds
    now = datetime.now(UTC).isoformat()
    fields: dict[str, str] = {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "video_key": video_key,
        "progress": "0.0",
        "message": "Queued",
        "created_at": now,
        "started_at": "",
        "completed_at": "",
        "error": "",
    }
    if user_id is not None:
        fields["user_id"] = user_id
    await valkey.hset(
        f"{TASK_KEY_PREFIX}{task_id}",
        mapping=fields,
    )
    await valkey.expire(f"{TASK_KEY_PREFIX}{task_id}", ttl)


async def update_progress(
    task_id: str,
    fraction: float,
    message: str,
) -> None:
    valkey = get_valkey()
    await valkey.hset(
        f"{TASK_KEY_PREFIX}{task_id}",
        mapping={"progress": str(round(fraction, 3)), "message": message},
    )


async def store_result(
    task_id: str,
    result: dict[str, Any],
) -> None:
    valkey = get_valkey()
    now = datetime.now(UTC).isoformat()
    await valkey.hset(
        f"{TASK_KEY_PREFIX}{task_id}",
        mapping={
            "status": TaskStatus.COMPLETED,
            "progress": "1.0",
            "message": "Done",
            "completed_at": now,
            "result": json.dumps(result),
        },
    )


async def store_error(
    task_id: str,
    error_message: str,
) -> None:
    valkey = get_valkey()
    now = datetime.now(UTC).isoformat()
    await valkey.hset(
        f"{TASK_KEY_PREFIX}{task_id}",
        mapping={
            "status": TaskStatus.FAILED,
            "completed_at": now,
            "error": error_message,
        },
    )


async def mark_cancelled(task_id: str) -> None:
    valkey = get_valkey()
    now = datetime.now(UTC).isoformat()
    await valkey.hset(
        f"{TASK_KEY_PREFIX}{task_id}",
        mapping={
            "status": TaskStatus.CANCELLED,
            "completed_at": now,
            "message": "Cancelled",
        },
    )


async def get_task_state(task_id: str) -> dict[str, Any] | None:
    valkey = get_valkey()
    data = await valkey.hgetall(f"{TASK_KEY_PREFIX}{task_id}")
    if not data:
        return None
    result = data.get("result")
    data["result"] = json.loads(result) if result else None
    data["progress"] = float(data.get("progress", "0"))
    return data


async def is_cancelled(task_id: str) -> bool:
    valkey = get_valkey()
    return await valkey.get(f"{TASK_CANCEL_PREFIX}{task_id}") == "1"


async def set_cancel_signal(task_id: str) -> None:
    valkey = get_valkey()
    ttl = get_settings().app.task_ttl_seconds
    await valkey.setex(f"{TASK_CANCEL_PREFIX}{task_id}", ttl, "1")


async def publish_task_event(
    task_id: str,
    data: dict,
) -> None:
    valkey = get_valkey()
    await valkey.publish(f"{TASK_EVENTS_PREFIX}{task_id}", json.dumps(data))
