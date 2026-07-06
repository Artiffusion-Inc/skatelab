"""Workspace API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from collections.abc import Sequence

from litestar import Controller, delete, get, patch, post
from litestar.exceptions import ClientException, NotFoundException
from litestar.status_codes import HTTP_201_CREATED, HTTP_204_NO_CONTENT, HTTP_409_CONFLICT
from sqlalchemy.exc import IntegrityError

from app.auth.deps import CurrentUser, DbDep, VerifiedUser, require_workspace_role
from app.crud.user import get_by_email
from app.crud.workspace import (
    add_workspace_member,
    count_workspaces_for_user,
    create_workspace,
    get_workspace_by_id,
    get_workspace_member,
    list_workspace_members,
    list_workspaces_for_user,
    remove_workspace_member,
    update_member_role,
)
from app.middleware.rate_limit import check_rate_limit
from app.models.workspace import WorkspaceRole
from app.schemas import (
    CreateWorkspaceRequest,
    InviteMemberRequest,
    WorkspaceMemberResponse,
    WorkspaceResponse,
)

MAX_WORKSPACES_PER_USER = 50  # #740: per-user workspace count limit


class WorkspacesController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["workspaces"]

    @post("", status_code=HTTP_201_CREATED)
    async def create(
        self, data: CreateWorkspaceRequest, verified_user: VerifiedUser, db: DbDep
    ) -> WorkspaceResponse:
        # #740: per-user workspace count limit
        ws_count = await count_workspaces_for_user(db, verified_user.id)
        if ws_count >= MAX_WORKSPACES_PER_USER:
            raise ClientException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Workspace limit reached (max {MAX_WORKSPACES_PER_USER})",
            )
        # #731: slug collision race — try/except IntegrityError
        try:
            ws = await create_workspace(
                db,
                name=data.name,
                slug=data.slug,
                owner_id=verified_user.id,
                description=data.description,
            )
        except IntegrityError:
            raise ClientException(
                status_code=HTTP_409_CONFLICT,
                detail="Workspace slug already taken",
            ) from None
        return WorkspaceResponse.model_validate(ws)

    @get("")
    async def list(self, user: CurrentUser, db: DbDep) -> list[WorkspaceResponse]:
        workspaces = await list_workspaces_for_user(db, user.id)
        return [WorkspaceResponse.model_validate(w) for w in workspaces]

    @get("/{workspace_id:str}")
    async def get_workspace(
        self, workspace_id: str, user: CurrentUser, db: DbDep
    ) -> WorkspaceResponse:
        # #735: check existence before role — 404 not 403 for nonexistent
        ws = await get_workspace_by_id(db, workspace_id)
        if not ws:
            raise NotFoundException(detail="Workspace not found")
        await require_workspace_role(workspace_id, user, db)
        return WorkspaceResponse.model_validate(ws)

    @post("/{workspace_id:str}/invite", status_code=HTTP_201_CREATED)
    async def invite(
        self,
        workspace_id: str,
        data: InviteMemberRequest,
        verified_user: VerifiedUser,
        db: DbDep,
    ) -> WorkspaceMemberResponse:
        await require_workspace_role(workspace_id, verified_user, db, min_role=WorkspaceRole.ADMIN)
        # #741: rate limit invites
        await check_rate_limit(
            f"workspace:invite:{verified_user.id}", max_requests=20, window_seconds=300
        )
        # #733: no self-invite
        target = await get_by_email(db, data.email)
        if not target:
            raise ClientException(detail="User not found")
        if target.id == verified_user.id:
            raise ClientException(status_code=HTTP_409_CONFLICT, detail="Cannot invite yourself")
        # #742: check target is_active
        if not target.is_active:
            raise ClientException(detail="User account is deactivated")
        # #508 + #734: re-inviting existing member → clean 409
        existing = await get_workspace_member(db, workspace_id, target.id)
        if existing is not None:
            raise ClientException(status_code=HTTP_409_CONFLICT, detail="Already a member")
        # #732: ADMIN cannot invite another ADMIN — only OWNER can
        new_role = WorkspaceRole(data.role)
        if new_role == WorkspaceRole.ADMIN:
            caller = await get_workspace_member(db, workspace_id, verified_user.id)
            if caller is None or caller.role != WorkspaceRole.OWNER:
                raise ClientException(status_code=403, detail="Only the owner may invite admins")
        member = await add_workspace_member(
            db,
            workspace_id=workspace_id,
            user_id=target.id,
            role=new_role,
            invited_by=verified_user.id,
        )
        resp = WorkspaceMemberResponse.model_validate(member)
        resp.user_name = target.display_name or target.email
        resp.user_email = target.email
        return resp

    @get("/{workspace_id:str}/members")
    async def list_members(
        self, workspace_id: str, user: CurrentUser, db: DbDep
    ) -> list[WorkspaceMemberResponse]:
        await require_workspace_role(workspace_id, user, db)
        members = await list_workspace_members(db, workspace_id)
        return [WorkspaceMemberResponse.model_validate(m) for m in members]

    @delete("/{workspace_id:str}/members/{user_id:str}", status_code=HTTP_204_NO_CONTENT)
    async def remove_member(
        self, workspace_id: str, user_id: str, verified_user: VerifiedUser, db: DbDep
    ) -> None:
        await require_workspace_role(workspace_id, verified_user, db, min_role=WorkspaceRole.ADMIN)
        # #466: removing the OWNER orphans the workspace
        target = await get_workspace_member(db, workspace_id, user_id)
        # #737: 404 on non-existent member instead of silent 204
        if target is None:
            raise NotFoundException(detail="Member not found")
        if target.role == WorkspaceRole.OWNER and target.user_id != verified_user.id:
            raise ClientException(status_code=403, detail="Cannot remove the workspace owner")
        # #736: last-admin guard — don't remove the last admin/owner
        if target.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
            members = await list_workspace_members(db, workspace_id)
            admin_count = sum(
                1
                for m in members
                if m.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN) and m.user_id != user_id
            )
            if admin_count == 0:
                raise ClientException(status_code=403, detail="Cannot remove the last admin")
        await remove_workspace_member(db, workspace_id, user_id)

    @patch("/{workspace_id:str}/members/{user_id:str}/role")
    async def update_role(
        self,
        workspace_id: str,
        user_id: str,
        data: InviteMemberRequest,
        verified_user: VerifiedUser,
        db: DbDep,
    ) -> WorkspaceMemberResponse:
        caller = await require_workspace_role(
            workspace_id, verified_user, db, min_role=WorkspaceRole.ADMIN
        )
        new_role = WorkspaceRole(data.role)
        # #739: no self-demotion — admin demoting themselves locks them out
        if user_id == verified_user.id and new_role != caller.role:
            raise ClientException(status_code=403, detail="Cannot change your own role")
        target = await get_workspace_member(db, workspace_id, user_id)
        # #466: cannot change the owner's role
        if target is not None and target.role == WorkspaceRole.OWNER:
            raise ClientException(
                status_code=403, detail="Cannot change the workspace owner's role"
            )
        if target is None:
            raise NotFoundException(detail="Member not found")
        # #732: promotion to ADMIN is owner-only
        if new_role == WorkspaceRole.ADMIN and caller.role != WorkspaceRole.OWNER:
            raise ClientException(
                status_code=403, detail="Only the owner may promote members to admin"
            )
        updated = await update_member_role(db, workspace_id, user_id, new_role)
        if not updated:
            raise NotFoundException(detail="Member not found")
        return WorkspaceMemberResponse.model_validate(updated)
