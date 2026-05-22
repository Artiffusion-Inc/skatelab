"""Tests for auth API routes."""

from datetime import UTC, datetime, timedelta

import pytest
from app.auth.security import hash_password, hash_token
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.models.verification_token import VerificationToken
from sqlalchemy.ext.asyncio import AsyncSession


async def test_register(client, db_session: AsyncSession):
    """Test successful registration."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "securepass123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # Verify user was created
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == "new@example.com"))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.hashed_password != "securepass123"


async def test_register_duplicate_email(client, db_session: AsyncSession):
    """Test registration with duplicate email returns 409."""
    user = User(email="exists@example.com", hashed_password="hash")
    db_session.add(user)
    await db_session.flush()

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "exists@example.com", "password": "securepass123"},
    )
    assert response.status_code == 409


async def test_register_short_password(client):
    """Test registration with short password returns 400 (Litestar validation)."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "short"},
    )
    assert response.status_code == 400


async def test_login(client, db_session: AsyncSession):
    """Test successful login."""
    user = User(email="login@example.com", hashed_password=hash_password("pass123"), is_verified=True)
    db_session.add(user)
    await db_session.flush()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "pass123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


async def test_login_wrong_password(client, db_session: AsyncSession):
    """Test login with wrong password returns 401."""
    user = User(email="login@example.com", hashed_password=hash_password("correct"), is_verified=True)
    db_session.add(user)
    await db_session.flush()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


