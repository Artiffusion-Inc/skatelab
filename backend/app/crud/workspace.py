"""Workspace and WorkspaceMember CRUD operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.workspace import (
    Subscription,
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create_workspace(
    db: AsyncSession,
    *,
    name: str,
    slug: str,
    owner_id: str,
    description: str | None = None,
) -> Workspace:
    """Create a new workspace with owner as first member."""
    ws = Workspace(name=name, slug=slug, description=description)
    db.add(ws)
    await db.flush()
    await db.refresh(ws)

    member = WorkspaceMember(
        workspace_id=ws.id,
        user_id=owner_id,
        role=WorkspaceRole.OWNER,
        joined_at=datetime.now(UTC),
    )
    db.add(member)

    sub = Subscription(workspace_id=ws.id, plan="free", status="trial")
    db.add(sub)

    await db.flush()
    return ws


async def get_workspace_by_id(db: AsyncSession, workspace_id: str) -> Workspace | None:
    """Get workspace by ID."""
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    return result.scalar_one_or_none()


async def get_workspace_by_slug(db: AsyncSession, slug: str) -> Workspace | None:
    """Get workspace by slug."""
    result = await db.execute(select(Workspace).where(Workspace.slug == slug))
    return result.scalar_one_or_none()


async def count_workspaces_for_user(db: AsyncSession, user_id: str) -> int:
    """Count workspaces a user is a member of. #740: per-user limit."""
    result = await db.execute(
        select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.user_id == user_id)
    )
    return result.scalar_one()


async def list_workspaces_for_user(db: AsyncSession, user_id: str) -> list[Workspace]:
    """List all workspaces a user is a member of."""
    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMember)
        .where(WorkspaceMember.user_id == user_id, Workspace.is_active.is_(True))
        .order_by(Workspace.created_at.desc())
    )
    return list(result.scalars().all())


async def add_workspace_member(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    role: WorkspaceRole,
    invited_by: str | None = None,
) -> WorkspaceMember:
    """Add a member to a workspace."""
    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
        joined_at=datetime.now(UTC),
        invited_by=invited_by,
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member


async def get_workspace_member(
    db: AsyncSession, workspace_id: str, user_id: str
) -> WorkspaceMember | None:
    """Get a specific workspace membership."""
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_workspace_members(db: AsyncSession, workspace_id: str) -> list[WorkspaceMember]:
    """List all members of a workspace."""
    result = await db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.joined_at.desc())
    )
    return list(result.scalars().all())


async def remove_workspace_member(db: AsyncSession, workspace_id: str, user_id: str) -> bool:
    """Remove a member from a workspace. Returns True if removed."""
    member = await get_workspace_member(db, workspace_id, user_id)
    if member is None:
        return False
    await db.delete(member)
    await db.flush()
    return True


async def update_member_role(
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
    new_role: WorkspaceRole,
) -> WorkspaceMember | None:
    """Update a member's role."""
    member = await get_workspace_member(db, workspace_id, user_id)
    if member is None:
        return None
    member.role = new_role
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member
