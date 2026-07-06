"""#683 repro: complete_upload must reject malformed parts with 400, not 500.

RED contract (before fix): `int(p["part_number"])` and `p["etag"]` accessed
dict keys with no validation. Missing `part_number` or non-int value raised
KeyError/ValueError mid-handler → 500, no semantic error to client. GREEN
contract (after fix): parts are validated by a Pydantic model — malformed
payload rejected at the schema layer with 422/400 before the handler runs.
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


def _src() -> str:
    return Path(_mod().__file__).read_text()


def test_source_uses_typed_part_model() -> None:
    """CompleteUploadRequest.parts is a typed Pydantic model list, not list[dict]."""
    src = _src()
    assert "list[dict]" not in src, (
        "parts: list[dict] — no validation, missing part_number raises KeyError → 500"
    )
    assert "BaseModel" in src, "typed part model missing"


@pytest.mark.asyncio
async def test_complete_upload_missing_part_number_rejected(
    client, auth_headers, authed_user
) -> None:
    """Part missing part_number → 4xx validation error, not 500."""
    from unittest.mock import MagicMock, patch

    mod = _mod()
    s3 = MagicMock()
    s3.complete_multipart_upload.return_value = {}
    upload_key = f"uploads/{authed_user.id}/uuid/video.mp4"
    with (
        patch.object(mod, "get_s3_client", return_value=s3),
        patch.object(mod, "get_settings") as mock_settings,
    ):
        mock_settings.return_value.s3.bucket = "b"
        response = await client.post(
            "/v1/uploads/complete",
            json={
                "upload_id": "up_123",
                "key": upload_key,
                "parts": [{"etag": '"e1"'}],  # missing part_number
            },
            headers=auth_headers,
        )
    assert 400 <= response.status_code < 500, response.text
    s3.complete_multipart_upload.assert_not_called()


@pytest.mark.asyncio
async def test_complete_upload_non_int_part_number_rejected(
    client, auth_headers, authed_user
) -> None:
    """Part with non-int part_number → 4xx validation error, not 500."""
    from unittest.mock import MagicMock, patch

    mod = _mod()
    s3 = MagicMock()
    s3.complete_multipart_upload.return_value = {}
    upload_key = f"uploads/{authed_user.id}/uuid/video.mp4"
    with (
        patch.object(mod, "get_s3_client", return_value=s3),
        patch.object(mod, "get_settings") as mock_settings,
    ):
        mock_settings.return_value.s3.bucket = "b"
        response = await client.post(
            "/v1/uploads/complete",
            json={
                "upload_id": "up_123",
                "key": upload_key,
                "parts": [{"part_number": "not-an-int", "etag": '"e1"'}],
            },
            headers=auth_headers,
        )
    assert 400 <= response.status_code < 500, response.text
    s3.complete_multipart_upload.assert_not_called()
