"""Tests for workspace API routes."""

import pytest
from app.auth.security import hash_password
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def member_user(db_session: AsyncSession) -> User:
    user = User(
        email="member@ice.com",
        hashed_password=hash_password("pass"),
        display_name="Member",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


async def test_create_workspace(client, auth_headers):
    response = await client.post(
        "/v1/workspaces",
        json={"name": "Ice Academy", "slug": "ice-academy"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Ice Academy"
    assert data["slug"] == "ice-academy"


async def test_list_workspaces(client, auth_headers, db_session):
    ws = Workspace(name="Ice", slug="ice-list")
    db_session.add(ws)
    await db_session.flush()
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == "user@example.com"))
    owner = result.scalar_one()
    member = WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role=WorkspaceRole.OWNER)
    db_session.add(member)
    await db_session.flush()

    response = await client.get("/v1/workspaces", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == ws.id


async def test_invite_member(client, auth_headers, member_user, db_session):
    ws = Workspace(name="Ice", slug="ice-invite")
    db_session.add(ws)
    await db_session.flush()
    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == "user@example.com"))
    owner = result.scalar_one()
    owner_member = WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role=WorkspaceRole.OWNER)
    db_session.add(owner_member)
    await db_session.flush()

    response = await client.post(
        f"/v1/workspaces/{ws.id}/invite",
        json={"email": "member@ice.com", "role": "coach"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == member_user.id
    assert data["role"] == "coach"
