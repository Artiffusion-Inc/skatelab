"""#682 repro: init_upload / presign_upload must sanitize file_name path traversal.

RED contract (before fix): `file_name` is a path parameter used verbatim in
the S3 key: `f"uploads/{user_id}/{uuid}/{file_name}"`. A caller passing
`file_name="../../etc/passwd"` produces a key with `..` segments — S3 stores
the literal key, downstream path-resolving tools may escape the user prefix.
GREEN contract (after fix): path separators and `..` segments stripped from
file_name before key construction.
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


def test_source_has_file_name_sanitizer() -> None:
    """uploads route sanitizes file_name before using it in the S3 key."""
    src = _src()
    assert "sanitize" in src.lower() or "PurePath" in src, (
        "no file_name sanitizer — traversal segments reach the S3 key verbatim"
    )


def test_sanitize_strips_traversal_segments() -> None:
    """sanitize_file_name collapses `..` / `/` / `\\` to a safe basename."""
    from litestar.exceptions import ClientException

    sanitize = _mod().sanitize_file_name
    assert sanitize("../../etc/passwd") == "passwd"
    assert sanitize("a/b/c.mp4") == "c.mp4"
    assert sanitize("evil\\..\\x") == "x"
    # bare traversal rejected, not returned as-is
    with pytest.raises(ClientException):
        sanitize("..")
    with pytest.raises(ClientException):
        sanitize(".")


@pytest.mark.asyncio
async def test_init_upload_key_has_no_traversal(client, auth_headers) -> None:
    """POST /uploads/init with traversal file_name produces a key with no '..'."""
    from unittest.mock import MagicMock, patch

    mod = _mod()
    s3 = MagicMock()
    s3.create_multipart_upload.return_value = {"UploadId": "up_123"}
    s3.generate_presigned_url.return_value = "https://presigned.url/part"
    with (
        patch.object(mod, "get_s3_client", return_value=s3),
        patch.object(mod, "get_settings") as mock_settings,
    ):
        mock_settings.return_value.s3.bucket = "b"
        response = await client.post(
            "/v1/uploads/init",
            params={"file_name": "../../etc/passwd", "total_size": 10000000},
            headers=auth_headers,
        )
    # sanitized to basename → key ends with /passwd, no `..`
    data = response.json()
    key = data["key"]
    assert ".." not in key, f"traversal segment in key: {key!r}"
    assert key.endswith("/passwd")
