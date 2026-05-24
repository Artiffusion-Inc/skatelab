"""Tests for auth cookie domain and path attributes."""

import pytest
from app.auth.security import hash_password
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession


async def test_auth_cookies_have_domain(client, db_session: AsyncSession):
    """Auth cookies set domain=skatelab.ru for cross-subdomain sharing."""
    user = User(
        email="cookie@example.com",
        hashed_password=hash_password("pass123"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    response = await client.post(
        "/v1/auth/login",
        json={"email": "cookie@example.com", "password": "pass123"},
    )
    assert response.status_code == 200

    # httpx returns all Set-Cookie values via get_list
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert len(set_cookie_headers) > 0, "No Set-Cookie headers found"

    auth_cookies = [
        h
        for h in set_cookie_headers
        if any(name in h for name in ("access_token", "refresh_token", "sb_auth"))
    ]
    assert len(auth_cookies) == 3, (
        f"Expected 3 auth cookies, got {len(auth_cookies)}: {auth_cookies}"
    )

    for header in auth_cookies:
        header_lower = header.lower()
        assert "domain=skatelab.ru" in header_lower or "domain=.skatelab.ru" in header_lower, (
            f"Cookie missing domain=skatelab.ru: {header}"
        )


async def test_refresh_token_cookie_path_is_root(client, db_session: AsyncSession):
    """Refresh token cookie path is / (covers /v1/auth and any future prefixes)."""
    user = User(
        email="cookie2@example.com",
        hashed_password=hash_password("pass123"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    response = await client.post(
        "/v1/auth/login",
        json={"email": "cookie2@example.com", "password": "pass123"},
    )
    assert response.status_code == 200

    set_cookie_headers = response.headers.get_list("set-cookie")
    refresh_cookies = [h for h in set_cookie_headers if "refresh_token" in h]
    assert len(refresh_cookies) >= 1, f"No refresh_token cookie found: {set_cookie_headers}"

    # refresh_token path should be "/" not "/v1/auth"
    for header in refresh_cookies:
        assert "path=/v1/auth" not in header.lower(), (
            f"refresh_token cookie still has narrow path: {header}"
        )
        # Ensure path=/ is present (root path)
        assert "path=/" in header.lower(), f"refresh_token cookie missing path=/: {header}"


async def test_logout_clears_cookies_with_correct_domain(client, db_session: AsyncSession):
    """Logout clears cookies with matching domain so browser actually deletes them."""
    user = User(
        email="cookie3@example.com",
        hashed_password=hash_password("pass123"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    # Login first
    login_resp = await client.post(
        "/v1/auth/login",
        json={"email": "cookie3@example.com", "password": "pass123"},
    )
    assert login_resp.status_code == 200

    # Logout
    logout_resp = await client.post(
        "/v1/auth/logout",
        json={"refresh_token": "unused"},
    )
    assert logout_resp.status_code == 204

    set_cookie_headers = logout_resp.headers.get_list("set-cookie")
    clear_cookies = [
        h
        for h in set_cookie_headers
        if any(name in h for name in ("access_token", "refresh_token", "sb_auth"))
    ]
    assert len(clear_cookies) == 3, (
        f"Expected 3 clear cookies, got {len(clear_cookies)}: {clear_cookies}"
    )

    for header in clear_cookies:
        header_lower = header.lower()
        assert "domain=skatelab.ru" in header_lower or "domain=.skatelab.ru" in header_lower, (
            f"Clear cookie missing domain=skatelab.ru: {header}"
        )
        assert "max-age=0" in header_lower, f"Clear cookie missing max-age=0: {header}"
