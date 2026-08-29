"""No-Valkey contract checks for the backend-to-GPU sensor-fusion path."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.schemas import ProcessRequest
from app.vastai.client import VastResult, process_video_remote_async


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.vastai.api_key.get_secret_value.return_value = "test-api-key"
    settings.vastai.endpoint_name = "skatelab-workers"
    settings.s3.endpoint_url = "https://s3.example.test"
    settings.s3.access_key_id.get_secret_value.return_value = "s3-key"
    settings.s3.secret_access_key.get_secret_value.return_value = "s3-secret"
    settings.s3.bucket = "test-bucket"
    return settings


def _route_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "url": "https://worker.example.test",
        "signature": "signature",
        "reqnum": 1,
        "request_idx": 2,
        "cost": 0.0,
    }
    return response


def test_process_request_carries_all_sensor_artifact_keys() -> None:
    request = ProcessRequest.model_validate(
        {
            "video_key": "uploads/session/video.mp4",
            "person_click": {"x": 10, "y": 20},
            "imu_left_key": "uploads/session/left.binpb",
            "imu_right_key": "uploads/session/right.binpb",
            "manifest_key": "uploads/session/manifest.json",
        }
    )

    assert request.imu_left_key == "uploads/session/left.binpb"
    assert request.imu_right_key == "uploads/session/right.binpb"
    assert request.manifest_key == "uploads/session/manifest.json"


@pytest.mark.asyncio
async def test_remote_process_propagates_sensor_keys_and_preserves_result() -> None:
    process_response = MagicMock()
    process_response.raise_for_status = MagicMock()
    process_response.json.return_value = {
        "poses_s3_key": "output/poses.npy",
        "metrics_s3_key": "output/metrics.json",
        "stats": {"total_frames": 1, "valid_frames": 1, "fps": 30.0},
        "sensor_fusion": {
            "status": "available",
            "provenance": "android_binpb",
            "validation": "unvalidated",
        },
    }
    client = AsyncMock()
    client.post.side_effect = [_route_response(), process_response]

    with (
        patch("app.vastai.client.get_async_client", return_value=client),
        patch("app.vastai.client.get_settings", return_value=_settings()),
    ):
        result = await process_video_remote_async(
            video_key="uploads/session/video.mp4",
            imu_left_key="uploads/session/left.binpb",
            imu_right_key="uploads/session/right.binpb",
            manifest_key="uploads/session/manifest.json",
        )

    payload = client.post.call_args_list[1].kwargs["json"]["payload"]
    assert payload["imu_left_s3_key"] == "uploads/session/left.binpb"
    assert payload["imu_right_s3_key"] == "uploads/session/right.binpb"
    assert payload["manifest_s3_key"] == "uploads/session/manifest.json"
    assert result.sensor_fusion == {
        "status": "available",
        "provenance": "android_binpb",
        "validation": "unvalidated",
    }


@pytest.mark.asyncio
async def test_worker_propagates_session_artifacts_and_result_diagnostics() -> None:
    from app.worker import process_video_task

    session = MagicMock(
        element_type="axel",
        isu_code=None,
        imu_left_key="uploads/session/left.binpb",
        imu_right_key="uploads/session/right.binpb",
        manifest_key="uploads/session/manifest.json",
        user_id="user-1",
    )
    db = AsyncMock()
    db.add = MagicMock()
    session_result = VastResult(
        poses_key=None,
        metrics_key=None,
        stats={"total_frames": 2, "valid_frames": 2, "fps": 100.0},
        metrics=None,
        phases=None,
        recommendations=None,
        sensor_fusion={
            "status": "available",
            "provenance": "android_binpb",
            "validation": "unvalidated",
        },
    )

    with (
        patch("app.worker.get_valkey", return_value=AsyncMock()),
        patch("app.worker.update_progress", new_callable=AsyncMock),
        patch("app.worker.publish_task_event", new_callable=AsyncMock),
        patch("app.worker.is_cancelled", new_callable=AsyncMock, return_value=False),
        patch("app.database.async_session_factory", create=True) as session_factory,
        patch("app.crud.session.get_by_id", new_callable=AsyncMock, return_value=session),
        patch("app.vastai.client.process_video_remote_async", new_callable=AsyncMock) as remote,
        patch(
            "app.services.analyzer_save.save_analyzer_results",
            new_callable=AsyncMock,
            return_value={"element_type": None, "rotations": None, "overall_score": 0.0},
        ),
        patch("app.worker.store_result", new_callable=AsyncMock) as store_result,
    ):
        session_factory.return_value.__aenter__.return_value = db
        remote.return_value = session_result

        response = await process_video_task(
            ctx={},
            task_id="task-sensor-contract",
            video_key="uploads/session/video.mp4",
            person_click={"x": 10, "y": 20},
            session_id="session-1",
        )

    call_kwargs = remote.await_args.kwargs
    assert call_kwargs["imu_left_key"] == "uploads/session/left.binpb"
    assert call_kwargs["imu_right_key"] == "uploads/session/right.binpb"
    assert call_kwargs["manifest_key"] == "uploads/session/manifest.json"
    assert response["sensor_fusion"]["provenance"] == "android_binpb"
    assert response["stats"]["sensor_fusion"]["validation"] == "unvalidated"
    store_result.assert_awaited_once()


def test_vast_result_keeps_unavailable_sensor_fusion_as_null() -> None:
    result = VastResult(
        poses_key=None,
        metrics_key=None,
        stats={},
        metrics=None,
        phases=None,
        recommendations=None,
        sensor_fusion=None,
    )

    assert result.sensor_fusion is None
