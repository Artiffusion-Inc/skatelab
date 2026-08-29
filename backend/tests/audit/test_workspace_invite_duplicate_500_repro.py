"""RED repro — workspaces re-invite existing member → IntegrityError 500.

BUG (MEDIUM — missing-upsert-on-unique / unhandled-IntegrityError, #493 mirror
in the invite route):
    backend/app/crud/workspace.py:73-92 `add_workspace_member`: plain `db.add`,
    no check-existing / upsert / ON CONFLICT. `db.flush()` raises
    IntegrityError on the second insert against the
    `uq_workspace_member` unique(workspace_id, user_id) index
    (backend/app/models/workspace.py:121).

    backend/app/routes/workspaces.py:71-93 `invite`: calls
    `add_workspace_member` directly — no `get_workspace_member` pre-check, no
    `IntegrityError` handling, no `try/except`. `backend/app/main.py` registers
    no global IntegrityError handler (only the default HTTPException path).

    ADMIN/OWNER re-invites a user who is ALREADY a member (same email) →
    `add_workspace_member` inserts a duplicate WorkspaceMember row → flush()
    raises IntegrityError → unhandled → 500 Internal Server Error instead of
    a clean 4xx Conflict / "already a member".

Result: re-invite is plausible (weak-network client retry, admin forgot they
already invited, double-submit). A 500 reads as a server fault ("try again
later") and breaks invite idempotency. The existing test
`test_invite_member` (backend/tests/test_workspace_routes.py) covers only the
single-success happy path — no duplicate-invite test.

These tests assert the invite route returns a clean 4xx (409 Conflict /
400 Bad Request) for a duplicate. They currently return 500 → RED.

Mandate: RED tests only. No production code edits, no fix-PR.
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
                secret_key=MagicMock(
                    get_secret_value=lambda: "test-secret-key-for-backend-tests-32b"
                ),
                access_token_expire_minutes=15,
            )
        )
        return create_access_token(user_id=user.id)


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(user)}"}


async def _seed(
    db_session: AsyncSession,
) -> tuple[Workspace, User, User]:
    """Create a workspace with OWNER (O) + an already-member STUDENT (B)."""
    owner = User(
        email="owner@ice.com",
        hashed_password=hash_password("pass"),
        display_name="Owner",
        is_verified=True,
    )
    member_b = User(
        email="b@ice.com",
        hashed_password=hash_password("pass"),
        display_name="Member B",
        is_verified=True,
    )
    db_session.add_all([owner, member_b])
    await db_session.flush()

    ws = Workspace(name="Dup Invite Repro", slug="dup-invite-repro")
    db_session.add(ws)
    await db_session.flush()

    # Owner + an ALREADY-existing member B (coach role).
    db_session.add_all(
        [
            WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role=WorkspaceRole.OWNER),
            WorkspaceMember(workspace_id=ws.id, user_id=member_b.id, role=WorkspaceRole.COACH),
        ]
    )
    await db_session.flush()
    return ws, owner, member_b


async def test_invite_existing_member_returns_conflict_not_500(
    client: AsyncTestClient, db_session: AsyncSession
):
    """OWNER re-invites a user who is already a member → must be clean 4xx.

    RED now: 500 (IntegrityError from the unique index, unhandled by the
    invite route / no global handler).
    """
    ws, owner, member_b = await _seed(db_session)

    response = await client.post(
        f"/v1/workspaces/{ws.id}/invite",
        json={"email": member_b.email, "role": "student"},
        headers=_headers(owner),
    )
    assert response.status_code in (409, 400), (
        f"BUG: re-inviting an existing member returned {response.status_code} "
        f"(500 = unhandled IntegrityError from uq_workspace_member unique "
        f"index; add_workspace_member has no check-existing/upsert and the "
        f"invite route has no IntegrityError handling). Expected 409 Conflict "
        f"or 400 Bad Request ('already a member'). Body: {response.text}"
    )


async def test_admin_re_invite_existing_member_returns_conflict_not_500(
    client: AsyncTestClient, db_session: AsyncSession
):
    """ADMIN re-invites an existing member → must be clean 4xx (not 500).

    ADMIN has invite rights (require_workspace_role min_role=ADMIN) and the
    duplicate path is the same. RED now: 500.
    """
    ws, _owner, member_b = await _seed(db_session)
    admin = User(
        email="admin@ice.com",
        hashed_password=hash_password("pass"),
        display_name="Admin",
        is_verified=True,
    )
    db_session.add(admin)
    await db_session.flush()
    db_session.add(WorkspaceMember(workspace_id=ws.id, user_id=admin.id, role=WorkspaceRole.ADMIN))
    await db_session.flush()

    response = await client.post(
        f"/v1/workspaces/{ws.id}/invite",
        json={"email": member_b.email, "role": "student"},
        headers=_headers(admin),
    )
    assert response.status_code in (409, 400), (
        f"BUG: ADMIN re-inviting an existing member returned "
        f"{response.status_code} (500 = unhandled IntegrityError). Expected "
        f"409/400. Body: {response.text}"
    )