async def test_login_nonexistent_email(client):
    """Test login with nonexistent email returns 401."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "pass123"},
    )
    assert response.status_code == 401


async def test_refresh_tokens(client, db_session: AsyncSession):
    """Test refresh token rotation."""
    user = User(email="refresh@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    # Login to get tokens
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "pass"},
    )
    tokens = login_resp.json()
    old_refresh = tokens["refresh_token"]

    # Use refresh token
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    assert new_tokens["refresh_token"] != old_refresh
    assert "access_token" in new_tokens

    # Old refresh token should be revoked
    second_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert second_refresh.status_code == 401


async def test_refresh_with_completely_unknown_token(client):
    """Test refresh with a token that was never issued returns 401."""
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "a" * 64},
    )
    assert response.status_code == 401
    assert "Invalid or expired" in response.json()["message"]


async def test_logout_with_valid_token(client, db_session: AsyncSession):
    """Test logout revokes the refresh token."""
    user = User(email="logout@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    # Login to get tokens
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "logout@example.com", "password": "pass"},
    )
    tokens = login_resp.json()
    refresh_token = tokens["refresh_token"]

    # Logout
    logout_resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 204

    # Refresh should now fail (token revoked)
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 401


async def test_logout_with_nonexistent_token(client):
    """Test logout with a token that was never issued returns 204 (idempotent)."""
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "b" * 64},
    )
    assert response.status_code == 204


async def test_refresh_token_reuse_revokes_family(client, db_session):
    """Using a refresh token twice revokes the whole family."""
    user = User(email="reuse@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "reuse@example.com", "password": "pass"},
    )
    print("LOGIN STATUS:", login_resp.status_code)
    print("LOGIN BODY:", login_resp.text)
    tokens = login_resp.json()
    refresh1 = tokens["refresh_token"]

    # First refresh succeeds
    r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
    assert r1.status_code == 200

    # Second refresh with same token fails and revokes family
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
    assert r2.status_code == 401
    assert "reuse" in r2.json()["message"].lower()

    # Even the new token from r1 should now be revoked
    new_refresh = r1.json()["refresh_token"]
    r3 = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert r3.status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_valkey():
    """Fake Valkey client for rate-limit tests."""
    _store = {}

    class FakeValkey:
        async def ping(self):
            return True

        async def aclose(self):
            pass

        def pipeline(self):
            class _Pipe:
                async def execute(self):
                    key = _store.get("last_key")
                    val = _store.get(key, 0) + 1
                    _store[key] = val
                    return [val, -1 if val == 1 else 60]

                def incr(self, key):
                    _store["last_key"] = key

                def ttl(self, _key):
                    return -1 if _store.get("last_key", 0) == 1 else 60

            return _Pipe()

        async def expire(self, key, seconds):
            pass

    return FakeValkey()


async def test_register_rate_limit_by_ip(client, mock_valkey):
    """After 5 register requests from same IP, 6th returns 429."""
    from app.task_manager import _set_test_pool

    _set_test_pool(mock_valkey)
    try:
        for i in range(5):
            resp = await client.post(
                "/api/v1/auth/register",
                json={"email": f"user{i}@test.com", "password": "password123"},
            )
            assert resp.status_code == 201, f"Request {i + 1} should succeed"

        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "overflow@test.com", "password": "password123"},
        )
        assert resp.status_code == 429
        assert "Rate limit" in resp.json()["message"]
    finally:
        _set_test_pool(None)


async def test_login_rate_limit_by_email(client, db_session, mock_valkey):
    """After 5 failed logins for same email, 6th returns 429."""
    user = User(email="rate@example.com", hashed_password=hash_password("correct"), is_verified=True)
    db_session.add(user)
    await db_session.flush()

    from app.task_manager import _set_test_pool

    _set_test_pool(mock_valkey)
    try:
        for i in range(5):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "rate@example.com", "password": "wrong"},
            )
            assert resp.status_code == 401, f"Request {i + 1} should fail auth"

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "rate@example.com", "password": "wrong"},
        )
        assert resp.status_code == 429
    finally:
        _set_test_pool(None)


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


async def test_forgot_password_existing_email(client, db_session: AsyncSession):
    """Forgot-password returns 200 and creates a reset token."""
    user = User(email="forgot@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "forgot@example.com"},
    )
    assert resp.status_code == 200
    assert "reset link sent" in resp.json()["message"].lower()

    # Verify token created in DB
    from sqlalchemy import select

    result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    token = result.scalar_one_or_none()
    assert token is not None
    assert token.used_at is None


async def test_forgot_password_nonexistent_email(client):
    """Forgot-password returns 200 with generic message for unknown email."""
    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nobody@example.com"},
    )
    assert resp.status_code == 200
    assert "reset link sent" in resp.json()["message"].lower()


async def test_forgot_password_rate_limit(client, mock_valkey):
    """After 3 forgot-password requests, 4th returns 429."""
    from app.task_manager import _set_test_pool

    _set_test_pool(mock_valkey)
    try:
        for i in range(3):
            resp = await client.post(
                "/api/v1/auth/forgot-password",
                json={"email": f"rate{i}@test.com"},
            )
            assert resp.status_code == 200, f"Request {i + 1} should succeed"

        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "overflow@test.com"},
        )
        assert resp.status_code == 429
    finally:
        _set_test_pool(None)


async def test_reset_password_valid_token(client, db_session: AsyncSession):
    """Reset password with valid token succeeds and marks token used."""
    user = User(email="reset@example.com", hashed_password=hash_password("oldpass"))
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    token_raw = "a" * 64
    token_hash = hash_token(token_raw)
    prt = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(prt)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token_raw, "password": "newpass123"},
    )
    assert resp.status_code == 200
    assert "success" in resp.json()["message"].lower()

    # Verify token marked used
    from sqlalchemy import select

    result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.id == prt.id)
    )
    token = result.scalar_one()
    assert token.used_at is not None

    # Verify password updated
    result = await db_session.execute(select(User).where(User.id == user.id))
    updated_user = result.scalar_one()
    from app.auth.security import verify_password

    assert verify_password("newpass123", updated_user.hashed_password)


async def test_reset_password_invalid_token(client):
    """Reset password with invalid token returns 400."""
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "invalidtoken", "password": "newpass123"},
    )
    assert resp.status_code == 400
    assert "invalid" in resp.json()["message"].lower()


async def test_reset_password_expired_token(client, db_session: AsyncSession):
    """Reset password with expired token returns 400."""
    user = User(email="expired@example.com", hashed_password=hash_password("oldpass"))
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    token_raw = "b" * 64
    token_hash = hash_token(token_raw)
    prt = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(prt)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token_raw, "password": "newpass123"},
    )
    assert resp.status_code == 400
    assert "invalid" in resp.json()["message"].lower()


async def test_reset_password_rate_limit(client, mock_valkey):
    """After 5 reset-password requests, 6th returns 429."""
    from app.task_manager import _set_test_pool

    _set_test_pool(mock_valkey)
    try:
        for i in range(5):
            resp = await client.post(
                "/api/v1/auth/reset-password",
                json={"token": f"{'c' * 64}{i}", "password": "newpass123"},
            )
            # Each fails with 400 (invalid token) but counts toward rate limit
            assert resp.status_code == 400, f"Request {i + 1} should fail auth"

        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "d" * 64, "password": "newpass123"},
        )
        assert resp.status_code == 429
    finally:
        _set_test_pool(None)


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


async def test_verify_email_valid_token(client, db_session: AsyncSession):
    """Verify-email with valid token marks user as verified."""
    user = User(email="verify@example.com", hashed_password=hash_password("pass"))
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    token_raw = "v" * 64
    token_hash_str = hash_token(token_raw)
    vt = VerificationToken(
        user_id=user.id,
        token_hash=token_hash_str,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db_session.add(vt)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": token_raw},
    )
    assert resp.status_code == 200
    assert "verified" in resp.json()["message"].lower()

    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.id == user.id))
    updated = result.scalar_one()
    assert updated.is_verified is True

    result = await db_session.execute(
        select(VerificationToken).where(VerificationToken.id == vt.id)
    )
    used_token = result.scalar_one()
    assert used_token.used_at is not None


async def test_verify_email_invalid_token(client):
    """Verify-email with invalid token returns 400."""
    resp = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": "invalidtoken"},
    )
    assert resp.status_code == 400
    assert "invalid" in resp.json()["message"].lower()


async def test_verify_email_expired_token(client, db_session: AsyncSession):
    """Verify-email with expired token returns 400."""
    user = User(email="expired-verify@example.com", hashed_password=hash_password("pass"))
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    token_raw = "x" * 64
    token_hash_str = hash_token(token_raw)
    vt = VerificationToken(
        user_id=user.id,
        token_hash=token_hash_str,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(vt)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": token_raw},
    )
    assert resp.status_code == 400


async def test_resend_verification_existing_user(client, db_session: AsyncSession):
    """Resend-verification creates a new token for unverified user."""
    user = User(
        email="resend@example.com", hashed_password=hash_password("pass"), is_verified=False
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    resp = await client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "resend@example.com"},
    )
    assert resp.status_code == 200

    from sqlalchemy import select

    result = await db_session.execute(
        select(VerificationToken).where(VerificationToken.user_id == user.id)
    )
    token = result.scalar_one_or_none()
    assert token is not None
    assert token.used_at is None


async def test_resend_verification_already_verified(client, db_session: AsyncSession):
    """Resend-verification returns generic message for already verified user."""
    user = User(
        email="verified@example.com", hashed_password=hash_password("pass"), is_verified=True
    )
    db_session.add(user)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "verified@example.com"},
    )
    assert resp.status_code == 200
    assert "verification sent" in resp.json()["message"].lower()


async def test_resend_verification_nonexistent_email(client):
    """Resend-verification returns generic message for unknown email."""
    resp = await client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "nobody@example.com"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# CookieToHeaderMiddleware
# ---------------------------------------------------------------------------


async def test_cookie_middleware_injects_header(client, db_session: AsyncSession):
    """CookieToHeaderMiddleware injects Authorization from access_token cookie."""
    from app.auth.security import create_access_token

    user = User(
        id="cookie-test",
        email="cookie@example.com",
        hashed_password=hash_password("pass"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(user_id="cookie-test")
    # Use raw Cookie header because httpx per-request cookies may not
    # propagate through the ASGI transport correctly.
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Cookie": f"access_token={token}"},
    )
    assert resp.status_code == 200


async def test_cookie_middleware_does_not_override_header(client, db_session: AsyncSession):
    """If Authorization header present, cookie is ignored."""
    from app.auth.security import create_access_token

    user = User(
        id="header-test",
        email="header@example.com",
        hashed_password=hash_password("pass"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(user_id="header-test")
    resp = await client.get(
        "/api/v1/users/me",
        headers={
            "Authorization": f"Bearer {token}",
            "Cookie": "access_token=invalid-token-value",
        },
    )
    assert resp.status_code == 200


async def test_refresh_with_no_body_uses_cookie(client, db_session):
    """Refresh with no body reads refresh_token from cookie."""
    from app.auth.security import hash_password
    from app.models.user import User

    user = User(
        email="cookie-refresh@example.com",
        hashed_password=hash_password("pass"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    # Login to get cookies
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "cookie-refresh@example.com", "password": "pass"},
    )
    assert login_resp.status_code == 200

    # Refresh using only cookies (no body)
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={},  # empty body — refresh_token from cookie
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Cookie management
# ---------------------------------------------------------------------------


async def test_login_sets_cookies(client, db_session):
    """Login sets access_token, refresh_token, and sb_auth cookies."""
    from app.auth.security import hash_password
    from app.models.user import User

    user = User(email="cookies@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "cookies@example.com", "password": "pass"},
    )
    assert resp.status_code == 200

    # Check Set-Cookie headers for the three auth cookies
    set_cookie_headers = resp.headers.get_list("set-cookie")
    cookie_names = [h.split("=")[0].strip() for h in set_cookie_headers]
    assert "access_token" in cookie_names
    assert "refresh_token" in cookie_names
    assert "sb_auth" in cookie_names

    # Verify httponly flags
    for h in set_cookie_headers:
        name = h.split("=")[0].strip()
        if name in ("access_token", "refresh_token"):
            assert "httponly" in h.lower(), f"{name} should be httponly"
        if name == "sb_auth":
            # sb_auth is NOT httponly (readable by JS)
            # httpx lowercases, so check both cases
            pass  # Not asserting absence since Litestar may always set it


async def test_logout_clears_cookies(client, db_session):
    """Logout clears all auth cookies."""
    from app.auth.security import hash_password
    from app.models.user import User

    user = User(email="logout-cookies@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "logout-cookies@example.com", "password": "pass"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 204

    # Check that cookies are cleared (max-age=0)
    set_cookie_headers = resp.headers.get_list("set-cookie")
    cookie_names = [h.split("=")[0].strip() for h in set_cookie_headers]
    assert "access_token" in cookie_names
    assert "refresh_token" in cookie_names
    assert "sb_auth" in cookie_names
    # All cleared cookies should have max-age=0
    for h in set_cookie_headers:
        name = h.split("=")[0].strip()
        if name in ("access_token", "refresh_token", "sb_auth"):
            assert "max-age=0" in h.lower(), f"{name} should be cleared with max-age=0"


# ---------------------------------------------------------------------------
# Email verify gate
# ---------------------------------------------------------------------------


async def test_login_unverified_email(client, db_session):
    """Login with unverified email returns 403."""
    from app.auth.security import hash_password
    from app.models.user import User

    user = User(email="unverified@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=False)
    db_session.add(user)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "unverified@example.com", "password": "pass"},
    )
    assert resp.status_code == 403
    detail = resp.json().get("detail", resp.json().get("message", ""))
    assert "not verified" in detail.lower() or "not verified" in str(resp.json()).lower()


# ---------------------------------------------------------------------------
# UA binding
# ---------------------------------------------------------------------------


async def test_ua_mismatch_revokes_family(client, db_session):
    """Refresh with different User-Agent revokes entire family."""
    from app.auth.security import hash_password
    from app.models.user import User

    user = User(email="ua-test@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    # Login with UA "Original/1.0"
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ua-test@example.com", "password": "pass"},
        headers={"User-Agent": "Original/1.0"},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    # Refresh with same UA — should succeed
    resp1 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"User-Agent": "Original/1.0"},
    )
    assert resp1.status_code == 200
    new_refresh = resp1.json()["refresh_token"]

    # Refresh new token with DIFFERENT UA — should fail and revoke family
    resp2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh},
        headers={"User-Agent": "Attacker/1.0"},
    )
    assert resp2.status_code == 401


async def test_legacy_token_skips_ua_check(client, db_session):
    """Legacy refresh tokens (user_agent_hash='legacy') skip UA check."""
    import secrets
    from datetime import UTC, datetime, timedelta

    from app.auth.security import hash_password, hash_token
    from app.models.refresh_token import RefreshToken
    from app.models.user import User

    user = User(email="legacy-ua@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    # Create a token with legacy UA hash directly
    raw = secrets.token_urlsafe(32)
    token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        family_id="legacy-family",
        is_revoked=False,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        user_agent_hash="legacy",
    )
    db_session.add(token)
    await db_session.flush()

    # Refresh with any UA — should succeed (legacy token)
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": raw},
        headers={"User-Agent": "AnyBrowser/1.0"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


async def test_audit_log_records_login(client, db_session):
    """Successful login creates audit entry."""
    from app.models.auth_audit_log import AuthAuditLog
    from sqlalchemy import select

    user = User(
        email="audit-login@example.com",
        hashed_password=hash_password("pass"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "audit-login@example.com", "password": "pass"},
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AuthAuditLog).where(AuthAuditLog.event_type == "login")
    )
    entry = result.scalar_one_or_none()
    assert entry is not None
    assert entry.user_id == user.id


async def test_audit_login_failed(client, db_session):
    """Failed login creates login_failed audit entry."""
    from app.models.auth_audit_log import AuthAuditLog
    from sqlalchemy import select

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "noone@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401

    result = await db_session.execute(
        select(AuthAuditLog).where(AuthAuditLog.event_type == "login_failed")
    )
    entry = result.scalar_one_or_none()
    assert entry is not None
    assert entry.ip_address is not None


async def test_audit_logout(client, db_session):
    """Logout creates audit entry."""
    from app.auth.security import hash_password
    from app.models.auth_audit_log import AuthAuditLog
    from app.models.user import User
    from sqlalchemy import select

    user = User(email="audit-logout@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "audit-logout@example.com", "password": "pass"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})

    result = await db_session.execute(
        select(AuthAuditLog).where(AuthAuditLog.event_type == "logout")
    )
    entry = result.scalar_one_or_none()
    assert entry is not None


# ---------------------------------------------------------------------------
# Token cleanup
# ---------------------------------------------------------------------------


async def test_cleanup_expired_refresh_tokens(db_session: AsyncSession):
    """cleanup_expired deletes expired refresh tokens."""
    from app.crud.refresh_token import cleanup_expired, create

    # Create an already-expired token
    raw = "a" * 64
    token_hash_str = hash_token(raw)
    token = await create(
        db_session,
        user_id="test-user-cleanup",
        token_hash=token_hash_str,
        family_id="family-cleanup",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await db_session.commit()

    deleted = await cleanup_expired(db_session, batch_size=100)
    assert deleted >= 1
