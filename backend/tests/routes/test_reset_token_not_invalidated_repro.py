"""Repro tests — password-reset / email-verification tokens are NOT invalidated
when a new token is issued, so multiple valid tokens coexist (token-theft window).

`POST /auth/forgot-password` (routes/auth.py:271-300) and
`POST /auth/resend-verification` (routes/auth.py:380-407) create a NEW token via
`create_password_reset_token_crud(...)` / `create_verification_token_crud(...)`
but NEVER revoke / mark-used the previously-issued tokens for the same user.
`get_by_hash` (crud/password_reset_token.py:13-26, crud/verification_token.py:16-27)
filters only `used_at IS NULL AND expires_at > now` — it does not care that a
newer token exists. So ALL previously-issued, unexpired, unused tokens for a user
remain valid simultaneously.

Why this is a security bug:

  - A user who clicks "forgot password" twice (accidental double-click, or a
    second request days later) now has TWO valid reset tokens in flight. If the
    FIRST email/link was intercepted or leaked (phishing, shared inbox, log
    capture), the attacker can still reset the password with the OLD token —
    even after the user "refreshed" their reset request with the second token.
    The user believes the old link is dead; it is not.

  - Same for email verification: requesting a new verification link does not
    invalidate the old one, so a leaked old verification token can still verify
    the account.

Best practice: on issuing a new reset/verification token, revoke (mark used or
delete) all prior unused tokens for that user. The codebase already has the
mechanism (`mark_used`, `delete_expired`) but does not call it on new-issue.

The existing `test_reset_password_valid_token` (test_auth_routes.py) only tests
the single-token happy path; it never issues a SECOND token and checks the FIRST
is dead, so the multi-valid-token window never surfaces in CI.

Repro:
  1. Create a user + a FIRST reset token directly in the DB (token1).
  2. Call `POST /auth/forgot-password` (issues a SECOND token, token2).
  3. Call `POST /auth/reset-password` with token1 (the OLD one).
     RED now: 200 "Password reset successfully" — token1 is still valid.
     After the fix (revoke prior tokens on new-issue) → 400 "Invalid or
     expired reset token".

No production data mutated: in-memory SQLite test DB. The EmailService send is
swallowed inside the route (`contextlib.suppress(Exception)`, auth.py:295), so no
email mock is needed for the forgot-password call.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from app.auth.security import hash_password, hash_token
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _make_user(db_session: AsyncSession, email: str) -> User:
    user = User(email=email, hashed_password=hash_password("pass"))
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_forgot_password_invalidates_prior_reset_token_repro(
    client, db_session: AsyncSession
):
    """Issuing a NEW reset token must invalidate the OLD one.

    RED now: the old token1 still resets the password after forgot-password
    issued token2. After the fix → 400.
    """
    user = await _make_user(db_session, "reset-multi@example.com")

    # token1 — issued first (e.g. an earlier email the user thought was dead).
    token1_raw = "a" * 64
    token1 = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(token1_raw),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(token1)
    await db_session.flush()

    # User requests a NEW reset link (issues token2). forgot-password returns
    # the generic "reset link sent" regardless of email delivery (email send
    # is suppressed inside the route).
    resp = await client.post(
        "/v1/auth/forgot-password",
        json={"email": "reset-multi@example.com"},
    )
    assert resp.status_code == 200

    # After the fix, forgot-password invalidates prior unused tokens, so only
    # the freshly-issued token2 remains unused — token1 has been marked used.
    # (Before the fix, both coexisted unused: len >= 2 — that was the RED.)
    result = await db_session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    active_tokens = result.scalars().all()
    assert len(active_tokens) == 1, (
        "sanity: forgot-password invalidated prior tokens; only the new token "
        f"should remain unused, got {len(active_tokens)}"
    )

    # CONTRACT: the OLD token1 must now be INVALID (revoked by the new-issue).
    # RED now: reset with token1 succeeds (200) — token1 is still valid.
    reset_resp = await client.post(
        "/v1/auth/reset-password",
        json={"token": token1_raw, "password": "newpass123"},
    )

    assert reset_resp.status_code == 400, (
        "BUG: an OLD password-reset token (token1) is still valid AFTER a NEW "
        "reset token was issued (forgot-password). token1 should have been "
        f"revoked on new-issue. reset-password returned "
        f"{reset_resp.status_code} (expected 400) — a leaked old reset link "
        f"remains usable. Body: {reset_resp.text}"
    )
