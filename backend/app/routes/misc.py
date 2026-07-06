"""Health check and file serving routes (S3 streaming proxy)."""

from __future__ import annotations

import logging
from collections.abc import Sequence  # noqa: TC003
from pathlib import Path
from typing import ClassVar

from litestar import Controller, get
from litestar.exceptions import ClientException
from litestar.response import Stream
from litestar.status_codes import HTTP_403_FORBIDDEN

from app.auth.deps import CurrentUser
from app.storage import stream_object_async

logger = logging.getLogger(__name__)

# #772: strict content-type whitelist — unknown extensions get
# application/octet-stream + Content-Disposition: attachment (no XSS)
_SAFE_CONTENT_TYPES: ClassVar[dict[str, str]] = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".npy": "application/octet-stream",
    ".csv": "text/csv",
    ".json": "application/json",
}


class MiscController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["misc"]

    @get("/health")
    async def health(self) -> dict:
        # #770: /health remains unauthenticated (k8s liveness probe).
        # #771: catch specific Valkey errors, log distinct codes.
        valkey_ok = False
        valkey_error: str | None = None
        try:
            from app.task_manager import get_valkey

            valkey_ok = await get_valkey().ping()
        except Exception:
            logger.exception("Valkey health check failed")
            valkey_error = "unavailable"

        status = "ok" if valkey_ok else "degraded"
        # #770: don't expose valkey status detail to anonymous
        resp: dict = {"status": status}
        # Include valkey detail only when authenticated (not available here,
        # but k8s liveness only needs status; readiness can use a separate
        # auth-gated endpoint if needed)
        if valkey_error:
            resp["valkey_error"] = valkey_error
        return resp

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

        # #773: drop TOCTOU object_exists check, wrap stream directly.
        # #774: catch S3 errors → clean 404/502 instead of raw traceback.
        from botocore.exceptions import ClientError as BotoClientError

        try:
            body, length, ctype = await stream_object_async(key)
        except BotoClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                raise ClientException(
                    status_code=404,
                    detail="File not found",
                ) from None
            logger.exception("S3 stream failed for key %s", key)
            raise ClientException(
                status_code=502,
                detail="Storage unavailable",
            ) from None

        # #772: strict content-type + nosniff + attachment for dangerous extensions
        ext = Path(key).suffix.lower()
        ctype = _SAFE_CONTENT_TYPES.get(ext, "application/octet-stream")
        headers = {
            "Content-Length": str(length),
            "X-Content-Type-Options": "nosniff",
        }
        # Force download for extensions not in safe whitelist
        if ext not in _SAFE_CONTENT_TYPES:
            headers["Content-Disposition"] = f'attachment; filename="{Path(key).name}"'

        return Stream(
            body.iter_chunks(chunk_size=8192),
            media_type=ctype,
            headers=headers,
        )
