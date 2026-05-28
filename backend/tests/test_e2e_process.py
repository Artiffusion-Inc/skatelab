"""E2E integration test: upload → process → status → cancel.

Tests the full API flow with mocked S3 and arq pool,
verifying that each stage correctly chains into the next.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_s3_client():
    """S3 client mock for presign and upload operations."""
    s3 = MagicMock()
    s3.generate_presigned_url.return_value = "https://s3.test/presigned"
    s3.create_multipart_upload.return_value = {"UploadId": "up_e2e"}
    s3.complete_multipart_upload.return_value = {}
    return s3


@pytest.mark.asyncio
async def test_e2e_presign_enqueue_poll(client, auth_headers, mock_s3_client):
    """Full flow: presign upload → enqueue process → poll status → get result."""
    # 1. Presign upload
    with (
        patch("app.routes.uploads.get_s3_client", return_value=mock_s3_client),
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        mock_cfg = MagicMock()
        mock_cfg.s3.bucket = "test-bucket"
        mock_settings.return_value = mock_cfg

        presign_resp = await client.post(
            "/v1/uploads/presign",
            params={"file_name": "skater.mp4", "content_type": "video/mp4"},
            headers=auth_headers,
        )

    assert presign_resp.status_code == 201
    presign_data = presign_resp.json()
    video_key = presign_data["key"]
    assert video_key.startswith("uploads/")

    # 2. Enqueue process
    with (
        patch("app.routes.process.create_task_state", new_callable=AsyncMock),
    ):
        process_resp = await client.post(
            "/v1/process/queue",
            json={
                "video_key": video_key,
                "person_click": {"x": 150, "y": 300},
                "frame_skip": 2,
                "tracking": "auto",
                "lift_3d": True,
            },
            headers=auth_headers,
        )

    assert process_resp.status_code == 200
    process_data = process_resp.json()
    task_id = process_data["task_id"]
    assert task_id.startswith("proc_")

    # Verify arq job was enqueued with correct params
    enqueue_call = client.app.state.arq_pool.enqueue_job.call_args
    assert enqueue_call.kwargs["video_key"] == video_key
    assert enqueue_call.kwargs["frame_skip"] == 2
    assert enqueue_call.kwargs["tracking"] == "auto"
    ml_flags = enqueue_call.kwargs["ml_flags"]
    assert ml_flags.lift_3d is True

    # 3. Poll status — running
    fake_running = {
        "task_id": task_id,
        "status": "running",
        "progress": 0.5,
        "message": "Extracting poses",
        "result": None,
        "error": "",
    }
    with (
        patch(
            "app.routes.process.get_task_state", new_callable=AsyncMock, return_value=fake_running
        ),
    ):
        status_resp = await client.get(f"/v1/process/{task_id}/status", headers=auth_headers)

    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "running"
    assert status_data["progress"] == 0.5

    # 4. Poll status — completed with result
    fake_completed = {
        "task_id": task_id,
        "status": "completed",
        "progress": 1.0,
        "message": "Done",
        "result": {
            "video_path": f"output/{task_id}/result.mp4",
            "poses_path": f"output/{task_id}/poses.npz",
            "csv_path": f"output/{task_id}/metrics.csv",
            "stats": {
                "total_frames": 300,
                "valid_frames": 280,
                "fps": 30.0,
                "resolution": "1920x1080",
            },
            "status": "completed",
        },
        "error": "",
    }
    with (
        patch(
            "app.routes.process.get_task_state", new_callable=AsyncMock, return_value=fake_completed
        ),
    ):
        final_resp = await client.get(f"/v1/process/{task_id}/status", headers=auth_headers)

    assert final_resp.status_code == 200
    final_data = final_resp.json()
    assert final_data["status"] == "completed"
    assert final_data["result"] is not None
    assert final_data["result"]["stats"]["total_frames"] == 300


@pytest.mark.asyncio
async def test_e2e_enqueue_then_cancel(client, auth_headers):
    """Enqueue process then cancel it."""
    # 1. Enqueue
    with (
        patch("app.routes.process.create_task_state", new_callable=AsyncMock),
    ):
        process_resp = await client.post(
            "/v1/process/queue",
            json={
                "video_key": "input/cancel_test.mp4",
                "person_click": {"x": 100, "y": 200},
            },
            headers=auth_headers,
        )

    assert process_resp.status_code == 200
    task_id = process_resp.json()["task_id"]

    # 2. Cancel
    with (
        patch("app.routes.process.set_cancel_signal", new_callable=AsyncMock),
    ):
        cancel_resp = await client.post(f"/v1/process/{task_id}/cancel", headers=auth_headers)

    assert cancel_resp.status_code == 200
    cancel_data = cancel_resp.json()
    assert cancel_data["status"] == "cancel_requested"
    assert cancel_data["task_id"] == task_id

    # 3. Status should reflect cancelled
    fake_cancelled = {
        "task_id": task_id,
        "status": "cancelled",
        "progress": 0.3,
        "message": "Cancelled by user",
        "result": None,
        "error": "",
    }
    with (
        patch(
            "app.routes.process.get_task_state", new_callable=AsyncMock, return_value=fake_cancelled
        ),
    ):
        status_resp = await client.get(f"/v1/process/{task_id}/status", headers=auth_headers)

    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_e2e_process_failed_task(client, auth_headers):
    """Process task that fails — status returns error."""
    task_id = "proc_fail_e2e"

    fake_failed = {
        "task_id": task_id,
        "status": "failed",
        "progress": 0.1,
        "message": "GPU error",
        "result": None,
        "error": "CUDA out of memory",
    }
    with (
        patch(
            "app.routes.process.get_task_state", new_callable=AsyncMock, return_value=fake_failed
        ),
    ):
        status_resp = await client.get(f"/v1/process/{task_id}/status", headers=auth_headers)

    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "failed"
    assert status_data["error"] == "CUDA out of memory"


@pytest.mark.asyncio
async def test_e2e_multipart_upload_enqueue(client, auth_headers, mock_s3_client):
    """Multipart upload flow: init → complete → enqueue process with returned key."""
    # 1. Init multipart upload
    with (
        patch("app.routes.uploads.get_s3_client", return_value=mock_s3_client),
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        mock_cfg = MagicMock()
        mock_cfg.s3.bucket = "test-bucket"
        mock_settings.return_value = mock_cfg

        init_resp = await client.post(
            "/v1/uploads/init",
            params={"file_name": "long_jump.mp4", "total_size": 25_000_000},
            headers=auth_headers,
        )

    assert init_resp.status_code == 201
    init_data = init_resp.json()
    assert "upload_id" in init_data
    assert "key" in init_data
    assert init_data["part_count"] == 5  # 25MB / 5MB = 5 parts
    video_key = init_data["key"]

    # 2. Complete upload
    parts = [{"part_number": i, "etag": f"etag_{i}"} for i in range(1, 6)]
    with (
        patch("app.routes.uploads.get_s3_client", return_value=mock_s3_client),
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        mock_cfg = MagicMock()
        mock_cfg.s3.bucket = "test-bucket"
        mock_settings.return_value = mock_cfg

        complete_resp = await client.post(
            "/v1/uploads/complete",
            json={
                "upload_id": init_data["upload_id"],
                "key": video_key,
                "parts": parts,
            },
            headers=auth_headers,
        )

    assert complete_resp.status_code == 201
    assert complete_resp.json()["key"] == video_key

    # 3. Enqueue process with the uploaded key
    with (
        patch("app.routes.process.create_task_state", new_callable=AsyncMock),
    ):
        process_resp = await client.post(
            "/v1/process/queue",
            json={
                "video_key": video_key,
                "person_click": {"x": 200, "y": 400},
                "lift_3d": True,
                "segment": True,
            },
            headers=auth_headers,
        )

    assert process_resp.status_code == 200
    enqueue_kwargs = client.app.state.arq_pool.enqueue_job.call_args.kwargs
    assert enqueue_kwargs["video_key"] == video_key
    assert enqueue_kwargs["ml_flags"].lift_3d is True
    assert enqueue_kwargs["ml_flags"].segment is True
