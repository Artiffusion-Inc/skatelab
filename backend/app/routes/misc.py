"""Health check and file serving routes (S3 streaming proxy)."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence  # noqa: TC003
from pathlib import Path
from typing import ClassVar

from litestar import Controller, get
from litestar.exceptions import ClientException
from litestar.response import Stream
from litestar.status_codes import HTTP_403_FORBIDDEN

from app.auth.deps import CurrentUser
from app.storage import object_exists_async, stream_object_async


class MiscController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["misc"]

    # Content-type mapping by extension
    _CONTENT_TYPES: ClassVar[dict[str, str]] = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".npy": "application/octet-stream",
        ".csv": "text/csv",
    }

    @get("/health")
    async def health(self) -> dict:
        valkey_ok = False
        with contextlib.suppress(Exception):
            from app.task_manager import get_valkey

            valkey_ok = await get_valkey().ping()
        return {"status": "ok" if valkey_ok else "degraded", "valkey": valkey_ok}

    @get("/outputs/{key:path}")
    async def serve_output(self, key: str, user: CurrentUser) -> Stream:
        """Stream file from S3 as a proxy (frontend never talks to S3 directly).

        #513: previously unauthenticated — `/v1/outputs` was in JWTAuth.exclude
        AND the route had no CurrentUser dep, so anyone with a guessed/leaked
        S3 key (`uploads/{user_id}/{uuid}/video.mp4`) downloaded another user's
        private video. Require auth and enforce the caller owns the key's
        upload prefix (mirrors uploads.py:95 ownership check).
        """
        # {key:path} may capture a leading slash (/uploads/... vs uploads/...);
        # normalize so the prefix check is stable.
        key = key.lstrip("/")
        expected_prefix = f"uploads/{user.id}/"
        if not key.startswith(expected_prefix):
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not your file",
            )
        if not await object_exists_async(key):
            raise ClientException(
                status_code=404,
                detail="File not found",
            )

        body, length, ctype = await stream_object_async(key)
        # Prefer extension-based content type over what S3 reports
        ext = Path(key).suffix.lower()
        if ext in self._CONTENT_TYPES:
            ctype = self._CONTENT_TYPES[ext]

        return Stream(
            body.iter_chunks(chunk_size=8192),
            media_type=ctype,
            headers={"Content-Length": str(length)},
        )
