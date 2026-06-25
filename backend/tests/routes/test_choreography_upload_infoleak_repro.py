"""Repro test — choreography music upload leaks internal exception detail to the client.

`POST /choreography/music/upload` (routes/choreography.py:139-145) catches
`(OSError, ValueError, RuntimeError)` from the S3 upload / enqueue step and
re-raises a `ClientException` with:

    detail=f"Upload failed: {type(e).__name__}: {e}"

That `detail` is mapped to BOTH `error` and `message` in the HTTP response body
by `http_exception_handler` (app/exceptions.py:18-21), with NO scrubbing. So the
raw exception class name AND its message — which for an S3 / boto3 OSError
typically embeds the bucket name, the S3 endpoint host, and sometimes partial
credential / path hints — are sent verbatim to the client.

This is an information-disclosure bug: on a storage failure the client receives
internal infrastructure details (bucket `skatelab-prod-media`, endpoint
`s3.eu-central-1.amazonaws.com`, etc.) that aid an attacker in mapping the
backend. The correct contract is a generic user-facing message ("Upload failed,
please try again") with the technical detail logged server-side only.

The existing `test_upload_music_handles_upload_failure`
(routes/test_choreography_upload.py:127-153) actually ASSERTS the leak — it
checks `"Upload failed" in exc_info.value.detail`. It uses a benign message
("Upload failed") and asserts pass-through, so it encodes the leaky behavior as
the contract and never flags that real S3 exceptions carry sensitive detail.
This repro uses a realistic S3-style OSError carrying bucket + endpoint tokens
and asserts they do NOT reach the client. RED now: they do. After the fix
(generic detail, log the raw `e` server-side) → GREEN.

Repro uses the `_bound` direct-call pattern from the existing test file (it
calls the route handler with mocked deps, observing the raised
ClientException's `.detail` — which is exactly what becomes the response body).
No HTTP client / real S3 / real arq pool involved.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.routes.choreography import ChoreographyController

# Mock aiobotocore before importing (mirrors test_choreography_upload.py)
_mock_aiobotocore = MagicMock()
_mock_aiobotocore_session = MagicMock()
sys.modules["aiobotocore"] = _mock_aiobotocore
sys.modules["aiobotocore.session"] = _mock_aiobotocore_session

controller = object.__new__(ChoreographyController)


def _bound(name):
    handler = getattr(controller, name)
    return handler.fn.__get__(controller, ChoreographyController)


@pytest.fixture
def mock_user():
    u = MagicMock()
    u.id = "user_leak"
    return u


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_file():
    f = MagicMock()
    f.filename = "test.mp3"
    f.read = AsyncMock(return_value=b"fake audio content")
    return f


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.app.state.arq_pool = AsyncMock()
    return req


@pytest.fixture
def mock_tmp():
    tmp = MagicMock()
    tmp.name = "/tmp/test.mp3"
    tmp.write = MagicMock()
    tmp.__enter__ = MagicMock(return_value=tmp)
    tmp.__exit__ = MagicMock(return_value=False)
    return tmp


# Realistic S3/boto3-style OSError carrying internal infra details.
_SENSITIVE_BUCKET = "skatelab-prod-media"
_SENSITIVE_ENDPOINT = "s3.eu-central-1.amazonaws.com"
_LEAKY_OSError = OSError(
    f"Connection to bucket '{_SENSITIVE_BUCKET}' at {_SENSITIVE_ENDPOINT} "
    f"failed: read timeout (path=music/user_leak/music_123.mp3)"
)


@pytest.mark.asyncio
async def test_upload_music_failure_must_not_leak_s3_infra_detail_repro(
    mock_user, mock_db, mock_file, mock_request, mock_tmp
):
    """The 422 error detail must NOT contain bucket/endpoint from the S3 exception.

    RED now: detail is f"Upload failed: {type(e).__name__}: {e}" — it embeds the
    raw OSError message, leaking bucket + endpoint to the client. After the fix
    (generic user-facing message) → the sensitive tokens are absent.
    """
    from litestar.exceptions import ClientException

    mock_music = MagicMock()
    mock_music.id = "music_leak"

    with (
        patch("app.routes.choreography.find_music_by_fingerprint", return_value=None),
        patch("app.routes.choreography.create_music_analysis", return_value=mock_music),
        patch("app.routes.choreography.upload_file", side_effect=_LEAKY_OSError),
        patch("app.routes.choreography.update_music_analysis"),
        patch("app.routes.choreography.tempfile.NamedTemporaryFile", return_value=mock_tmp),
    ):
        with pytest.raises(ClientException) as exc_info:
            await _bound("upload_music")(mock_request, mock_user, mock_db, mock_file)

    assert exc_info.value.status_code == 422
    detail = str(exc_info.value.detail)

    # CONTRACT: internal S3 infrastructure tokens must NOT reach the client.
    assert _SENSITIVE_BUCKET not in detail, (
        f'BUG (info-leak): the S3 bucket name "{_SENSITIVE_BUCKET}" reached '
        f'the client error detail: "{detail}". The upload-failure response '
        f"must use a generic message, not the raw exception text."
    )
    assert _SENSITIVE_ENDPOINT not in detail, (
        f'BUG (info-leak): the S3 endpoint "{_SENSITIVE_ENDPOINT}" reached '
        f'the client error detail: "{detail}". The upload-failure response '
        f"must use a generic message, not the raw exception text."
    )
