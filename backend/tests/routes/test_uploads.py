"""Tests for uploads multipart route."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest  # noqa: E402 — must follow sys.modules mock

# Mock aiobotocore before importing routes that depend on it
_mock_aiobotocore = MagicMock()
_mock_aiobotocore_session = MagicMock()
sys.modules["aiobotocore"] = _mock_aiobotocore
sys.modules["aiobotocore.session"] = _mock_aiobotocore_session

from app.routes.uploads import CHUNK_SIZE  # noqa: E402


def _mock_r2():
    r2 = MagicMock()
    r2.create_multipart_upload.return_value = {"UploadId": "up_123"}
    r2.generate_presigned_url.return_value = "https://presigned.url/part"
    r2.complete_multipart_upload.return_value = {}
    return r2


def _mock_settings():
    cfg = MagicMock()
    cfg.r2.bucket = "test-bucket"
    return cfg


@pytest.mark.asyncio
async def test_init_upload(client, auth_headers):
    """POST /uploads/init returns upload_id, key, chunk_size, part_count, parts."""
    with (
        patch("app.routes.uploads.get_r2_client") as mock_s3_client,
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        mock_s3_client.return_value = _mock_r2()
        mock_settings.return_value = _mock_settings()

        response = await client.post(
            "/v1/uploads/init",
            params={"file_name": "video.mp4", "total_size": 10000000},
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["upload_id"] == "up_123"
    assert data["key"].startswith("uploads/")
    assert data["key"].endswith("/video.mp4")
    assert data["chunk_size"] == CHUNK_SIZE
    assert isinstance(data["part_count"], int)
    assert isinstance(data["parts"], list)
    assert len(data["parts"]) == data["part_count"]


@pytest.mark.asyncio
async def test_init_upload_part_count(client, auth_headers):
    """15MB file / 5MB chunk = 3 parts."""
    with (
        patch("app.routes.uploads.get_r2_client") as mock_s3_client,
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        mock_s3_client.return_value = _mock_r2()
        mock_settings.return_value = _mock_settings()

        total_size = 15 * 1024 * 1024  # exactly 3 chunks
        response = await client.post(
            "/v1/uploads/init",
            params={"file_name": "big.mp4", "total_size": total_size},
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["part_count"] == 3
    assert len(data["parts"]) == 3


@pytest.mark.asyncio
async def test_init_upload_single_part(client, auth_headers):
    """3MB file = 1 part."""
    with (
        patch("app.routes.uploads.get_r2_client") as mock_s3_client,
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        mock_s3_client.return_value = _mock_r2()
        mock_settings.return_value = _mock_settings()

        total_size = 3 * 1024 * 1024  # fits in 1 chunk
        response = await client.post(
            "/v1/uploads/init",
            params={"file_name": "small.mp4", "total_size": total_size},
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["part_count"] == 1
    assert len(data["parts"]) == 1


@pytest.mark.asyncio
async def test_complete_upload(client, auth_headers):
    """POST /uploads/complete calls complete_multipart_upload with sorted parts."""
    with (
        patch("app.routes.uploads.get_r2_client") as mock_s3_client,
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        r2 = _mock_r2()
        mock_s3_client.return_value = r2
        mock_settings.return_value = _mock_settings()

        response = await client.post(
            "/v1/uploads/complete",
            json={
                "upload_id": "up_123",
                "key": "uploads/user-id/uuid/video.mp4",
                "parts": [
                    {"part_number": 1, "etag": '"etag1"'},
                    {"part_number": 2, "etag": '"etag2"'},
                ],
            },
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "completed"
    assert data["key"] == "uploads/user-id/uuid/video.mp4"

    r2.complete_multipart_upload.assert_called_once()
    call_kwargs = r2.complete_multipart_upload.call_args
    parts = call_kwargs.kwargs["MultipartUpload"]["Parts"]
    assert parts == [
        {"PartNumber": 1, "ETag": '"etag1"'},
        {"PartNumber": 2, "ETag": '"etag2"'},
    ]


@pytest.mark.asyncio
async def test_complete_upload_empty_parts(client, auth_headers):
    """POST /uploads/complete with no parts returns 400."""
    with (
        patch("app.routes.uploads.get_r2_client") as mock_s3_client,
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        mock_s3_client.return_value = _mock_r2()
        mock_settings.return_value = _mock_settings()

        response = await client.post(
            "/v1/uploads/complete",
            json={
                "upload_id": "up_123",
                "key": "uploads/user-id/uuid/video.mp4",
                "parts": [],
            },
            headers=auth_headers,
        )

    assert response.status_code == 400
    data = response.json()
    assert "No parts provided" in data["message"]


@pytest.mark.asyncio
async def test_complete_upload_parts_sorted(client, auth_headers):
    """Parts are sorted by part_number regardless of input order."""
    with (
        patch("app.routes.uploads.get_r2_client") as mock_s3_client,
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        r2 = _mock_r2()
        mock_s3_client.return_value = r2
        mock_settings.return_value = _mock_settings()

        response = await client.post(
            "/v1/uploads/complete",
            json={
                "upload_id": "up_123",
                "key": "uploads/user-id/uuid/video.mp4",
                "parts": [
                    {"part_number": 3, "etag": '"etag3"'},
                    {"part_number": 1, "etag": '"etag1"'},
                    {"part_number": 2, "etag": '"etag2"'},
                ],
            },
            headers=auth_headers,
        )

    assert response.status_code == 201

    call_kwargs = r2.complete_multipart_upload.call_args
    parts = call_kwargs.kwargs["MultipartUpload"]["Parts"]
    assert parts == [
        {"PartNumber": 1, "ETag": '"etag1"'},
        {"PartNumber": 2, "ETag": '"etag2"'},
        {"PartNumber": 3, "ETag": '"etag3"'},
    ]


@pytest.mark.asyncio
async def test_init_upload_auth_required(client):
    """POST /uploads/init without auth returns 401."""
    with (
        patch("app.routes.uploads.get_r2_client") as mock_s3_client,
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        mock_s3_client.return_value = _mock_r2()
        mock_settings.return_value = _mock_settings()

        response = await client.post(
            "/v1/uploads/init",
            params={"file_name": "video.mp4", "total_size": 10000000},
        )

    assert response.status_code == 401
