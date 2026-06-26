"""Tests for detect routes (enqueue, status, result)."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# POST /detect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_detect(client, auth_headers):
    """POST /detect uploads video, creates task state, enqueues job."""
    video_content = b"fake-video-bytes"

    with (
        patch("app.routes.detect.create_task_state", new_callable=AsyncMock),
        patch("app.routes.detect.upload_bytes_async", new_callable=AsyncMock),
    ):
        response = await client.post(
            "/v1/detect",
            files={"video": ("test.mp4", BytesIO(video_content), "video/mp4")},
            data={"tracking": "auto"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["task_id"].startswith("det_")
    assert data["video_key"].startswith("input/")
    assert data["video_key"].endswith(".mp4")
    assert data["status"] == "pending"

    client.app.state.arq_pool.enqueue_job.assert_awaited_once_with(
        "detect_video_task",
        task_id=data["task_id"],
        video_key=data["video_key"],
        tracking="auto",
        _queue_name="skatelab:queue:fast",
    )


@pytest.mark.asyncio
async def test_enqueue_detect_custom_tracking(client, auth_headers):
    """POST /detect passes the tracking query parameter to the job."""
    video_content = b"fake-video-bytes"

    with (
        patch("app.routes.detect.create_task_state", new_callable=AsyncMock),
        patch("app.routes.detect.upload_bytes_async", new_callable=AsyncMock),
    ):
        response = await client.post(
            "/v1/detect?tracking=manual",
            files={"video": ("test.webm", BytesIO(video_content), "video/webm")},
            headers=auth_headers,
        )

    assert response.status_code == 200

    call_kwargs = client.app.state.arq_pool.enqueue_job.call_args.kwargs
    assert call_kwargs["tracking"] == "manual"


# ---------------------------------------------------------------------------
# GET /detect/{task_id}/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_status(client, auth_headers, authed_user):
    """GET /detect/{task_id}/status returns task state without result."""
    fake_state = {
        "task_id": "det_abc123",
        "status": "running",
        "progress": 0.5,
        "message": "Processing",
        "result": None,
        "error": "",
        "user_id": str(authed_user.id),
    }

    with (
        patch("app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=fake_state),
    ):
        response = await client.get("/v1/detect/det_abc123/status", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "det_abc123"
    assert data["status"] == "running"
    assert data["progress"] == 0.5
    assert data["message"] == "Processing"
    assert data["result"] is None
    assert data["error"] == ""


@pytest.mark.asyncio
async def test_detect_status_not_found(client, auth_headers):
    """GET /detect/{task_id}/status returns 404 when task not found."""
    with (
        patch("app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=None),
    ):
        response = await client.get("/v1/detect/det_nonexist/status", headers=auth_headers)

    assert response.status_code == 404
    data = response.json()
    assert data["message"] == "Task not found"


@pytest.mark.asyncio
async def test_detect_status_with_error(client, auth_headers, authed_user):
    """GET /detect/{task_id}/status returns error field when present."""
    fake_state = {
        "task_id": "det_fail",
        "status": "failed",
        "progress": 0.3,
        "message": "Error",
        "result": None,
        "error": "CUDA out of memory",
        "user_id": str(authed_user.id),
    }

    with (
        patch("app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=fake_state),
    ):
        response = await client.get("/v1/detect/det_fail/status", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "CUDA out of memory"


@pytest.mark.asyncio
async def test_detect_status_with_result_type_mismatch(client, auth_headers, authed_user):
    """GET /detect/{task_id}/status raises ValidationError when result is DetectResultResponse.

    TaskStatusResponse.result is typed as ProcessResponse | None, so embedding
    a DetectResultResponse causes a Pydantic validation error at serialization.
    This is a known type mismatch in the detect route (see # type: ignore on line 73).
    In production, ServerErrorMiddleware converts this to 500.
    """

    fake_result = {
        "persons": [
            {
                "track_id": 1,
                "hits": 50,
                "bbox": [0.1, 0.2, 0.8, 0.9],
                "mid_hip": [0.5, 0.6],
            }
        ],
        "preview_image": "base64data",
        "video_key": "input/abc.mp4",
        "auto_click": {"x": 100, "y": 200},
        "status": "completed",
    }
    fake_state = {
        "task_id": "det_abc123",
        "status": "completed",
        "progress": 1.0,
        "message": "Done",
        "result": fake_result,
        "error": "",
        "user_id": str(authed_user.id),
    }

    with (
        patch("app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=fake_state),
    ):
        response = await client.get("/v1/detect/det_abc123/status", headers=auth_headers)

    assert response.status_code == 500


# ---------------------------------------------------------------------------
# GET /detect/{task_id}/result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_result(client, auth_headers, authed_user):
    """GET /detect/{task_id}/result returns DetectResultResponse for completed task."""
    fake_result = {
        "persons": [
            {
                "track_id": 2,
                "hits": 100,
                "bbox": [0.0, 0.0, 1.0, 1.0],
                "mid_hip": [0.5, 0.5],
            }
        ],
        "preview_image": "abc123",
        "video_key": "input/test.webm",
        "auto_click": None,
        "status": "completed",
    }
    fake_state = {
        "task_id": "det_done",
        "status": "completed",
        "progress": 1.0,
        "message": "Done",
        "result": fake_result,
        "error": "",
        "user_id": str(authed_user.id),
    }

    with (
        patch("app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=fake_state),
    ):
        response = await client.get("/v1/detect/det_done/result", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["video_key"] == "input/test.webm"
    assert len(data["persons"]) == 1
    assert data["persons"][0]["track_id"] == 2
    assert data["auto_click"] is None


@pytest.mark.asyncio
async def test_detect_result_with_auto_click(client, auth_headers, authed_user):
    """GET /detect/{task_id}/result returns auto_click when present."""
    fake_result = {
        "persons": [],
        "preview_image": "img",
        "video_key": "input/x.mp4",
        "auto_click": {"x": 320, "y": 240},
        "status": "completed",
    }
    fake_state = {
        "task_id": "det_auto",
        "status": "completed",
        "progress": 1.0,
        "message": "Done",
        "result": fake_result,
        "error": "",
        "user_id": str(authed_user.id),
    }

    with (
        patch("app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=fake_state),
    ):
        response = await client.get("/v1/detect/det_auto/result", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["auto_click"] == {"x": 320, "y": 240}


@pytest.mark.asyncio
async def test_detect_result_not_found(client, auth_headers):
    """GET /detect/{task_id}/result returns 404 when task not found."""
    with (
        patch("app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=None),
    ):
        response = await client.get("/v1/detect/det_ghost/result", headers=auth_headers)

    assert response.status_code == 404
    data = response.json()
    assert data["message"] == "Task not found"


@pytest.mark.asyncio
async def test_detect_result_not_completed(client, auth_headers, authed_user):
    """GET /detect/{task_id}/result returns 400 when task not completed."""
    fake_state = {
        "task_id": "det_running",
        "status": "running",
        "progress": 0.5,
        "message": "Processing",
        "result": None,
        "error": "",
        "user_id": str(authed_user.id),
    }

    with (
        patch("app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=fake_state),
    ):
        response = await client.get("/v1/detect/det_running/result", headers=auth_headers)

    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "Task not completed yet"


@pytest.mark.asyncio
async def test_detect_result_no_result(client, auth_headers, authed_user):
    """GET /detect/{task_id}/result returns 500 when task completed but no result stored."""
    fake_state = {
        "task_id": "det_empty",
        "status": "completed",
        "progress": 1.0,
        "message": "Done",
        "result": None,
        "error": "",
        "user_id": str(authed_user.id),
    }

    with (
        patch("app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=fake_state),
    ):
        response = await client.get("/v1/detect/det_empty/result", headers=auth_headers)

    assert response.status_code == 500
    data = response.json()
    assert data["message"] == "No result stored"
