"""Workspace API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from collections.abc import Sequence

from litestar import Controller, delete, get, patch, post
from litestar.exceptions import ClientException, NotFoundException
from litestar.status_codes import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from app.auth.deps import CurrentUser, DbDep, VerifiedUser, require_workspace_role
from app.crud.user import get_by_email
from app.crud.workspace import (
    add_workspace_member,
    create_workspace,
    get_workspace_by_id,
    get_workspace_by_slug,
    get_workspace_member,
    list_workspace_members,
    list_workspaces_for_user,
    remove_workspace_member,
    update_member_role,
)
from app.models.workspace import WorkspaceRole
from app.schemas import (
    CreateWorkspaceRequest,
    InviteMemberRequest,
    WorkspaceMemberResponse,
    WorkspaceResponse,
)


class WorkspacesController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["workspaces"]

    @post("", status_code=HTTP_201_CREATED)
    async def create(
        self, data: CreateWorkspaceRequest, verified_user: VerifiedUser, db: DbDep
    ) -> WorkspaceResponse:
        existing = await get_workspace_by_slug(db, data.slug)
        if existing:
            raise ClientException(detail="Workspace slug already taken")
        ws = await create_workspace(
            db,
            name=data.name,
            slug=data.slug,
            owner_id=verified_user.id,
            description=data.description,
        )
        return WorkspaceResponse.model_validate(ws)

    @get("")
    async def list(self, user: CurrentUser, db: DbDep) -> list[WorkspaceResponse]:
        workspaces = await list_workspaces_for_user(db, user.id)
        return [WorkspaceResponse.model_validate(w) for w in workspaces]

    @get("/{workspace_id:str}")
    async def get_workspace(
        self, workspace_id: str, user: CurrentUser, db: DbDep
    ) -> WorkspaceResponse:
        await require_workspace_role(workspace_id, user, db)
        ws = await get_workspace_by_id(db, workspace_id)
        if not ws:
            raise NotFoundException(detail="Workspace not found")
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
        target = await get_by_email(db, data.email)
        if not target:
            raise ClientException(detail="User not found")
        member = await add_workspace_member(
            db,
            workspace_id=workspace_id,
            user_id=target.id,
            role=WorkspaceRole(data.role),
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
        # #466: removing the OWNER orphans the workspace (no one left to
        # admin it). Only the OWNER may remove themselves; an ADMIN must not
        # delete the OWNER row.
        target = await get_workspace_member(db, workspace_id, user_id)
        if (
            target is not None
            and target.role == WorkspaceRole.OWNER
            and target.user_id != verified_user.id
        ):
            raise ClientException(status_code=403, detail="Cannot remove the workspace owner")
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
        target = await get_workspace_member(db, workspace_id, user_id)
        # #466: broken access control guards — check the TARGET, not just the caller.
        # (a) Never demote/remove the OWNER via role change: an ADMIN demoting the
        #     OWNER is irreversible (the role pattern excludes "owner", so it can't
        #     be undone) and seizes control of the workspace.
        if target is not None and target.role == WorkspaceRole.OWNER:
            raise ClientException(
                status_code=403, detail="Cannot change the workspace owner's role"
            )
        # (b) Promotion to ADMIN is owner-only: an ADMIN promoting a STUDENT peer
        #     to admin is horizontal privilege escalation.
        if new_role == WorkspaceRole.ADMIN and caller.role != WorkspaceRole.OWNER:
            raise ClientException(
                status_code=403, detail="Only the owner may promote members to admin"
            )
        updated = await update_member_role(db, workspace_id, user_id, new_role)
        if not updated:
            raise NotFoundException(detail="Member not found")
        return WorkspaceMemberResponse.model_validate(updated)
