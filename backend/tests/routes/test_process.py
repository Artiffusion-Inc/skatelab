"""Tests for process routes (enqueue, status, cancel).

Note: SSE stream tests live in test_sse_timeout.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# POST /process/queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_process(client, auth_headers):
    """POST /process/queue creates task state and enqueues job with correct params."""
    req_body = {
        "video_key": "input/test.mp4",
        "person_click": {"x": 150, "y": 300},
        "frame_skip": 4,
        "tracking": "auto",
        "session_id": "sess_123",
        "lift_3d": False,
        "optical_flow": False,
    }

    with (
        patch("app.routes.process.create_task_state", new_callable=AsyncMock),
    ):
        response = await client.post("/v1/process/queue", json=req_body, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["task_id"].startswith("proc_")
    assert data["status"] == "pending"

    client.app.state.arq_pool.enqueue_job.assert_awaited_once()
    call_kwargs = client.app.state.arq_pool.enqueue_job.call_args.kwargs
    assert call_kwargs["task_id"] == data["task_id"]
    assert call_kwargs["video_key"] == "input/test.mp4"
    assert call_kwargs["person_click"] == {"x": 150, "y": 300}
    assert call_kwargs["frame_skip"] == 4
    assert call_kwargs["tracking"] == "auto"
    assert call_kwargs["session_id"] == "sess_123"
    assert call_kwargs["_queue_name"] == "skatelab:queue:heavy"

    # Verify MLModelFlags are passed correctly
    ml_flags = call_kwargs["ml_flags"]
    assert ml_flags.lift_3d is False
    assert ml_flags.optical_flow is False
    assert ml_flags.segment is False
    assert ml_flags.foot_track is False
    assert ml_flags.matting is False
    assert ml_flags.inpainting is False


@pytest.mark.asyncio
async def test_enqueue_process_with_ml_flags(client, auth_headers):
    """POST /process/queue passes ML model flags to the job."""
    req_body = {
        "video_key": "input/flags.mp4",
        "person_click": {"x": 50, "y": 50},
        "lift_3d": True,
        "optical_flow": True,
        "segment": True,
        "foot_track": True,
    }

    with (
        patch("app.routes.process.create_task_state", new_callable=AsyncMock),
    ):
        response = await client.post("/v1/process/queue", json=req_body, headers=auth_headers)

    assert response.status_code == 200

    call_kwargs = client.app.state.arq_pool.enqueue_job.call_args.kwargs
    ml_flags = call_kwargs["ml_flags"]
    assert ml_flags.lift_3d is True
    assert ml_flags.optical_flow is True
    assert ml_flags.segment is True
    assert ml_flags.foot_track is True
    assert ml_flags.matting is False
    assert ml_flags.inpainting is False


@pytest.mark.asyncio
async def test_enqueue_process_defaults(client, auth_headers):
    """POST /process/queue uses default values for optional fields."""
    req_body = {
        "video_key": "input/minimal.mp4",
        "person_click": {"x": 0, "y": 0},
    }

    with (
        patch("app.routes.process.create_task_state", new_callable=AsyncMock),
    ):
        response = await client.post("/v1/process/queue", json=req_body, headers=auth_headers)

    assert response.status_code == 200

    call_kwargs = client.app.state.arq_pool.enqueue_job.call_args.kwargs
    assert call_kwargs["frame_skip"] == 1
    assert call_kwargs["tracking"] == "auto"
    assert call_kwargs["session_id"] is None


# ---------------------------------------------------------------------------
# GET /process/{task_id}/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_status(client, auth_headers):
    """GET /process/{task_id}/status returns task state without result."""
    fake_state = {
        "task_id": "proc_abc",
        "status": "running",
        "progress": 0.75,
        "message": "Extracting poses",
        "result": None,
        "error": "",
    }

    with (
        patch("app.routes.process.get_task_state", new_callable=AsyncMock, return_value=fake_state),
    ):
        response = await client.get("/v1/process/proc_abc/status", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "proc_abc"
    assert data["status"] == "running"
    assert data["progress"] == 0.75
    assert data["message"] == "Extracting poses"
    assert data["result"] is None


@pytest.mark.asyncio
async def test_process_status_not_found(client, auth_headers):
    """GET /process/{task_id}/status returns 404 when task not found."""
    with (
        patch("app.routes.process.get_task_state", new_callable=AsyncMock, return_value=None),
    ):
        response = await client.get("/v1/process/proc_nonexist/status", headers=auth_headers)

    assert response.status_code == 404
    data = response.json()
    assert data["message"] == "Task not found"


@pytest.mark.asyncio
async def test_process_status_with_result(client, auth_headers):
    """GET /process/{task_id}/status embeds ProcessResponse when result exists."""
    fake_result = {
        "video_path": "output/proc_abc/result.mp4",
        "poses_path": "output/proc_abc/poses.npz",
        "csv_path": "output/proc_abc/metrics.csv",
        "stats": {
            "total_frames": 300,
            "valid_frames": 280,
            "fps": 30.0,
            "resolution": "1920x1080",
        },
        "status": "completed",
    }
    fake_state = {
        "task_id": "proc_done",
        "status": "completed",
        "progress": 1.0,
        "message": "Done",
        "result": fake_result,
        "error": "",
    }

    with (
        patch("app.routes.process.get_task_state", new_callable=AsyncMock, return_value=fake_state),
    ):
        response = await client.get("/v1/process/proc_done/status", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["result"] is not None
    assert data["result"]["video_path"] == "output/proc_abc/result.mp4"
    assert data["result"]["stats"]["total_frames"] == 300


@pytest.mark.asyncio
async def test_process_status_with_error(client, auth_headers):
    """GET /process/{task_id}/status returns error field when present."""
    fake_state = {
        "task_id": "proc_fail",
        "status": "failed",
        "progress": 0.1,
        "message": "Error",
        "result": None,
        "error": "Model loading failed",
    }

    with (
        patch("app.routes.process.get_task_state", new_callable=AsyncMock, return_value=fake_state),
    ):
        response = await client.get("/v1/process/proc_fail/status", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()


# ---------------------------------------------------------------------------
# POST /process/{task_id}/cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_process(client, auth_headers):
    """POST /process/{task_id}/cancel sets cancel signal and returns confirmation."""
    with patch("app.routes.process.set_cancel_signal", new_callable=AsyncMock):
        response = await client.post("/v1/process/proc_running/cancel", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancel_requested"
    assert data["task_id"] == "proc_running"
