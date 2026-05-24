"""Tests for the presign upload endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


async def test_presign_returns_url_and_key(client, auth_headers, authed_user):
    resp = await client.post(
        "/v1/uploads/presign",
        headers=auth_headers,
        params={"file_name": "imu_left.pb", "content_type": "application/x-protobuf"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "url" in body
    assert "key" in body
    assert f"uploads/{authed_user.id}" in body["key"]
    assert body["key"].endswith("imu_left.pb")


async def test_presign_default_content_type(client, auth_headers):
    resp = await client.post(
        "/v1/uploads/presign",
        headers=auth_headers,
        params={"file_name": "manifest.json"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "key" in body
    assert body["key"].endswith("manifest.json")
