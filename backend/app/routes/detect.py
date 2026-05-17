"""POST /api/detect — enqueue person detection job."""

from __future__ import annotations

import uuid
from collections.abc import Sequence  # noqa: TC003
from pathlib import Path
from typing import ClassVar

from litestar import Controller, Request, get, post
from litestar.exceptions import ClientException

from app.auth.deps import CurrentUser
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
    get_task_state,
    get_valkey,
)


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
        await check_rate_limit(f"detect:enqueue:{user.id}", max_requests=10, window_seconds=60)

        form_data = await request.form()
        video = form_data.get("video")
        if not video:
            raise ClientException(
                status_code=400,
                detail="No video file uploaded",
            )

        suffix = Path(video.filename or "video.mp4").suffix
        video_key = f"input/{uuid.uuid4().hex}{suffix}"

        content = await video.read()
        await upload_bytes_async(content, video_key)

        task_id = f"det_{uuid.uuid4().hex[:12]}"

        valkey = get_valkey()
        await create_task_state(task_id, video_key=video_key, valkey=valkey, user_id=str(user.id))

        await request.app.state.arq_pool.enqueue_job(
            "detect_video_task",
            task_id=task_id,
            video_key=video_key,
            tracking=tracking,
            _queue_name="skatelab:queue:fast",
        )

        return DetectQueueResponse(task_id=task_id, video_key=video_key)

    @get("/{task_id:str}/status")
    async def get_detect_status(self, task_id: str, user: CurrentUser) -> TaskStatusResponse:
        """Poll detection task status."""
        valkey = get_valkey()
        state = await get_task_state(task_id, valkey=valkey)

        if state is None:
            raise ClientException(
                status_code=404,
                detail="Task not found",
            )

        result = None
        if state.get("result"):
            result = DetectResultResponse(**state["result"])

        return TaskStatusResponse(
            task_id=task_id,
            status=state["status"],
            progress=state["progress"],
            message=state.get("message", ""),
            result=result,  # type: ignore[reportArgumentType]
            error=state.get("error"),
        )

    @get("/{task_id:str}/result")
    async def get_detect_result(self, task_id: str, user: CurrentUser) -> DetectResultResponse:
        """Get detection result (persons, preview)."""
        valkey = get_valkey()
        state = await get_task_state(task_id, valkey=valkey)

        if state is None:
            raise ClientException(
                status_code=404,
                detail="Task not found",
            )

        if state.get("status") != TaskStatus.COMPLETED:
            raise ClientException(
                status_code=400,
                detail="Task not completed yet",
            )

        if not state.get("result"):
            raise ClientException(
                status_code=500,
                detail="No result stored",
            )

        return DetectResultResponse(**state["result"])
