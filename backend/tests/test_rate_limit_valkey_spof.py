"""RED repro: Valkey-down rate-limit SPOF crashes all auth (#443).

`check_rate_limit` (rate_limit.py) had no try/except around the Valkey
pipeline, so a connection flap raised `redis.exceptions.ConnectionError`
unhandled — Litestar turns that into a 500 on every rate-limited route.

Inject a broken Valkey pool via the existing `_set_test_pool` hook and assert
auth routes return a graceful handled status (not 500).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import redis.exceptions
from app.task_manager import _set_test_pool


class _BrokenValkey:
    """Valkey client whose pipeline().execute() raises on connection (down)."""

    def pipeline(self):
        pipe = MagicMock()

        async def _execute():
            raise redis.exceptions.ConnectionError("Connection refused")

        pipe.execute = _execute
        return pipe

    async def expire(self, key, seconds):  # pragma: no cover - should not be reached
        raise redis.exceptions.ConnectionError("Connection refused")


async def test_register_survives_valkey_down(client):
    _set_test_pool(_BrokenValkey())
    try:
        response = await client.post(
            "/v1/auth/register",
            json={"email": "spof@example.com", "password": "securepass123"},
        )
        assert response.status_code in {200, 201, 429, 503}, (
            f"Valkey-down rate-limit SPOF: POST /v1/auth/register returned "
            f"{response.status_code} (unhandled) when Valkey is down. "
            f"Expected a graceful handled response in {{200, 201, 429, 503}}. "
            f"Body: {response.text}"
        )
    finally:
        _set_test_pool(None)


async def test_login_survives_valkey_down(client, db_session):
    from app.auth.security import hash_password
    from app.models.user import User

    db_session.add(
        User(
            email="login_spof@example.com",
            hashed_password=hash_password("pass123"),
            is_verified=True,
        )
    )
    await db_session.flush()

    _set_test_pool(_BrokenValkey())
    try:
        response = await client.post(
            "/v1/auth/login",
            json={"email": "login_spof@example.com", "password": "pass123"},
        )
        assert response.status_code in {200, 201, 429, 503}, (
            f"Valkey-down rate-limit SPOF: POST /v1/auth/login returned "
            f"{response.status_code} (unhandled) when Valkey is down. "
            f"Body: {response.text}"
        )
    finally:
        _set_test_pool(None)
