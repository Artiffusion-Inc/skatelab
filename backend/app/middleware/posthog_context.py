"""Extract PostHog tracing headers from frontend API requests.

Stores distinct_id + session_id in request.state for
session replay correlation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litestar.types import ASGIApp, Receive, Scope, Send


class PostHogContextMiddleware:
    """Extract X-POSTHOG-DISTINCT-ID and X-POSTHOG-SESSION-ID headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            for k, v in scope.get("headers", []):
                if k == b"x-posthog-distinct-id":
                    scope.setdefault("state", {})["posthog_distinct_id"] = v.decode("latin-1")
                elif k == b"x-posthog-session-id":
                    scope.setdefault("state", {})["posthog_session_id"] = v.decode("latin-1")
        await self.app(scope, receive, send)
