"""Coach comment API routes."""

from __future__ import annotations

from collections.abc import Sequence  # noqa: TC003
from typing import ClassVar

from litestar import Controller, post
from litestar.exceptions import ClientException
from litestar.status_codes import (
    HTTP_201_CREATED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)

from app.auth.deps import DbDep, VerifiedUser
from app.crud.comments import create as create_comment
from app.crud.connection import is_connected_as
from app.crud.session import get_by_id
from app.models.connection import ConnectionType
from app.schemas import CommentResponse, CreateCommentRequest
from app.services.notification_events import coach_comment_created


class CommentsController(Controller):
    """Create feedback on sessions owned by connected athletes."""

    path = ""
    tags: ClassVar[Sequence[str]] = ["comments"]

    @post("/{session_id:str}/comments", status_code=HTTP_201_CREATED)
    async def create_comment(
        self,
        session_id: str,
        data: CreateCommentRequest,
        verified_user: VerifiedUser,
        db: DbDep,
    ) -> CommentResponse:
        """Create a coach comment and notify the session owner atomically."""
        session = await get_by_id(db, session_id)
        if session is None:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

        if not await is_connected_as(
            db,
            from_user_id=verified_user.id,
            to_user_id=session.user_id,
            connection_type=ConnectionType.COACHING,
        ):
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized to comment on this session",
            )

        comment = await create_comment(
            db,
            session_id=session.id,
            coach_id=verified_user.id,
            content=data.content,
        )
        await coach_comment_created(
            db,
            user_id=session.user_id,
            comment_id=comment.id,
            session_id=session.id,
        )
        return CommentResponse.model_validate(comment)
