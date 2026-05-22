"""Extended tests for Vast.ai client async functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.vastai.client import (
    VastResult,
    _async_route_request,
    process_video_remote_async,
)


def _make_settings():
    s = MagicMock()
    s.vastai.api_key.get_secret_value.return_value = "test-api-key"
    s.vastai.endpoint_name = "skatelab-workers"
    s.r2.endpoint_url = "https://r2.example.com"
    s.r2.access_key_id.get_secret_value.return_value = "r2-key-id"
    s.r2.secret_access_key.get_secret_value.return_value = "r2-secret"
    s.r2.bucket = "test-bucket"
    return s


def _make_route_resp():
    """Create a mock route response with full auth data."""
    mock = MagicMock()
    mock.status_code = 200
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "url": "https://worker.vast.ai:5000",
        "signature": "test-signature",
        "reqnum": 0,
        "request_idx": 175,
        "cost": 0.0,
    }
    return mock


def _make_process_result(**overrides):
    data = {
        "poses_r2_key": "output/test_poses.npy",
        "metrics_r2_key": "output/test_metrics.json",
        "stats": {"total_frames": 100, "valid_frames": 90, "fps": 30.0},
        "metrics": [{"name": "airtime", "value": 0.5}],
        "phases": {"takeoff": 10, "peak": 20, "landing": 30},
        "recommendations": ["Keep your back straight"],
    }
    data.update(overrides)
    return data


def _make_async_client(route_resp, process_resp):
    """Create a mock AsyncClient with post returning route then process."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = [route_resp, process_resp]
    return mock_client


# ---------------------------------------------------------------------------
# _async_route_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_route_request_success():
    """_async_route_request returns full route data."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "url": "https://async-worker.vast.ai:5000",
        "signature": "async-sig",
        "reqnum": 2,
        "request_idx": 50,
        "cost": 0.0,
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with patch("app.vastai.client.get_async_client", return_value=mock_client):
        route = await _async_route_request("skatelab-workers", "test-key")

    assert route["url"] == "https://async-worker.vast.ai:5000"
    assert route["signature"] == "async-sig"
    assert route["request_idx"] == 50


@pytest.mark.asyncio
async def test_async_route_request_raises_on_http_error():
    """Propagates HTTP errors from the route endpoint."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.raise_for_status.side_effect = Exception("Unauthorized")

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with (
        patch("app.vastai.client.get_async_client", return_value=mock_client),
        pytest.raises(Exception, match="Unauthorized"),
    ):
        await _async_route_request("ep", "bad-key")


# ---------------------------------------------------------------------------
# process_video_remote_async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_video_remote_async_happy_path():
    """Full async flow: route -> process -> return VastResult."""
    route_resp = _make_route_resp()
    process_resp = MagicMock()
    process_resp.status_code = 200
    process_resp.json.return_value = _make_process_result()
    process_resp.raise_for_status = MagicMock()

    mock_client = _make_async_client(route_resp, process_resp)

    with (
        patch("app.vastai.client.get_async_client", return_value=mock_client),
        patch("app.vastai.client.get_settings", return_value=_make_settings()),
    ):
        result = await process_video_remote_async(
            video_key="input/test.mp4",
            person_click={"x": 100, "y": 200},
            frame_skip=8,
            tracking="centroid",
            ml_flags={"depth": True},
            element_type="waltz_jump",
        )

    assert isinstance(result, VastResult)
    assert result.poses_key == "output/test_poses.npy"
    assert result.metrics_key == "output/test_metrics.json"
    assert result.stats["total_frames"] == 100
    assert result.metrics == [{"name": "airtime", "value": 0.5}]
    assert result.phases == {"takeoff": 10, "peak": 20, "landing": 30}
    assert result.recommendations == ["Keep your back straight"]

    # Verify body has auth_data + payload structure
    process_call = mock_client.post.call_args_list[1]
    body = process_call.kwargs["json"]
    assert "auth_data" in body
    assert "payload" in body
    assert body["payload"]["video_r2_key"] == "input/test.mp4"
    assert body["payload"]["person_click"] == {"x": 100, "y": 200}
    assert body["payload"]["frame_skip"] == 8
    assert body["payload"]["tracking"] == "centroid"
    assert body["payload"]["ml_flags"] == {"depth": True}
    assert body["payload"]["element_type"] == "waltz_jump"
    # No export/layer in payload
    assert "export" not in body["payload"]
    assert "layer" not in body["payload"]


@pytest.mark.asyncio
async def test_process_video_remote_async_defaults():
    """Default parameter values produce correct payload."""
    route_resp = _make_route_resp()
    result_data = _make_process_result()
    del result_data["poses_r2_key"]
    del result_data["metrics_r2_key"]
    del result_data["metrics"]
    del result_data["phases"]
    del result_data["recommendations"]

    process_resp = MagicMock()
    process_resp.status_code = 200
    process_resp.json.return_value = result_data
    process_resp.raise_for_status = MagicMock()

    mock_client = _make_async_client(route_resp, process_resp)

    with (
        patch("app.vastai.client.get_async_client", return_value=mock_client),
        patch("app.vastai.client.get_settings", return_value=_make_settings()),
    ):
        result = await process_video_remote_async(video_key="input/test.mp4")

    assert result.poses_key is None
    assert result.metrics_key is None
    assert result.metrics is None
    assert result.phases is None
    assert result.recommendations is None

    # Verify defaults in payload
    process_call = mock_client.post.call_args_list[1]
    body = process_call.kwargs["json"]
    assert body["payload"]["person_click"] is None
    assert body["payload"]["frame_skip"] == 1
    assert body["payload"]["tracking"] == "auto"
    assert body["payload"]["ml_flags"] == {}
    assert body["payload"]["element_type"] is None


@pytest.mark.asyncio
async def test_process_video_remote_async_route_failure():
    """Raises when the route endpoint returns an error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.raise_for_status.side_effect = Exception("Not Found")

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with (
        patch("app.vastai.client.get_async_client", return_value=mock_client),
        patch("app.vastai.client.get_settings", return_value=_make_settings()),
        pytest.raises(Exception, match="Not Found"),
    ):
        await process_video_remote_async(video_key="input/test.mp4")


@pytest.mark.asyncio
async def test_process_video_remote_async_process_failure():
    """Raises when the worker process endpoint returns an error."""
    route_resp = _make_route_resp()
    process_resp = MagicMock()
    process_resp.status_code = 500
    process_resp.raise_for_status.side_effect = Exception("Worker Error")

    mock_client = _make_async_client(route_resp, process_resp)

    with (
        patch("app.vastai.client.get_async_client", return_value=mock_client),
        patch("app.vastai.client.get_settings", return_value=_make_settings()),
        pytest.raises(Exception, match="Worker Error"),
    ):
        await process_video_remote_async(video_key="input/test.mp4")
