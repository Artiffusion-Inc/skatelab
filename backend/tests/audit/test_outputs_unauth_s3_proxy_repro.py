"""RED repro — #513: unauthenticated S3 proxy leaks private videos.

backend/app/routes/misc.py `serve_output` (`GET /v1/outputs/{key:path}`) had NO
auth: `/v1/outputs` was in JWTAuth.exclude (backend/app/main.py:143) AND the
route had no CurrentUser dep / ownership check. `{key:path}` accepts slashes,
so any S3 key is reachable — `uploads/{victim_user_id}/{uuid}/video.mp4` streams
a victim's private video. video_key leaks via SessionResponse; user_id leaks
via coach connections. No credentials required.

Legitimate private-video access uses time-limited signed presigned URLs
(sessions.py:54); this proxy bypasses presigning entirely.

Fix (do NOT apply here): remove `/v1/outputs` from JWTAuth.exclude + add
CurrentUser + ownership prefix check (`uploads/{user.id}/`).

These tests MUST fail (RED) against the current code. Repros, not fixes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from app.auth.security import create_access_token, hash_password
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def user_a(db_session: AsyncSession) -> User:
    user = User(email="a@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def user_b(db_session: AsyncSession) -> User:
    user = User(email="b@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers_a(user_a):
    token = create_access_token(user_id=user_a.id)
    return {"Authorization": f"Bearer {token}"}


def _mock_storage(monkeypatch):
    """Mock S3 storage so the test never touches real S3. object_exists → True,
    stream_object → a body whose iter_chunks yields one chunk (async iterable).

    Litestar replaces `app.routes.misc` with a Router proxy at registration, so
    import the real module via sys.modules and patch its namespace (the route's
    `object_exists_async` / `stream_object_async` bindings live there).
    """
    import sys

    misc_mod = sys.modules["app.routes.misc"]

    class _Body:
        async def iter_chunks(self, chunk_size: int = 8192):  # noqa: ARG002
            yield b"VIDEOFETCH"

    monkeypatch.setattr(misc_mod, "object_exists_async", AsyncMock(return_value=True))
    monkeypatch.setattr(
        misc_mod,
        "stream_object_async",
        AsyncMock(return_value=(_Body(), 8, "video/mp4")),
    )


@pytest.mark.asyncio
async def test_outputs_cross_user_read_forbidden(
    client, user_a: User, user_b: User, auth_headers_a, monkeypatch
):
    """An authenticated user reading ANOTHER user's output key must get 403,
    NOT 200. RED now: 200 streams the victim's video (no ownership check).

    NOTE: the test client sets APP_SKIP_AUTH=true, so get_current_user returns
    the first active user by created_at (user_a, seeded before user_b) — i.e.
    the "attacker". The route-level ownership check (key prefix vs current user)
    is what this exercises, mirroring the gamification IDOR repro pattern. The
    middleware-exclude removal is verified by code review (in prod skip_auth is
    off, so an unauthenticated request is rejected at the JWTAuth layer before
    reaching the route).
    """
    _mock_storage(monkeypatch)
    key = f"uploads/{user_b.id}/some-uuid/private-video.mp4"
    response = await client.get(f"/v1/outputs/{key}", headers=auth_headers_a)
    assert response.status_code in (403, 404), (
        f"BUG #513: IDOR — user A read user B's private video via the S3 proxy. "
        f"expected 403/404, got {response.status_code} body={response.content[:60]!r}. "
        f"The route had no ownership check on the key prefix."
    )
