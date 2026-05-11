"""Tests for Vast.ai client module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.vastai.client import (
    VastDetectResult,
    VastResult,
    _build_auth_data,
    _route_request,
    process_video_remote,
)


def test_route_request_success():
    """_route_request returns full route data from Vast.ai."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "url": "https://worker-1.vast.ai:5000",
        "signature": "abc123",
        "reqnum": 1,
        "request_idx": 42,
        "cost": 0.0,
    }

    with patch("app.vastai.client.httpx.post", return_value=mock_resp):
        route = _route_request("skatelab-workers", "test-key")

    assert route["url"] == "https://worker-1.vast.ai:5000"
    assert route["signature"] == "abc123"
    assert route["reqnum"] == 1
    assert route["request_idx"] == 42
    assert route["cost"] == 0.0


def test_route_request_error_msg():
    """_route_request raises RuntimeError on error_msg from Vast.ai."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"error_msg": "endpoint not found"}

    with patch("app.vastai.client.httpx.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="endpoint not found"):
            _route_request("bad-endpoint", "test-key")


def test_build_auth_data():
    """_build_auth_data constructs correct auth_data dict."""
    route = {
        "url": "https://worker.vast.ai:5000",
        "signature": "sig123",
        "reqnum": 2,
        "request_idx": 99,
        "cost": 0.0,
    }
    auth = _build_auth_data(route, "skatelab-workers")

    assert auth["endpoint"] == "skatelab-workers"
    assert auth["request_idx"] == 99
    assert auth["reqnum"] == 2
    assert auth["url"] == "https://worker.vast.ai:5000"
    assert auth["cost"] == 0.0
    assert auth["signature"] == "sig123"


def test_vast_result_fields():
    r = VastResult(
        poses_key="output/test_poses.npy",
        metrics_key="output/test_metrics.json",
        stats={"frames": 100},
        metrics=None,
        phases=None,
        recommendations=None,
    )
    assert r.poses_key == "output/test_poses.npy"
    assert r.metrics_key == "output/test_metrics.json"
    assert r.stats == {"frames": 100}


def test_vast_result_keys_none():
    r = VastResult(
        poses_key=None,
        metrics_key=None,
        stats={"frames": 100},
        metrics=None,
        phases=None,
        recommendations=None,
    )
    assert r.poses_key is None
    assert r.metrics_key is None


def test_vast_detect_result_fields():
    r = VastDetectResult(
        persons=[{"track_id": 0, "hits": 30, "bbox": [0.1, 0.2, 0.9, 0.8], "mid_hip": [0.5, 0.6]}],
        preview_image="base64data",
        video_key="uploads/test/video.mp4",
        auto_click={"x": 500, "y": 1000},
        width=1080,
        height=1920,
        status="OK",
    )
    assert len(r.persons) == 1
    assert r.auto_click == {"x": 500, "y": 1000}
    assert r.width == 1080


@patch("app.vastai.client.httpx.post")
def test_process_video_remote_wraps_in_auth_data(mock_post):
    """process_video_remote sends auth_data + payload format to PyWorker."""
    mock_route_resp = MagicMock()
    mock_route_resp.status_code = 200
    mock_route_resp.json.return_value = {
        "url": "https://worker.vast.ai:5000",
        "signature": "test-sig",
        "reqnum": 0,
        "request_idx": 175,
        "cost": 0.0,
    }
    mock_route_resp.raise_for_status = MagicMock()

    mock_process_resp = MagicMock()
    mock_process_resp.status_code = 200
    mock_process_resp.json.return_value = {
        "poses_r2_key": "output/test_poses.npy",
        "metrics_r2_key": "output/test_metrics.json",
        "stats": {"total_frames": 100, "valid_frames": 90, "fps": 30.0, "resolution": "1920x1080"},
    }
    mock_process_resp.raise_for_status = MagicMock()

    mock_post.side_effect = [mock_route_resp, mock_process_resp]

    with patch("app.vastai.client.get_settings") as mock_settings:
        s = MagicMock()
        s.vastai.api_key.get_secret_value.return_value = "test-key"
        s.vastai.endpoint_name = "skatelab-workers"
        s.r2.endpoint_url = "https://r2.example.com"
        s.r2.access_key_id.get_secret_value.return_value = "key-id"
        s.r2.secret_access_key.get_secret_value.return_value = "secret"
        s.r2.bucket = "test-bucket"
        mock_settings.return_value = s

        result = process_video_remote(
            video_key="input/test.mp4",
            person_click={"x": 100, "y": 200},
        )

    assert result.poses_key == "output/test_poses.npy"
    assert result.metrics_key == "output/test_metrics.json"
    assert mock_post.call_count == 2

    # Verify process call has auth_data + payload structure
    process_call = mock_post.call_args_list[1]
    body = process_call.kwargs["json"]
    assert "auth_data" in body
    assert "payload" in body
    assert body["auth_data"]["endpoint"] == "skatelab-workers"
    assert body["auth_data"]["signature"] == "test-sig"
    assert body["auth_data"]["request_idx"] == 175
    assert body["payload"]["video_r2_key"] == "input/test.mp4"
    assert body["payload"]["person_click"] == {"x": 100, "y": 200}
    assert body["payload"]["r2_bucket"] == "test-bucket"
    # No export/layer in payload (removed)
    assert "export" not in body["payload"]
    assert "layer" not in body["payload"]


@pytest.mark.asyncio
async def test_detect_video_remote_async_wraps_in_auth_data():
    """detect_video_remote_async sends auth_data + payload format."""
    from app.vastai.client import detect_video_remote_async

    route_data = {
        "url": "https://worker.vast.ai:5000",
        "signature": "detect-sig",
        "reqnum": 1,
        "request_idx": 200,
        "cost": 0.0,
    }
    mock_route_resp = MagicMock()
    mock_route_resp.status_code = 200
    mock_route_resp.json.return_value = route_data
    mock_route_resp.raise_for_status = MagicMock()

    mock_detect_resp = MagicMock()
    mock_detect_resp.status_code = 200
    mock_detect_resp.json.return_value = {
        "persons": [
            {"track_id": 0, "hits": 30, "bbox": [0.1, 0.2, 0.9, 0.8], "mid_hip": [0.5, 0.6]}
        ],
        "preview_image": "base64data",
        "video_key": "uploads/test/video.mp4",
        "auto_click": {"x": 500, "y": 1000},
        "width": 1080,
        "height": 1920,
        "status": "OK",
    }
    mock_detect_resp.raise_for_status = MagicMock()

    with (
        patch("app.vastai.client.httpx.AsyncClient") as mock_client_cls,
        patch("app.vastai.client.get_settings") as mock_settings,
    ):
        s = MagicMock()
        s.vastai.api_key.get_secret_value.return_value = "test-key"
        s.vastai.endpoint_name = "skatelab-workers"
        s.r2.endpoint_url = "https://r2.example.com"
        s.r2.access_key_id.get_secret_value.return_value = "key-id"
        s.r2.secret_access_key.get_secret_value.return_value = "secret"
        s.r2.bucket = "test-bucket"
        mock_settings.return_value = s

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = [mock_route_resp, mock_detect_resp]
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client_instance

        result = await detect_video_remote_async(
            video_key="uploads/test/video.mp4",
            tracking="auto",
        )

    assert len(result.persons) == 1
    assert result.auto_click == {"x": 500, "y": 1000}
    assert result.video_key == "uploads/test/video.mp4"


@pytest.mark.asyncio
async def test_async_route_request_error_msg():
    """_async_route_request raises RuntimeError on error_msg."""
    from app.vastai.client import _async_route_request

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"error_msg": "endpoint 0 not found"}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.vastai.client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(RuntimeError, match="endpoint 0 not found"):
            await _async_route_request("bad-endpoint", "test-key")
