"""POST /api/process/queue — enqueue video processing job."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Sequence  # noqa: TC003
from typing import Any, ClassVar

from litestar import Controller, Request, get, post
from litestar.exceptions import NotAuthorizedException
from litestar.response import ServerSentEvent

from app.auth.deps import CurrentUser, DbDep
from app.auth.ownership import assert_session_owned, assert_task_owned
from app.middleware.rate_limit import check_rate_limit
from app.schemas import (
    ProcessRequest,
    ProcessResponse,
    QueueProcessResponse,
    TaskStatusResponse,
)
from app.task_manager import (
    TASK_EVENTS_PREFIX,
    create_task_state,
    get_task_state,
    get_valkey,
    set_cancel_signal,
)

logger = logging.getLogger(__name__)

SSE_STREAM_TIMEOUT = 60  # seconds


class ProcessController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["process"]

    @post("/queue", status_code=200)
    async def enqueue_process(
        self,
        request: Request,
        data: ProcessRequest,
        user: CurrentUser,
        db: DbDep,
    ) -> QueueProcessResponse:
        """Enqueue video processing job and return task_id immediately."""
        await check_rate_limit(f"process:enqueue:{user.id}", max_requests=10, window_seconds=60)

        if data.session_id is not None:
            await assert_session_owned(db, data.session_id, user)

        task_id = f"proc_{uuid.uuid4().hex[:12]}"

        await create_task_state(task_id, video_key=data.video_key, user_id=str(user.id))

        ml_flags = {
            "lift_3d": data.lift_3d,
            "optical_flow": data.optical_flow,
            "segment": data.segment,
            "foot_track": data.foot_track,
            "matting": data.matting,
            "inpainting": data.inpainting,
        }

        await request.app.state.arq_pool.enqueue_job(
            "process_video_task",
            task_id=task_id,
            video_key=data.video_key,
            person_click={"x": data.person_click.x, "y": data.person_click.y},
            frame_skip=data.frame_skip,
            tracking=data.tracking,
            ml_flags=ml_flags,
            session_id=data.session_id,
            user_id=str(user.id),
            _queue_name="skatelab:queue:heavy",
        )

        return QueueProcessResponse(task_id=task_id)

    @get("/{task_id:str}/status")
    async def get_process_status(self, task_id: str, user: CurrentUser) -> TaskStatusResponse:
        """Poll task status."""
        state = await assert_task_owned(task_id, user)

        result = None
        if state.get("result"):
            result = ProcessResponse(**state["result"])

        return TaskStatusResponse(
            task_id=task_id,
            status=state["status"],
            progress=state["progress"],
            message=state.get("message", ""),
            result=result,  # type: ignore[reportArgumentType]
            error=state.get("error"),
        )

    @post("/{task_id:str}/cancel", status_code=200)
    async def cancel_queued_process(self, task_id: str, user: CurrentUser) -> dict:
        """Cancel a queued or running task via Valkey signal."""
        await assert_task_owned(task_id, user)
        await set_cancel_signal(task_id)
        return {"status": "cancel_requested", "task_id": task_id}

    @get("/{task_id:str}/stream")
    async def stream_process_status(self, task_id: str, user: CurrentUser) -> ServerSentEvent:
        """SSE endpoint for real-time task progress streaming."""

        async def event_generator():
            valkey = get_valkey()
            pubsub = valkey.pubsub()
            channel = f"{TASK_EVENTS_PREFIX}{task_id}"
            await pubsub.subscribe(channel)
            try:
                # Send initial state
                state = await get_task_state(task_id)
                if state:
                    # Ownership check: fail-closed — reject if task belongs to
                    # another user OR if the owner cannot be established (missing
                    # user_id on legacy/unattributed tasks). Mirrors assert_task_owned.
                    task_user_id = state.get("user_id")
                    if task_user_id is None or str(task_user_id) != str(user.id):
                        raise NotAuthorizedException("Not authorized to view this task")
                    yield {"data": json.dumps(state)}
                else:
                    yield {"data": json.dumps({"status": "unknown"})}

                async with asyncio.timeout(SSE_STREAM_TIMEOUT):
                    async for message in pubsub.listen():
                        if message["type"] == "message":
                            yield {"data": message["data"].decode()}
                            try:
                                data = json.loads(message["data"])
                                if data.get("status") in ("completed", "failed", "cancelled"):
                                    break
                            except (json.JSONDecodeError, TypeError):
                                pass
            except TimeoutError:
                # No messages for 60s — poll final state and yield timeout event
                logger.warning("SSE stream timeout for task %s", task_id)
                state = await get_task_state(task_id)
                payload: dict[str, Any] = state or {"status": "unknown"}
                payload["_timeout"] = True
                yield {"data": json.dumps(payload)}
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()

        return ServerSentEvent(event_generator())
