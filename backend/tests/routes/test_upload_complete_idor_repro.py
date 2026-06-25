"""Repro tests for IDOR on /uploads/complete — no ownership check on key/upload_id.

`POST /uploads/complete` (routes/uploads.py:82-112) finalizes an S3 multipart
upload using `data.key` and `data.upload_id` taken DIRECTLY from the request
body (`CompleteUploadRequest`). It does NOT verify that:

  - `data.key` is prefixed with `uploads/{verified_user.id}/` (the format every
    init/presign endpoint uses — uploads.py:48, :128), i.e. that the object key
    belongs to the caller; OR
  - `data.upload_id` was created by the caller (the init endpoint returns the
    `upload_id` from `s3.create_multipart_upload`, but nothing records which
    user owns it; the complete endpoint trusts the body blindly).

So ANY authenticated user can finalize ANY other user's in-flight multipart
upload by supplying the victim's `key` + `upload_id`. The victim's `upload_id`
is returned by `/uploads/init` to the victim and can leak via logs / shared
links; the `key` is predictable (`uploads/{victim_id}/{uuid}/{filename}`). The
attacker can complete (and thus "claim" / finalize) the victim's upload under
the victim's own key prefix, or supply a victim's key with attacker-chosen
parts.

The init endpoint correctly scopes keys to the caller (`f"uploads/{verified_user.id}/..."`
uploads.py:48), but complete has no symmetric check — the ownership boundary
established at init is not enforced at complete.

The existing `test_uploads.py` tests only call `/complete` as the SAME user who
called `/init` (single-user happy path), so cross-user completion never
surfaces in CI.

Repro: mock S3 so init returns a victim-scoped key + upload_id, then call
`/complete` as the ATTACKER with the victim's key + upload_id. RED now: 200
and `s3.complete_multipart_upload` is called with the victim's Key (the upload
is finalized for the attacker). After the fix (verify
`data.key.startswith(f"uploads/{verified_user.id}/")` and/or track upload_id
ownership) → 403.

No production data mutated: S3 client is a MagicMock; no real S3 calls, no real
uploads finalized. Only the route's authorization decision is observed.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Mock aiobotocore before importing routes that depend on it (mirrors test_uploads.py)
_mock_aiobotocore = MagicMock()
_mock_aiobotocore_session = MagicMock()
sys.modules["aiobotocore"] = _mock_aiobotocore
sys.modules["aiobotocore.session"] = _mock_aiobotocore_session

from app.auth.security import create_access_token, hash_password  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture
async def victim_user(db_session: AsyncSession) -> User:
    user = User(
        email="victim-upload@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def attacker_user(db_session: AsyncSession) -> User:
    user = User(
        email="attacker-upload@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def attacker_headers(attacker_user):
    token = create_access_token(user_id=attacker_user.id)
    return {"Authorization": f"Bearer {token}"}


def _mock_s3():
    s3 = MagicMock()
    s3.create_multipart_upload.return_value = {"UploadId": "up_victim"}
    s3.generate_presigned_url.return_value = "https://presigned.url/part"
    s3.complete_multipart_upload.return_value = {}
    return s3


def _mock_settings():
    cfg = MagicMock()
    cfg.s3.bucket = "test-bucket"
    return cfg


@pytest.mark.asyncio
async def test_complete_upload_idor_other_users_key_returns_403_repro(
    client, attacker_headers, victim_user
):
    """POST /uploads/complete with ANOTHER user's key+upload_id must 403.

    RED now: the route finalizes the victim's multipart upload (200) with no
    ownership check. After the fix → 403.
    """
    # The victim's key follows the init-endpoint format uploads/{victim_id}/{uuid}/file
    victim_key = f"uploads/{victim_user.id}/deadbeef/video.mp4"
    victim_upload_id = "up_victim"

    with (
        patch("app.routes.uploads.get_s3_client") as mock_s3_client,
        patch("app.routes.uploads.get_settings") as mock_settings,
    ):
        s3 = _mock_s3()
        mock_s3_client.return_value = s3
        mock_settings.return_value = _mock_settings()

        response = await client.post(
            "/v1/uploads/complete",
            json={
                "upload_id": victim_upload_id,
                "key": victim_key,
                "parts": [{"part_number": 1, "etag": "etag1"}],
            },
            headers=attacker_headers,
        )

    assert response.status_code == 403, (
        "BUG (IDOR): POST /uploads/complete finalized another user's multipart "
        f"upload (got {response.status_code}, expected 403). The key "
        f'"{victim_key}" belongs to the victim (uploads/{"<victim_id>"}/...) '
        f"but the attacker (a different authenticated user) was allowed to "
        f"complete it. Body: {response.text}"
    )

    # The S3 complete call must NOT have used the victim's key for the attacker.
    if s3.complete_multipart_upload.called:
        call_kwargs = s3.complete_multipart_upload.call_args.kwargs
        used_key = call_kwargs.get("Key")
        assert used_key != victim_key, (
            f"BUG (IDOR): s3.complete_multipart_upload was called with the "
            f'victim\'s Key="{used_key}" on behalf of the attacker — the '
            f"upload was finalized cross-user."
        )
