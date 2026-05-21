"""Authentication dependencies for Litestar."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from litestar.exceptions import NotAuthorizedException
from litestar.params import Dependency
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.crud.workspace import get_workspace_member
from app.models.user import User
from app.models.workspace import WorkspaceMember, WorkspaceRole

if TYPE_CHECKING:
    from litestar import Request
    from litestar.connection import ASGIConnection


async def retrieve_user_handler(token: Any, connection: ASGIConnection) -> User | None:
    """Litestar JWTAuth callback: decode token and fetch user from DB."""
    user_id = getattr(token, "sub", None)
    if user_id is None and callable(getattr(token, "get", None)):
        user_id = token.get("sub")
    if not user_id:
        return None

    # Tests inject session via app.state; prod creates a fresh one.
    db = getattr(connection.app.state, "test_db_session", None)
    if db is None:
        from app.database import async_session_factory

        async with async_session_factory() as db:
            result = await db.execute(
                select(User).where(User.id == user_id, User.is_active.is_(True))
            )
            return result.scalar_one_or_none()
    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    return result.scalar_one_or_none()


async def get_current_user(request: Request, db: AsyncSession) -> User:
    """Return the currently authenticated user.

    Used as a dependency provider for routes that need the user object.
    When APP_SKIP_AUTH=true, returns the first active user.
    """
    if get_settings().app.skip_auth:
        result = await db.execute(
            select(User).where(User.is_active.is_(True)).order_by(User.created_at).limit(1)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotAuthorizedException("No active users in database. Create one first.")
        return user

    # Normal JWT flow: request.user is set by JWTAuth middleware
    user = request.user
    if user is None or not getattr(user, "is_active", False):
        raise NotAuthorizedException("Could not validate credentials")
    return user


# Type alias for clean injection in route signatures
CurrentUser = Annotated[User, Dependency()]
DbDep = Annotated[AsyncSession, Dependency()]


async def get_verified_user(user: CurrentUser) -> User:
    """Dependency that requires the user to have verified their email."""
    if not user.is_verified:
        raise NotAuthorizedException(
            detail="Email verification required. Please check your inbox or request a new verification link."
        )
    return user


VerifiedUser = Annotated[User, Dependency()]


async def require_workspace_role(
    workspace_id: str,
    user: User,
    db: AsyncSession,
    min_role: WorkspaceRole = WorkspaceRole.STUDENT,
) -> WorkspaceMember:
    """Require user to have at least min_role in workspace."""
    member = await get_workspace_member(db, workspace_id, user.id)
    if member is None:
        raise NotAuthorizedException("Not a member of this workspace")
    # Simple hierarchy: owner > admin > coach > student > parent
    hierarchy = {
        WorkspaceRole.OWNER: 4,
        WorkspaceRole.ADMIN: 3,
        WorkspaceRole.COACH: 2,
        WorkspaceRole.STUDENT: 1,
        WorkspaceRole.PARENT: 0,
    }
    if hierarchy.get(member.role, -1) < hierarchy.get(min_role, -1):
        raise NotAuthorizedException("Insufficient workspace permissions")
    return member
