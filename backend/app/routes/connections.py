"""Flexible connection API routes."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence  # noqa: TC003
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, get, post
from litestar.exceptions import ClientException
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from app.auth.deps import CurrentUser, DbDep, VerifiedUser
from app.crud.connection import (
    create as create_conn,
)
from app.crud.connection import (
    get_active as get_active_conn,
)
from app.crud.connection import (
    get_by_id as get_conn_by_id,
)
from app.crud.connection import (
    list_for_user,
    list_pending_for_user,
)
from app.crud.user import get_by_email
from app.middleware import check_rate_limit
from app.models.connection import ConnectionStatus, ConnectionType
from app.schemas import ConnectionListResponse, ConnectionResponse, InviteRequest
from app.services.email import EmailService

if TYPE_CHECKING:
    from app.models.connection import Connection


def _conn_to_response(conn: Connection) -> ConnectionResponse:
    data = ConnectionResponse.model_validate(conn)
    data.from_user_name = conn.from_user.display_name if conn.from_user else None
    data.to_user_name = conn.to_user.display_name if conn.to_user else None
    return data


class ConnectionsController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["connections"]

    @post("/invite", status_code=HTTP_201_CREATED)
    async def invite(
        self, data: InviteRequest, verified_user: VerifiedUser, db: DbDep
    ) -> ConnectionResponse:
        """User invites another user to a connection."""
        await check_rate_limit(f"invite:{verified_user.id}", max_requests=3, window_seconds=3600)

        to_user = await get_by_email(db, data.to_user_email)
        if not to_user:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        conn_type = ConnectionType(data.connection_type)
        existing = await get_active_conn(
            db, from_user_id=verified_user.id, to_user_id=to_user.id, connection_type=conn_type
        )
        if existing:
            raise ClientException(
                status_code=HTTP_409_CONFLICT,
                detail="Connection already exists",
            )

        conn = await create_conn(
            db,
            from_user_id=verified_user.id,
            to_user_id=to_user.id,
            connection_type=conn_type,
            initiated_by=verified_user.id,
        )

        email_svc = EmailService()
        inviter_name = verified_user.display_name or verified_user.email
        with contextlib.suppress(Exception):
            await email_svc.send_coaching_invite(
                to=to_user.email,
                inviter_name=inviter_name,
                connection_type=data.connection_type,
                locale=to_user.language,
            )

        return _conn_to_response(conn)

    @post("/{conn_id:str}/accept", status_code=HTTP_200_OK)
    async def accept_invite(
        self, conn_id: str, verified_user: VerifiedUser, db: DbDep
    ) -> ConnectionResponse:
        """Invitee accepts a connection."""
        conn = await get_conn_by_id(db, conn_id)
        if not conn:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Connection not found",
            )
        if conn.to_user_id != verified_user.id:
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )
        if conn.status != ConnectionStatus.INVITED:
            raise ClientException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Not an active invite",
            )
        conn.status = ConnectionStatus.ACTIVE
        db.add(conn)
        await db.flush()
        await db.refresh(conn)
        return _conn_to_response(conn)

    @post("/{conn_id:str}/end", status_code=HTTP_200_OK)
    async def end_connection(
        self, conn_id: str, verified_user: VerifiedUser, db: DbDep
    ) -> ConnectionResponse:
        """Either party ends the connection."""
        conn = await get_conn_by_id(db, conn_id)
        if not conn:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Connection not found",
            )
        if verified_user.id not in (conn.from_user_id, conn.to_user_id):
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )
        if conn.status == ConnectionStatus.ENDED:
            raise ClientException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Already ended",
            )
        conn.status = ConnectionStatus.ENDED
        conn.ended_at = datetime.now(UTC)
        db.add(conn)
        await db.flush()
        await db.refresh(conn)
        return _conn_to_response(conn)

    @get("")
    async def list_connections(self, user: CurrentUser, db: DbDep) -> ConnectionListResponse:
        """List all connections for the current user."""
        conns = await list_for_user(db, user.id)
        return ConnectionListResponse(
            total=len(conns), connections=[_conn_to_response(c) for c in conns]
        )

    @get("/pending")
    async def list_pending(self, user: CurrentUser, db: DbDep) -> ConnectionListResponse:
        """List pending invites received by the current user."""
        conns = await list_pending_for_user(db, user.id)
        return ConnectionListResponse(
            total=len(conns), connections=[_conn_to_response(c) for c in conns]
        )
