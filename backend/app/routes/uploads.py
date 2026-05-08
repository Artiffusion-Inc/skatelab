"""Chunked S3 multipart upload endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Sequence  # noqa: TC003
from typing import ClassVar

from litestar import Controller, post
from litestar.exceptions import ClientException
from litestar.params import Parameter
from litestar.status_codes import HTTP_400_BAD_REQUEST
from pydantic import BaseModel

from app.auth.deps import VerifiedUser
from app.config import get_settings
from app.storage import get_r2_client

CHUNK_SIZE = 5 * 1024 * 1024  # 5MB


class CompleteUploadRequest(BaseModel):
    upload_id: str
    key: str
    parts: list[dict]


class UploadsController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["uploads"]

    @post("/init")
    async def init_upload(
        self,
        verified_user: VerifiedUser,
        file_name: str = Parameter(min_length=1),
        content_type: str = Parameter(default="video/mp4"),
        total_size: int = Parameter(gt=0),
    ) -> dict:
        """Initialize a multipart upload. Returns upload_id and pre-signed part URLs."""
        r2 = get_r2_client()
        bucket = get_settings().r2.bucket
        key = f"uploads/{verified_user.id}/{uuid.uuid4()}/{file_name}"

        upload_id = r2.create_multipart_upload(
            Bucket=bucket,
            Key=key,
            ContentType=content_type,
        )["UploadId"]

        # Calculate number of parts
        part_count = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        # Generate pre-signed URLs for each part
        part_urls = []
        for part_number in range(1, part_count + 1):
            url = r2.generate_presigned_url(
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
        r2 = get_r2_client()
        bucket = get_settings().r2.bucket

        multipart_parts = [
            {"PartNumber": p["part_number"], "ETag": p["etag"]}
            for p in sorted(data.parts, key=lambda x: int(x["part_number"]))
        ]

        if not multipart_parts:
            raise ClientException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="No parts provided",
            )

        r2.complete_multipart_upload(
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
        """Generate a presigned PUT URL for direct R2 upload (small files)."""
        r2 = get_r2_client()
        bucket = get_settings().r2.bucket
        key = f"uploads/{verified_user.id}/{uuid.uuid4()}/{file_name}"

        url = r2.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=3600,
        )

        return {"url": url, "key": key}
