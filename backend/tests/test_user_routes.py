"""Tests for user API routes."""

import io
from unittest.mock import patch

import pytest
from app.auth.security import hash_password
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession


async def test_get_me(client, auth_headers):
    """Test GET /api/users/me returns current user."""
    response = await client.get("/v1/users/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "user@example.com"
    assert data["display_name"] == "Test User"
    assert data["bio"] == "Skater"
    assert data["height_cm"] == 175
    assert data["weight_kg"] == 70.0


async def test_get_me_unauthorized(client):
    """Test GET /api/users/me without auth returns 401."""
    response = await client.get("/v1/users/me")
    assert response.status_code == 401


async def test_update_profile(client, auth_headers):
    """Test PATCH /api/users/me updates profile fields."""
    response = await client.patch(
        "/v1/users/me",
        json={"display_name": "New Name", "bio": "Updated bio", "height_cm": 180},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "New Name"
    assert data["bio"] == "Updated bio"
    assert data["height_cm"] == 180


async def test_update_settings(client, auth_headers):
    """Test PATCH /api/users/me/settings updates preferences."""
    response = await client.patch(
        "/v1/users/me/settings",
        json={"language": "en", "theme": "dark"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["language"] == "en"
    assert data["theme"] == "dark"


async def test_update_angular_unit(client, auth_headers):
    """Test PATCH /api/users/me/settings updates angular_unit preference."""
    resp = await client.patch(
        "/v1/users/me/settings",
        json={"angular_unit": "rpm"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["angular_unit"] == "rpm"

    # Verify persists
    resp2 = await client.get("/v1/users/me", headers=auth_headers)
    assert resp2.json()["angular_unit"] == "rpm"


async def test_upload_avatar(client, auth_headers):
    """Test POST /me/avatar uploads avatar and updates user."""
    img = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    with (
        patch("app.routes.users.upload_bytes", return_value="avatars/test-user-id.png"),
        patch(
            "app.routes.users.get_object_url",
            return_value="https://r2.example.com/avatars/test-user-id.png",
        ),
    ):
        resp = await client.post(
            "/v1/users/me/avatar",
            files={"file": ("avatar.png", img, "image/png")},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "avatar_url" in data
    assert data["avatar_url"] == "https://r2.example.com/avatars/test-user-id.png"


async def test_upload_avatar_rejects_invalid_type(client, auth_headers):
    """Test POST /me/avatar rejects unsupported content types."""
    fake_gif = io.BytesIO(b"GIF89a" + b"\x00" * 100)
    resp = await client.post(
        "/v1/users/me/avatar",
        files={"file": ("avatar.gif", fake_gif, "image/gif")},
        headers=auth_headers,
    )
    assert resp.status_code == 422
