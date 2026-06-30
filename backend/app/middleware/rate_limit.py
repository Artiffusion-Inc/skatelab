"""Per-endpoint rate limiting backed by Valkey."""

from __future__ import annotations

import logging

from litestar.exceptions import ClientException
from redis.exceptions import RedisError

from app.task_manager import get_valkey

logger = logging.getLogger(__name__)


async def check_rate_limit(identifier: str, max_requests: int, window_seconds: int) -> None:
    """Increment counter for identifier and raise 429 if exceeded.

    Uses Valkey INCR + EXPIRE for a fixed window.

    Fail-open on Valkey errors: rate limiting is a soft control, so a Valkey
    flap serves traffic unbounded rather than 500-ing every rate-limited route
    (auth, sessions, detect, process, uploads, connections). See #443.
    """
    valkey = get_valkey()
    key = f"rate_limit:{identifier}"
    pipe = valkey.pipeline()
    pipe.incr(key)
    pipe.ttl(key)
    try:
        count, ttl = await pipe.execute()
        if count == 1 or ttl < 0:
            await valkey.expire(key, window_seconds)
    except RedisError:
        logger.warning("rate_limiter_unavailable identifier=%s — failing open", identifier)
        return

    if count > max_requests:
        raise ClientException(
            status_code=429, detail="Rate limit exceeded. Please try again later."
        )
