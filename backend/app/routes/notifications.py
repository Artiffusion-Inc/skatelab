"""In-app notifications API routes."""

from __future__ import annotations

from collections.abc import Sequence  # noqa: TC003
from math import ceil
from typing import ClassVar

from litestar import Controller, get, patch, post
from litestar.exceptions import ClientException
from litestar.params import Parameter
from litestar.status_codes import HTTP_200_OK, HTTP_404_NOT_FOUND

from app.auth.deps import CurrentUser, DbDep
from app.crud.notifications import count_by_user, get_by_id_for_user, list_by_user, mark_read
from app.crud.notifications import mark_all_read as mark_all_notifications_read
from app.schemas import (
    MarkAllNotificationsReadResponse,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)


class NotificationsController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["notifications"]

    @get("")
    async def list_notifications(
        self,
        user: CurrentUser,
        db: DbDep,
        page: int = Parameter(default=1, ge=1, le=10000),
        page_size: int = Parameter(default=20, ge=1, le=100),
        unread_only: bool = Parameter(default=False),
    ) -> NotificationListResponse:
        """List only the current user's notifications."""
        notifications = await list_by_user(
            db,
            user.id,
            page=page,
            page_size=page_size,
            unread_only=unread_only,
        )
        total = await count_by_user(db, user.id, unread_only=unread_only)
        unread_count = await count_by_user(db, user.id, unread_only=True)
        pages = max(1, ceil(total / page_size))
        return NotificationListResponse(
            notifications=[NotificationResponse.model_validate(n) for n in notifications],
            total=total,
            unread_count=unread_count,
            page=page,
            page_size=page_size,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1,
        )

    @get("/unread-count")
    async def unread_count(self, user: CurrentUser, db: DbDep) -> UnreadCountResponse:
        """Return the current user's unread notification count."""
        return UnreadCountResponse(unread_count=await count_by_user(db, user.id, unread_only=True))

    async def _mark_all_read(
        self, user: CurrentUser, db: DbDep
    ) -> MarkAllNotificationsReadResponse:
        return MarkAllNotificationsReadResponse(
            marked_read=await mark_all_notifications_read(db, user.id)
        )

    @post("/read-all", status_code=HTTP_200_OK)
    async def mark_all_read(self, user: CurrentUser, db: DbDep) -> MarkAllNotificationsReadResponse:
        """Mark all of the current user's unread notifications as read."""
        return await self._mark_all_read(user, db)

    @patch("/read-all")
    async def patch_all_read(
        self, user: CurrentUser, db: DbDep
    ) -> MarkAllNotificationsReadResponse:
        """PATCH alias for marking all of the current user's notifications read."""
        return await self._mark_all_read(user, db)

    async def _mark_notification_read(
        self, notification_id: str, user: CurrentUser, db: DbDep
    ) -> NotificationResponse:
        notification = await get_by_id_for_user(db, notification_id, user.id)
        if notification is None:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Notification not found",
            )
        _ = await mark_read(db, notification)
        return NotificationResponse.model_validate(notification)

    @post("/{notification_id:str}/read", status_code=HTTP_200_OK)
    async def mark_notification_read(
        self, notification_id: str, user: CurrentUser, db: DbDep
    ) -> NotificationResponse:
        """Mark one owned notification as read, idempotently."""
        return await self._mark_notification_read(notification_id, user, db)

    @patch("/{notification_id:str}/read")
    async def patch_notification_read(
        self, notification_id: str, user: CurrentUser, db: DbDep
    ) -> NotificationResponse:
        """PATCH alias for marking one owned notification read."""
        return await self._mark_notification_read(notification_id, user, db)
