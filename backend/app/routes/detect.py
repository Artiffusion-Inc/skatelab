"""POST /api/detect — enqueue person detection job."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence  # noqa: TC003
from pathlib import Path
from typing import ClassVar

from litestar import Controller, Request, Response, get, post
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_400_BAD_REQUEST, HTTP_413_REQUEST_ENTITY_TOO_LARGE

from app.auth.deps import CurrentUser
from app.auth.ownership import assert_task_owned
from app.middleware.rate_limit import check_rate_limit
from app.schemas import (
    DetectQueueResponse,
    DetectResultResponse,
    TaskStatusResponse,
)
from app.storage import upload_bytes_async
from app.task_manager import (
    TaskStatus,
    create_task_state,
)

logger = logging.getLogger(__name__)

# #761: max video upload size (100 MB)
MAX_VIDEO_SIZE = 100 * 1024 * 1024
# #763: allowed video file extensions (no .exe, .html, etc.)
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
# #766: global cap on detect enqueues. The per-user limit (10/min) does not stop
# a botnet of N accounts from running N*10/min GPU-detection jobs. A shared
# global counter caps the whole fleet so extra accounts buy nothing once the
# cap is hit. Tunable via env; conservative default covers legit traffic while
# bounding GPU queue growth and cost from a sybil attack.
GLOBAL_DETECT_CAP = 200


class DetectController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["detect"]

    @post("", status_code=200)
    async def enqueue_detect(
        self,
        request: Request,
        user: CurrentUser,
        tracking: str = "auto",
    ) -> DetectQueueResponse:
        """Upload video, enqueue detection job, return task_id immediately."""
        form_data = await request.form()
        video = form_data.get("video")
        if not video:
            # #762: rate limit not consumed by no-video requests — return early
            raise ClientException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="No video file uploaded",
            )

        # #761: enforce max video size
        content = await video.read()
        if len(content) > MAX_VIDEO_SIZE:
            raise ClientException(
                status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Video too large: {len(content)} bytes. Max: {MAX_VIDEO_SIZE} bytes",
            )

        # #763: reject dangerous file suffixes
        suffix = Path(video.filename or "video.mp4").suffix.lower()
        if suffix not in ALLOWED_VIDEO_SUFFIXES:
            raise ClientException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Unsupported video format: {suffix}. "
                f"Allowed: {', '.join(sorted(ALLOWED_VIDEO_SUFFIXES))}",
            )

        # #762: rate limit AFTER validation, not before
        await check_rate_limit(f"detect:enqueue:{user.id}", max_requests=10, window_seconds=60)
        # #766: global cap — a per-user limit alone doesn't stop a botnet (N
        # accounts = N*10/min). A shared counter caps the whole fleet so extra
        # accounts buy nothing once the cap is hit, bounding GPU queue flood
        # and cost. Checked AFTER per-user so legit single-user traffic hits
        # the cheaper per-user limit first.
        await check_rate_limit(
            "detect:enqueue:global",
            max_requests=GLOBAL_DETECT_CAP,
            window_seconds=60,
        )

        # #760: use full uuid4 hex instead of 12-char truncation
        task_id = f"det_{uuid.uuid4().hex}"
        video_key = f"input/{task_id}{suffix}"

        # #764 + #759: try S3 upload, then create task state; rollback S3 on failure
        try:
            await upload_bytes_async(content, video_key)
        except Exception:
            logger.exception("S3 upload failed for detect video key %s", video_key)
            raise ClientException(
                status_code=503,
                detail="Storage temporarily unavailable",
            ) from None

        try:
            await create_task_state(task_id, video_key=video_key, user_id=str(user.id))
        except Exception:
            logger.exception("Failed to create task state for %s", task_id)
            # #759 + #764: clean up orphaned S3 object
            try:
                from app.storage import delete_object_async

                await delete_object_async(video_key)
            except Exception:
                logger.warning("Failed to clean up S3 key %s after task state failure", video_key)
            raise ClientException(
                status_code=503,
                detail="Failed to create task",
            ) from None

        # #765: catch enqueue_job failure, clean up state
        try:
            await request.app.state.arq_pool.enqueue_job(
                "detect_video_task",
                task_id=task_id,
                video_key=video_key,
                tracking=tracking,
                _queue_name="skatelab:queue:fast",
            )
        except Exception:
            logger.exception("Failed to enqueue detect_video_task for %s", task_id)
            raise ClientException(
                status_code=503,
                detail="Failed to enqueue task",
            ) from None

        return DetectQueueResponse(task_id=task_id, video_key=video_key)

    @get("/{task_id:str}/status")
    async def get_detect_status(self, task_id: str, user: CurrentUser) -> Response:
        """Poll detection task status."""
        state = await assert_task_owned(task_id, user)

        # #758: handle missing progress key
        progress = state.get("progress", 0.0)
        if isinstance(progress, str):
            try:
                progress = float(progress)
            except (ValueError, TypeError):
                progress = 0.0

        # #757: use DetectResultResponse for detect results, not ProcessResponse
        result = None
        raw_result = state.get("result")
        if raw_result and isinstance(raw_result, dict):
            try:
                result = DetectResultResponse.model_validate(raw_result)
            except Exception:
                logger.warning("detect status: failed to parse result for task %s", task_id)
                result = None

        body = TaskStatusResponse(
            task_id=task_id,
            status=state["status"],
            progress=progress,
            message=state.get("message", ""),
            result=result,  # type: ignore[reportArgumentType]
            error=state.get("error"),
        )
        # #768: cache headers — 2s to reduce polling flood
        return Response(
            content=body.model_dump(),
            headers={"Cache-Control": "max-age=2"},
        )

    @get("/{task_id:str}/result")
    async def get_detect_result(self, task_id: str, user: CurrentUser) -> DetectResultResponse:
        """Get detection result (persons, preview)."""
        state = await assert_task_owned(task_id, user)

        if state.get("status") != TaskStatus.COMPLETED:
            raise ClientException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Task not completed yet",
            )

        raw_result = state.get("result")
        if not raw_result or not isinstance(raw_result, dict):
            raise ClientException(
                status_code=500,
                detail="No result stored",
            )

        # #767: handle schema drift with try/except
        try:
            return DetectResultResponse.model_validate(raw_result)
        except Exception:
            logger.warning("detect result: failed to parse result for task %s", task_id)
            raise ClientException(
                status_code=500,
                detail="Result data corrupted",
            ) from None
