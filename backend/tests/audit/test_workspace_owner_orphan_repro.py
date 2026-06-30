"""RED repro — workspaces ADMIN can remove/demote the OWNER (broken access control).

BUG (HIGH, security-adjacent — broken access control / horizontal privilege escalation /
irreversible orphan):
    backend/app/routes/workspaces.py:102-107 `remove_member` and :109-122 `update_role`
    gate the CALLER via `require_workspace_role(min_role=WorkspaceRole.ADMIN)` but never
    inspect the TARGET member's role. CRUD (backend/app/crud/workspace.py:118-142)
    `remove_workspace_member` / `update_member_role` blindly delete/overwrite any row,
    including the OWNER row.

    backend/app/auth/deps.py:83-103 `require_workspace_role` only checks the caller's
    rank against `min_role`, never the target's role.

    backend/app/schemas.py:171 `InviteMemberRequest.role` pattern is
    `^(admin|coach|student|parent)$` — "owner" is NOT in the allowed set, so an ADMIN
    can demote the OWNER to "parent" (or any of admin/coach/student/parent) via
    PATCH .../role, but cannot restore them to owner (pattern rejects "owner").

Result:
  - ADMIN removes OWNER → workspace orphaned (no OWNER, no one can re-admin it).
  - ADMIN demotes OWNER to parent → owner loses control; cannot be re-promoted
    (role pattern excludes "owner"), so the demotion is irreversible.
  - ADMIN promotes a STUDENT peer to admin → peer escalation.

These tests assert the routes REFUSE (403/400). They currently return 204/200 → RED.
"""

import pytest
from app.auth.security import create_access_token, hash_password
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from litestar.testing import AsyncTestClient
from sqlalchemy.ext.asyncio import AsyncSession


def _make_token(user: User) -> str:
    """Create a real JWT for the given user (matches conftest.auth_headers)."""
    from unittest.mock import MagicMock, patch

    with patch("app.auth.security.get_settings") as mock_get:
        mock_get.return_value = MagicMock(
            jwt=MagicMock(
                secret_key=MagicMock(get_secret_value=lambda: "test-secret"),
                access_token_expire_minutes=15,
            )
        )
        return create_access_token(user_id=user.id)


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(user)}"}


async def _seed(
    db_session: AsyncSession, client: AsyncTestClient
) -> tuple[Workspace, User, User, User]:
    """Create a workspace with OWNER (O), ADMIN (A, the attacker), STUDENT (S)."""
    owner = User(
        email="owner@ice.com",
        hashed_password=hash_password("pass"),
        display_name="Owner",
        is_verified=True,
    )
    admin = User(
        email="admin@ice.com",
        hashed_password=hash_password("pass"),
        display_name="Admin",
        is_verified=True,
    )
    student = User(
        email="student@ice.com",
        hashed_password=hash_password("pass"),
        display_name="Student",
        is_verified=True,
    )
    db_session.add_all([owner, admin, student])
    await db_session.flush()

    ws = Workspace(name="Orphan Repro", slug="orphan-repro")
    db_session.add(ws)
    await db_session.flush()

    db_session.add_all(
        [
            WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role=WorkspaceRole.OWNER),
            WorkspaceMember(workspace_id=ws.id, user_id=admin.id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(workspace_id=ws.id, user_id=student.id, role=WorkspaceRole.STUDENT),
        ]
    )
    await db_session.flush()
    return ws, owner, admin, student


async def test_admin_cannot_remove_owner(client, db_session):
    """1a: ADMIN removes OWNER → must be refused. RED now: 204 (owner deleted)."""
    ws, owner, admin, _student = await _seed(db_session, client)

    response = await client.delete(
        f"/v1/workspaces/{ws.id}/members/{owner.id}",
        headers=_headers(admin),
    )
    assert response.status_code in (403, 400), (
        f"BUG #1a: ADMIN removed the OWNER — workspace orphaned. "
        f"Expected 403/400, got {response.status_code} (204 = owner row deleted)."
    )


async def test_admin_cannot_demote_owner(client, db_session):
    """1b: ADMIN demotes OWNER to parent → must be refused. RED now: 200 (owner demoted)."""
    ws, owner, admin, _student = await _seed(db_session, client)

    response = await client.patch(
        f"/v1/workspaces/{ws.id}/members/{owner.id}/role",
        json={"email": owner.email, "role": "parent"},
        headers=_headers(admin),
    )
    assert response.status_code in (403, 400), (
        f"BUG #1b: ADMIN demoted the OWNER to parent — irreversible (role pattern "
        f"^(admin|coach|student|parent)$ excludes 'owner', so cannot be restored). "
        f"Expected 403/400, got {response.status_code}."
    )


async def test_admin_cannot_promote_peer_student_to_admin(client, db_session):
    """1c: ADMIN promotes a STUDENT peer to admin → must be refused (only OWNER can).

    RED now: 200 (peer escalated to admin).
    """
    ws, _owner, admin, student = await _seed(db_session, client)

    response = await client.patch(
        f"/v1/workspaces/{ws.id}/members/{student.id}/role",
        json={"email": student.email, "role": "admin"},
        headers=_headers(admin),
    )
    assert response.status_code in (403, 400), (
        f"BUG #1c: ADMIN promoted a STUDENT peer to admin — privilege escalation. "
        f"Expected 403/400, got {response.status_code}."
    )
