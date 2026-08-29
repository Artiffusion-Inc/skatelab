"""Repro tests for detect route bugfixes #757-#768."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROUTES_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "routes" / "detect.py"
SCHEMAS_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "schemas.py"


# ---------------------------------------------------------------------------
# Source-assertion tests
# ---------------------------------------------------------------------------


def test_757_detect_result_type_in_schema():
    """#757: TaskStatusResponse.result accepts DetectResultResponse."""
    src = SCHEMAS_FILE.read_text()
    assert "DetectResultResponse" in src, (
        "#757 DetectResultResponse missing from TaskStatusResponse"
    )


def test_758_progress_fallback_in_source():
    """#758: get_detect_status handles missing/malformed progress."""
    src = ROUTES_FILE.read_text()
    assert "isinstance(progress, str)" in src, "#758 progress string handling missing"


def test_759_task_state_rollback_in_source():
    """#759: S3 orphan cleanup when create_task_state fails."""
    src = ROUTES_FILE.read_text()
    assert "delete_object_async" in src, "#759 S3 rollback missing"


def test_760_full_uuid_in_source():
    """#760: task_id uses full uuid4 hex, not 12-char truncation."""
    src = ROUTES_FILE.read_text()
    # Should NOT have [:12] slice
    import re

    matches = re.findall(r"uuid4\(\)\.hex\[:\d+\]", src)
    assert len(matches) == 0, f"#760 still uses truncated hex: {matches}"


def test_761_video_size_limit_in_source():
    """#761: video upload has max size check."""
    src = ROUTES_FILE.read_text()
    assert "MAX_VIDEO_SIZE" in src, "#761 video size limit missing"


def test_762_rate_limit_after_validation_in_source():
    """#762: rate limit runs after video validation, not before."""
    src = ROUTES_FILE.read_text()
    video_check = src.find("if not video:")
    rate_limit = src.find("check_rate_limit", video_check)
    assert video_check > 0 and rate_limit > video_check, (
        "#762 rate limit must come after validation"
    )


def test_763_suffix_whitelist_in_source():
    """#763: file suffix whitelist prevents .exe uploads."""
    src = ROUTES_FILE.read_text()
    assert "ALLOWED_VIDEO_SUFFIXES" in src, "#763 video suffix whitelist missing"


def test_764_task_state_after_s3_in_source():
    """#764: create_task_state called after S3 upload, not before."""
    src = ROUTES_FILE.read_text()
    upload_pos = src.find("upload_bytes_async(content, video_key)")
    task_state_pos = src.find("create_task_state(task_id", upload_pos)
    assert upload_pos > 0 and task_state_pos > upload_pos, (
        "#764 task state must come after S3 upload"
    )


def test_765_enqueue_job_try_except_in_source():
    """#765: enqueue_job wrapped in try/except."""
    src = ROUTES_FILE.read_text()
    assert 'logger.exception("Failed to enqueue detect_video_task' in src, (
        "#765 enqueue_job try/except missing"
    )


def test_767_result_try_except_in_source():
    """#767: DetectResultResponse.model_validate wrapped in try/except."""
    src = ROUTES_FILE.read_text()
    assert "model_validate(raw_result)" in src, "#767 result validation missing"


def test_768_cache_headers_in_source():
    """#768: status endpoint returns Cache-Control header."""
    src = ROUTES_FILE.read_text()
    assert "Cache-Control" in src, "#768 cache headers missing"


# ---------------------------------------------------------------------------
# Route-level behavior tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_761_video_size_limit(client, auth_headers):
    """#761: oversized video returns 413."""
    from app.routes.detect import MAX_VIDEO_SIZE

    big_content = b"x" * (MAX_VIDEO_SIZE + 1)
    with (
        patch("app.routes.detect.create_task_state", new_callable=AsyncMock),
        patch("app.routes.detect.upload_bytes_async", new_callable=AsyncMock),
    ):
        response = await client.post(
            "/v1/detect",
            files={"video": ("big.mp4", BytesIO(big_content), "video/mp4")},
            headers=auth_headers,
        )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_763_reject_exe_suffix(client, auth_headers):
    """#763: .exe file suffix rejected."""
    with (
        patch("app.routes.detect.create_task_state", new_callable=AsyncMock),
        patch("app.routes.detect.upload_bytes_async", new_callable=AsyncMock),
    ):
        response = await client.post(
            "/v1/detect",
            files={"video": ("evil.exe", BytesIO(b"fake"), "application/octet-stream")},
            headers=auth_headers,
        )
    assert response.status_code == 400
    assert "Unsupported" in response.json()["message"]


@pytest.mark.asyncio
async def test_762_no_video_early_exit(client, auth_headers):
    """#762: no video file returns 400 without consuming rate limit."""
    response = await client.post(
        "/v1/detect",
        data={"tracking": "auto"},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_758_missing_progress_key(client, auth_headers, authed_user):
    """#758: missing progress key returns 0.0 instead of crashing."""
    fake_state = {
        "task_id": "det_noprogress",
        "status": "running",
        "message": "Processing",
        "result": None,
        "error": "",
        "user_id": str(authed_user.id),
        # progress key is missing
    }
    with patch(
        "app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=fake_state
    ):
        response = await client.get("/v1/detect/det_noprogress/status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["progress"] == 0.0


@pytest.mark.asyncio
async def test_757_detect_result_in_status(client, auth_headers, authed_user):
    """#757: DetectResultResponse in status endpoint returns 200, not 500."""
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
    with patch(
        "app.auth.ownership.get_task_state", new_callable=AsyncMock, return_value=fake_state
    ):
        response = await client.get("/v1/detect/det_abc123/status", headers=auth_headers)
    # #757: was 500 (ProcessResponse type mismatch), now 200
    assert response.status_code == 200
