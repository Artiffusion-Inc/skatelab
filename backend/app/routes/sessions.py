"""Session CRUD API routes."""

from __future__ import annotations

from collections.abc import Sequence  # noqa: TC003
from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, delete, get, patch, post
from litestar.exceptions import ClientException
from litestar.params import Parameter
from litestar.status_codes import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)

from app.auth.deps import CurrentUser, DbDep, VerifiedUser
from app.crud.connection import is_connected_as
from app.crud.session import count_by_user, create, get_by_id, list_by_user, soft_delete, update
from app.models.connection import ConnectionType
from app.schemas import (
    CreateSessionRequest,
    PatchSessionRequest,
    SessionListResponse,
    SessionResponse,
)
from app.storage import get_object_url_async

if TYPE_CHECKING:
    from app.models.session import Session


async def _session_to_response(session: Session) -> SessionResponse:
    """Convert ORM Session to response schema with presigned URLs."""
    video_url = (
        await get_object_url_async(session.video_key) if session.video_key else session.video_url
    )
    processed_video_url = (
        await get_object_url_async(session.processed_video_key)
        if session.processed_video_key
        else session.processed_video_url
    )
    return SessionResponse.model_validate(
        {
            "id": session.id,
            "user_id": session.user_id,
            "element_type": session.element_type,
            "video_key": session.video_key,
            "video_url": video_url,
            "processed_video_key": session.processed_video_key,
            "processed_video_url": processed_video_url,
            "poses_url": session.poses_url,
            "csv_url": session.csv_url,
            "pose_data": session.pose_data,
            "frame_metrics": session.frame_metrics,
            "status": session.status,
            "error_message": session.error_message,
            "phases": session.phases,
            "recommendations": session.recommendations,
            "overall_score": session.overall_score,
            "process_task_id": session.process_task_id,
            "imu_left_key": session.imu_left_key,
            "imu_right_key": session.imu_right_key,
            "manifest_key": session.manifest_key,
            "created_at": session.created_at,
            "processed_at": session.processed_at,
            "metrics": session.metrics,
        }
    )


class SessionsController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["sessions"]

    @post("", status_code=HTTP_201_CREATED)
    async def create_session(
        self, data: CreateSessionRequest, verified_user: VerifiedUser, db: DbDep
    ) -> SessionResponse:
        session = await create(
            db,
            user_id=verified_user.id,
            element_type=data.element_type,
            video_key=data.video_key,
            imu_left_key=data.imu_left_key,
            imu_right_key=data.imu_right_key,
            manifest_key=data.manifest_key,
            status="queued" if data.video_key else "uploading",
        )
        return await _session_to_response(session)

    @get("")
    async def list_sessions(
        self,
        user: CurrentUser,
        db: DbDep,
        user_id: str | None = None,
        element_type: str | None = None,
        limit: int = Parameter(default=20, ge=1, le=100),
        offset: int = Parameter(default=0, ge=0),
        sort: str = Parameter(default="created_at", pattern="^(created_at|overall_score)$"),
    ) -> SessionListResponse:
        # Coaches can view their students' sessions
        target_user_id = user_id if user_id else user.id
        if (
            user_id
            and user_id != user.id
            and not await is_connected_as(
                db,
                from_user_id=user.id,
                to_user_id=user_id,
                connection_type=ConnectionType.COACHING,
            )
        ):
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not a coach for this user",
            )

        sessions = await list_by_user(
            db,
            user_id=target_user_id,
            element_type=element_type,
            limit=limit,
            offset=offset,
            sort=sort,
        )
        total = await count_by_user(db, user_id=target_user_id, element_type=element_type)
        page = (offset // limit) + 1 if limit else 1  # type: ignore[operator]
        pages = (total + limit - 1) // limit if limit else 1  # type: ignore[operator]

        return SessionListResponse(
            sessions=[await _session_to_response(s) for s in sessions],
            total=total,
            page=page,
            page_size=limit,  # type: ignore[arg-type]
            pages=pages,
        )

    @get("/{session_id:str}")
    async def get_session(self, session_id: str, user: CurrentUser, db: DbDep) -> SessionResponse:
        session = await get_by_id(db, session_id)
        if not session:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        if session.user_id != user.id and not await is_connected_as(
            db,
            from_user_id=user.id,
            to_user_id=session.user_id,
            connection_type=ConnectionType.COACHING,
        ):
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )
        return await _session_to_response(session)

    @patch("/{session_id:str}")
    async def patch_session(
        self,
        session_id: str,
        data: PatchSessionRequest,
        verified_user: VerifiedUser,
        db: DbDep,
    ) -> SessionResponse:
        session = await get_by_id(db, session_id)
        if not session:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        if session.user_id != verified_user.id:
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )
        session = await update(db, session, **data.model_dump(exclude_unset=True))
        return await _session_to_response(session)

    @delete("/{session_id:str}", status_code=HTTP_204_NO_CONTENT)
    async def delete_session(self, session_id: str, verified_user: VerifiedUser, db: DbDep) -> None:
        session = await get_by_id(db, session_id)
        if not session:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        if session.user_id != verified_user.id:
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )
        await soft_delete(db, session)

    @delete("/bulk", status_code=HTTP_204_NO_CONTENT)
    async def delete_sessions_bulk(
        self,
        *,
        ids: str = Parameter(required=True),
        verified_user: VerifiedUser,
        db: DbDep,
    ) -> None:
        session_ids = [sid.strip() for sid in ids.split(",") if sid.strip()]
        for sid in session_ids:
            session = await get_by_id(db, sid)
            if not session:
                continue
            if session.user_id != verified_user.id:
                raise ClientException(
                    status_code=HTTP_403_FORBIDDEN,
                    detail="Cannot delete another user's session",
                )
            await soft_delete(db, session)
