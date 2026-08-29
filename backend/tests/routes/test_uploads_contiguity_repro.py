"""#684 repro: complete_upload must reject gaps / duplicates in part numbers.

RED contract (before fix): parts are sorted by part_number and passed to S3
with no contiguity or duplicate check. A gap (parts 1,3 — missing 2) or a
duplicate (parts 1,1) is silently accepted → S3 multipart completes with a
broken/unplayable object. GREEN contract (after fix): part numbers must equal
set(range(1, N+1)); gaps and duplicates return 400 before the S3 call.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest  # noqa: E402

_mock_aiobotocore = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
sys.modules.setdefault("aiobotocore", _mock_aiobotocore)
sys.modules.setdefault("aiobotocore.session", _mock_aiobotocore)


def _mod():
    if "app.routes.uploads" not in sys.modules:
        importlib.import_module("app.routes.uploads")
    return sys.modules["app.routes.uploads"]


def _body() -> str:
    src = Path(_mod().__file__).read_text()
    start = src.index("async def complete_upload")
    end = src.index("\n    @", start + 1)
    return src[start:end]


def test_source_has_contiguity_check() -> None:
    """complete_upload validates part numbers form a contiguous 1..N set."""
    body = _body()
    code_lines = [ln for ln in body.splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    assert "range(" in code or "set(" in code, (
        "no contiguity check — gaps/duplicates silently accepted by S3"
    )


@pytest.mark.asyncio
async def test_complete_upload_gap_rejected_400(client, auth_headers, authed_user) -> None:
    """Parts [1,3] (missing 2) → 400, S3 not called."""
    from unittest.mock import MagicMock, patch

    s3 = MagicMock()
    s3.complete_multipart_upload.return_value = {}
    upload_key = f"uploads/{authed_user.id}/uuid/video.mp4"
    with (
        patch("app.routes.uploads.get_s3_client", return_value=s3),
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        mock_settings.return_value.s3.bucket = "b"
        response = await client.post(
            "/v1/uploads/complete",
            json={
                "upload_id": "up_123",
                "key": upload_key,
                "parts": [
                    {"part_number": 1, "etag": '"e1"'},
                    {"part_number": 3, "etag": '"e3"'},
                ],
            },
            headers=auth_headers,
        )
    assert response.status_code == 400, response.text
    s3.complete_multipart_upload.assert_not_called()


@pytest.mark.asyncio
async def test_complete_upload_duplicate_rejected_400(client, auth_headers, authed_user) -> None:
    """Parts [1,1] (duplicate) → 400, S3 not called."""
    from unittest.mock import MagicMock, patch

    s3 = MagicMock()
    s3.complete_multipart_upload.return_value = {}
    upload_key = f"uploads/{authed_user.id}/uuid/video.mp4"
    with (
        patch("app.routes.uploads.get_s3_client", return_value=s3),
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        mock_settings.return_value.s3.bucket = "b"
        response = await client.post(
            "/v1/uploads/complete",
            json={
                "upload_id": "up_123",
                "key": upload_key,
                "parts": [
                    {"part_number": 1, "etag": '"e1"'},
                    {"part_number": 1, "etag": '"e1"'},
                ],
            },
            headers=auth_headers,
        )
    assert response.status_code == 400, response.text
    s3.complete_multipart_upload.assert_not_called()
