"""Repro tests — reset-password does not revoke active refresh tokens (#843).

``POST /auth/reset-password`` (routes/auth.py) changes the password and marks
the reset token used, but it does NOT revoke the user's active refresh tokens.
A stolen refresh token keeps minting access tokens via ``/auth/refresh`` even
after the victim reset their password — the canonical "credential leaked"
action fails to kick the attacker out.

Fix (#843): add ``revoke_all_for_user(db, user_id)`` to crud/refresh_token.py
(bulk UPDATE of non-revoked rows for the user) and call it in ``reset_password``
after the password is updated.

Tests:
  - behavioral: login (get refresh) → reset-password → ``/auth/refresh`` with
    the OLD refresh must return 401 (token revoked), not 200.
  - behavioral: the refresh row is ``is_revoked=True`` in the DB after reset.
  - source-asserting: ``revoke_all_for_user`` exists in crud; the route calls
    it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from app.auth.security import hash_password, hash_token
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _make_reset_token(db_session: AsyncSession, user: User) -> str:
    token_raw = "r" * 64
    prt = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(token_raw),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(prt)
    await db_session.flush()
    return token_raw


@pytest.mark.asyncio
async def test_reset_password_revokes_active_refresh_token(client, db_session: AsyncSession):
    """#843: a refresh token issued BEFORE the password reset must be revoked
    by the reset — ``/auth/refresh`` with the old token returns 401.

    RED without the fix: the old refresh token still works (200, new access
    token minted for the attacker). GREEN with the fix: 401.
    """
    user = User(
        email="resetvictim@example.com",
        hashed_password=hash_password("oldpass123"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    login = await client.post(
        "/v1/auth/login",
        json={"email": "resetvictim@example.com", "password": "oldpass123"},
    )
    assert login.status_code == 200, login.text
    old_refresh = login.json()["refresh_token"]

    token_raw = await _make_reset_token(db_session, user)
    reset = await client.post(
        "/v1/auth/reset-password",
        json={"token": token_raw, "password": "newpass123"},
    )
    assert reset.status_code == 200, reset.text

    refresh_resp = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )

    assert refresh_resp.status_code == 401, (
        f"#843: stolen refresh token survived password reset — "
        f"/auth/refresh returned {refresh_resp.status_code} (expected 401). "
        f"The reset-password path does not revoke active refresh tokens. "
        f"Body: {refresh_resp.text}"
    )


@pytest.mark.asyncio
async def test_reset_password_marks_refresh_row_revoked_in_db(client, db_session: AsyncSession):
    """#843: the refresh-token row issued before reset must be is_revoked=True
    in the DB after the reset completes.
    """
    user = User(
        email="resetrow@example.com",
        hashed_password=hash_password("oldpass123"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    login = await client.post(
        "/v1/auth/login",
        json={"email": "resetrow@example.com", "password": "oldpass123"},
    )
    assert login.status_code == 200, login.text
    old_refresh = login.json()["refresh_token"]

    token_raw = await _make_reset_token(db_session, user)
    reset = await client.post(
        "/v1/auth/reset-password",
        json={"token": token_raw, "password": "newpass123"},
    )
    assert reset.status_code == 200, reset.text

    token_hash = hash_token(old_refresh)
    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    row = result.scalar_one_or_none()
    assert row is not None, "refresh token row should exist after login"
    assert row.is_revoked is True, (
        f"#843: refresh token row is_revoked={row.is_revoked} after password "
        f"reset (expected True) — reset-password does not bulk-revoke."
    )


def test_source_revoke_all_for_user_exists_in_crud():
    """#843: crud/refresh_token.py must expose revoke_all_for_user(db, user_id)."""
    import inspect

    from app.crud.refresh_token import revoke_all_for_user

    sig = inspect.signature(revoke_all_for_user)
    assert "user_id" in sig.parameters, "#843: revoke_all_for_user must take a user_id parameter."
    src = inspect.getsource(revoke_all_for_user)
    assert "RefreshToken.is_revoked" in src
    assert "user_id" in src


def test_source_reset_password_route_calls_revoke_all_for_user():
    """#843: the reset_password route body must call revoke_all_for_user."""
    from pathlib import Path

    route_path = Path(__import__("app.routes.auth", fromlist=["__file__"]).__file__)
    src = route_path.read_text(encoding="utf-8")
    assert "revoke_all_for_user" in src, (
        "#843: reset_password route must call revoke_all_for_user to bulk-revoke "
        "active refresh tokens on password reset."
    )
