"""PostHog analytics — lazy singleton, fire-and-forget.

disabled=True when no API key → all calls are no-ops.
"""

from __future__ import annotations

import logging
import signal

from posthog import Posthog

from app.config import get_settings

logger = logging.getLogger(__name__)

_posthog: Posthog | None = None


def get_posthog() -> Posthog:
    global _posthog  # noqa: PLW0603
    if _posthog is not None:
        return _posthog
    settings = get_settings()
    api_key = settings.posthog.api_key.get_secret_value()
    if not api_key:
        _posthog = Posthog(project_api_key="", host="http://localhost:0", disabled=True)
        return _posthog
    _posthog = Posthog(
        project_api_key=api_key,
        host=settings.posthog.host,
        flush_at=50,
        flush_interval=10,
        max_queue_size=10000,
        max_retries=3,
        timeout=10,
        on_error=lambda e, _batch: logger.warning("PostHog upload failed: %s", e),
        send=True,
        gzip=True,
    )
    return _posthog


def capture_event(event: str, distinct_id: str, properties: dict | None = None) -> None:
    """Fire-and-forget. Never raises. O(1) queue put — non-blocking."""
    ph = get_posthog()
    if ph.disabled:
        return
    try:
        ph.capture(event=event, distinct_id=distinct_id, properties=properties or {})
    except Exception as e:
        logger.warning("PostHog capture failed for %s: %s", event, e)


def shutdown_posthog() -> None:
    """Flush + stop consumer threads. 5s timeout to prevent hanging."""
    global _posthog
    if _posthog is None:
        return
    try:
        old_handler = signal.signal(signal.SIGALRM, lambda *_: None)
        signal.alarm(5)
        try:
            _posthog.shutdown()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except Exception as e:
        logger.warning("PostHog shutdown error: %s", e)
    _posthog = None
