"""Tests for misc routes (health check, S3 output streaming).

#513: /v1/outputs now requires auth + ownership (the key must live under the
caller's `uploads/{user_id}/` prefix). serve_output tests therefore send auth
headers and use the authed user's own upload key. Health remains public.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from app.models.user import User
    from litestar.testing import AsyncTestClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncTestClient):
    """GET /health returns {"status": "ok"} without authentication."""
    response = await client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    # #770: valkey boolean no longer exposed to anonymous
    assert "valkey" not in data


@pytest.mark.asyncio
async def test_serve_output_not_found(client: AsyncTestClient, authed_user: User, auth_headers):
    """GET /outputs/{key} returns 404 when object does not exist in S3."""
    key = f"uploads/{authed_user.id}/nonexistent/video.mp4"
    fake_error = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}},
        "GetObject",
    )
    with patch(
        "app.routes.misc.stream_object_async",
        new_callable=AsyncMock,
        side_effect=fake_error,
    ):
        response = await client.get(f"/v1/outputs/{key}", headers=auth_headers)
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["message"].lower() or data["message"] == "File not found"


@pytest.mark.asyncio
async def test_serve_output_streams_file(client: AsyncTestClient, authed_user: User, auth_headers):
    """GET /outputs/{key} streams the file from S3 with correct content-type."""

    async def fake_iter_chunks(*, chunk_size):
        yield b"chunk1"
        yield b"chunk2"
        yield b"chunk3"

    mock_body = MagicMock()
    mock_body.iter_chunks = fake_iter_chunks

    key = f"uploads/{authed_user.id}/session123/result.mp4"
    with patch(
        "app.routes.misc.stream_object_async",
        new_callable=AsyncMock,
        return_value=(mock_body, 999, "application/octet-stream"),
    ):
        response = await client.get(f"/v1/outputs/{key}", headers=auth_headers)

    assert response.status_code == 200
    assert response.content == b"chunk1chunk2chunk3"
    assert response.headers["content-type"] == "video/mp4"


@pytest.mark.asyncio
async def test_serve_output_content_type_by_extension(
    client: AsyncTestClient, authed_user: User, auth_headers
):
    """GET /outputs/{key} uses extension-based content type from safe whitelist."""

    async def fake_iter_chunks(*, chunk_size):
        yield b"csv,data"

    mock_body = MagicMock()
    mock_body.iter_chunks = fake_iter_chunks

    key = f"uploads/{authed_user.id}/session123/metrics.csv"
    with patch(
        "app.routes.misc.stream_object_async",
        new_callable=AsyncMock,
        return_value=(mock_body, 9, "application/octet-stream"),
    ):
        response = await client.get(f"/v1/outputs/{key}", headers=auth_headers)

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_serve_output_unknown_extension_forces_octet_stream(
    client: AsyncTestClient, authed_user: User, auth_headers
):
    """#772: unknown extensions get application/octet-stream + Content-Disposition: attachment."""

    async def fake_iter_chunks(*, chunk_size):
        yield b"bin"

    mock_body = MagicMock()
    mock_body.iter_chunks = fake_iter_chunks

    key = f"uploads/{authed_user.id}/session123/data.xyz"
    with patch(
        "app.routes.misc.stream_object_async",
        new_callable=AsyncMock,
        return_value=(mock_body, 3, "application/special-type"),
    ):
        response = await client.get(f"/v1/outputs/{key}", headers=auth_headers)

    assert response.status_code == 200
    # Unknown extension → application/octet-stream (not S3-reported type)
    assert response.headers["content-type"] == "application/octet-stream"
    # #772: nosniff header
    assert response.headers["x-content-type-options"] == "nosniff"
    # #772: Content-Disposition: attachment for unknown types
    assert "attachment" in response.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_serve_output_path_with_slashes(
    client: AsyncTestClient, authed_user: User, auth_headers
):
    """GET /outputs/{key:path} handles nested paths with slashes."""
    key = f"uploads/{authed_user.id}/session/7/video.webm"
    fake_error = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}},
        "GetObject",
    )
    with patch(
        "app.routes.misc.stream_object_async",
        new_callable=AsyncMock,
        side_effect=fake_error,
    ):
        response = await client.get(f"/v1/outputs/{key}", headers=auth_headers)
    assert response.status_code == 404
