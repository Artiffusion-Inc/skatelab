"""Chunked S3 multipart upload endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Sequence  # noqa: TC003
from pathlib import PurePosixPath
from typing import ClassVar

from litestar import Controller, post
from litestar.exceptions import ClientException
from litestar.params import Parameter
from litestar.status_codes import HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN
from pydantic import BaseModel

from app.auth.deps import VerifiedUser
from app.config import get_settings
from app.middleware.rate_limit import check_rate_limit
from app.storage import get_s3_client

CHUNK_SIZE = 5 * 1024 * 1024  # 5MB


def sanitize_file_name(name: str) -> str:
    """Strip path separators / `..` segments from an upload file_name.

    #682: file_name is a user-controlled path parameter used verbatim in the
    S3 key (`uploads/{user_id}/{uuid}/{file_name}`). Without sanitization a
    caller can inject `..` or `/` segments — S3 stores the literal key and
    downstream path-resolving tools may escape the user prefix. Take the
    basename only and collapse to a single safe segment.
    """
    # PurePosixPath(...).name takes the final component, dropping any leading
    # `/` paths; normalize backslashes so nt-style separators don't sneak
    # through. Reject bare `.`/`..`/empty that `.name` leaves intact.
    base = PurePosixPath(name.replace("\\", "/")).name
    if base in {".", "..", ""}:
        raise ClientException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Invalid file_name",
        )
    return base


class UploadPart(BaseModel):
    # #683: typed model — missing/non-int part_number or missing etag is
    # rejected at the schema layer (400) instead of KeyError/ValueError → 500
    # mid-handler. int coerces stringified numbers from loose clients.
    part_number: int
    etag: str


class CompleteUploadRequest(BaseModel):
    upload_id: str
    key: str
    parts: list[UploadPart]


class UploadsController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["uploads"]

    @post("/init")
    async def init_upload(
        self,
        verified_user: VerifiedUser,
        file_name: str = Parameter(min_length=1),
        content_type: str = Parameter(default="video/mp4"),
        total_size: int = Parameter(gt=0, le=10 * 1024 * 1024 * 1024),  # #681: max 10 GB
    ) -> dict:
        """Initialize a multipart upload. Returns upload_id and pre-signed part URLs."""
        await check_rate_limit(
            f"upload:init:{verified_user.id}", max_requests=10, window_seconds=60
        )

        s3 = get_s3_client()
        bucket = get_settings().s3.bucket
        safe_name = sanitize_file_name(file_name)
        key = f"uploads/{verified_user.id}/{uuid.uuid4()}/{safe_name}"

        upload_id = s3.create_multipart_upload(
            Bucket=bucket,
            Key=key,
            ContentType=content_type,
        )["UploadId"]

        # Calculate number of parts
        part_count = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        # Generate pre-signed URLs for each part
        part_urls = []
        for part_number in range(1, part_count + 1):
            url = s3.generate_presigned_url(
                ClientMethod="upload_part",
                Params={
                    "Bucket": bucket,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=3600,
            )
            part_urls.append({"part_number": part_number, "url": url})

        return {
            "upload_id": upload_id,
            "key": key,
            "chunk_size": CHUNK_SIZE,
            "part_count": part_count,
            "parts": part_urls,
        }

    @post("/complete")
    async def complete_upload(
        self, verified_user: VerifiedUser, data: CompleteUploadRequest
    ) -> dict:
        """Complete a multipart upload. Returns the final object key."""
        await check_rate_limit(
            f"upload:complete:{verified_user.id}", max_requests=10, window_seconds=60
        )

        # Ownership check: the object key must live under the caller's upload
        # prefix (`uploads/{user_id}/...` — the format /init and /presign emit).
        # Reject cross-user completion (IDOR: finalizing another user's
        # in-flight multipart upload under their key).
        expected_prefix = f"uploads/{verified_user.id}/"
        if not data.key.startswith(expected_prefix):
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not your upload key",
            )

        s3 = get_s3_client()
        bucket = get_settings().s3.bucket

        if not data.parts:
            raise ClientException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="No parts provided",
            )

        # #684: validate part numbers form a contiguous 1..N set with no gaps
        # or duplicates. S3 silently completes a multipart upload with missing
        # parts → unplayable video that retries can't fix (multipart state
        # corrupted) and a storage leak. Reject before the S3 call.
        part_numbers = [p.part_number for p in data.parts]
        expected = set(range(1, len(part_numbers) + 1))
        if set(part_numbers) != expected:
            raise ClientException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Part numbers must be contiguous 1..N with no gaps or duplicates",
            )

        multipart_parts = [
            {"PartNumber": p.part_number, "ETag": p.etag}
            for p in sorted(data.parts, key=lambda x: x.part_number)
        ]

        s3.complete_multipart_upload(
            Bucket=bucket,
            Key=data.key,
            UploadId=data.upload_id,
            MultipartUpload={"Parts": multipart_parts},
        )

        return {"status": "completed", "key": data.key}

    @post("/presign")
    async def presign_upload(
        self,
        verified_user: VerifiedUser,
        file_name: str = Parameter(min_length=1),
        content_type: str = Parameter(default="application/octet-stream"),
    ) -> dict:
        """Generate a presigned PUT URL for direct S3 upload (small files)."""
        await check_rate_limit(
            f"upload:presign:{verified_user.id}", max_requests=10, window_seconds=60
        )

        s3 = get_s3_client()
        bucket = get_settings().s3.bucket
        safe_name = sanitize_file_name(file_name)
        key = f"uploads/{verified_user.id}/{uuid.uuid4()}/{safe_name}"

        url = s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=3600,
        )

        return {"url": url, "key": key}
