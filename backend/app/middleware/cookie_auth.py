"""ASGI middleware: reads access_token httpOnly cookie and injects Authorization header."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import unquote

from litestar.datastructures import MutableScopeHeaders
from litestar.types.empty import Empty
from litestar.utils.scope.state import ScopeState

if TYPE_CHECKING:
    from litestar.types import ASGIApp, Receive, Scope, Send


def _invalidate_headers_cache(scope: Scope) -> None:
    """Invalidate the ScopeState headers cache so downstream middleware sees the new header.

    Litestar's internal CORS middleware (and others) may create a ScopeState and cache
    the Headers object before our user middleware runs. Since we modify scope["headers"]
    after that cache is populated, we must reset the cached headers to Empty so
    Headers.from_scope re-reads the raw scope["headers"] list.
    """
    base_state = scope.get("state")
    if not base_state:
        return
    for val in base_state.values():
        if isinstance(val, ScopeState):
            val.headers = Empty  # type: ignore[assignment]
            break


class CookieToHeaderMiddleware:
    """If no Authorization header present, map access_token cookie to Bearer header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            has_auth = any(k == b"authorization" for k, _ in scope.get("headers", []))
            if not has_auth:
                cookie_value = None
                for k, v in scope.get("headers", []):
                    if k == b"cookie":
                        cookie_value = v.decode("latin-1")
                        break
                if cookie_value:
                    for raw_part in cookie_value.split(";"):
                        part = raw_part.strip()
                        if "=" in part:
                            name, value = part.split("=", 1)
                            if name.strip() == "access_token":
                                headers = MutableScopeHeaders(scope=scope)
                                headers["authorization"] = f"Bearer {unquote(value.strip())}"
                                _invalidate_headers_cache(scope)
                                break
        await self.app(scope, receive, send)
