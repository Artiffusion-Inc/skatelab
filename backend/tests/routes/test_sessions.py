"""Tests for sessions CRUD routes."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from app.auth.security import create_access_token, hash_password
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    user = User(email="other@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def other_headers(other_user):
    token = create_access_token(user_id=other_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def coach_user(db_session: AsyncSession) -> User:
    user = User(email="coach@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def skater_user(db_session: AsyncSession) -> User:
    user = User(email="skater@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def coach_headers(coach_user):
    token = create_access_token(user_id=coach_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def skater_headers(skater_user):
    token = create_access_token(user_id=skater_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def coaching_connection(db_session: AsyncSession, coach_user, skater_user):
    """Create an active coaching connection: coach -> skater."""
    from app.models.connection import Connection, ConnectionStatus, ConnectionType

    conn = Connection(
        from_user_id=coach_user.id,
        to_user_id=skater_user.id,
        connection_type=ConnectionType.COACHING,
        status=ConnectionStatus.ACTIVE,
        initiated_by=coach_user.id,
    )
    db_session.add(conn)
    await db_session.flush()
    await db_session.refresh(conn)
    return conn


@pytest.mark.asyncio
async def test_create_session(client, auth_headers, db_session: AsyncSession):
    """POST /sessions with element_type returns 201 and response fields."""
    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.post(
            "/v1/sessions",
            json={"element_type": "waltz_jump"},
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["element_type"] == "waltz_jump"
    assert data["status"] == "uploading"
    assert data["user_id"]
    assert data["id"]
    assert data["created_at"]


@pytest.mark.asyncio
async def test_create_session_with_video_key(client, auth_headers, db_session: AsyncSession):
    """POST /sessions with video_key sets status to 'queued'."""
    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.post(
            "/v1/sessions",
            json={"element_type": "toe_loop", "video_key": "uploads/user123/video.mp4"},
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "queued"
    assert data["video_key"] == "uploads/user123/video.mp4"
    assert data["video_url"] == "https://fake.url"


@pytest.mark.asyncio
async def test_create_session_without_video_key(client, auth_headers, db_session: AsyncSession):
    """POST /sessions without video_key sets status to 'uploading'."""
    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.post(
            "/v1/sessions",
            json={"element_type": "flip"},
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "uploading"
    assert data["video_key"] is None


@pytest.mark.asyncio
async def test_list_sessions(client, auth_headers, authed_user, db_session: AsyncSession):
    """GET /sessions returns list with total count."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        await crud_create(db_session, user_id=authed_user.id, element_type="waltz_jump")
        await crud_create(db_session, user_id=authed_user.id, element_type="toe_loop")

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get("/v1/sessions", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["sessions"]) == 2
    assert data["has_more"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_sessions_filter_element_type(
    client, auth_headers, authed_user, db_session: AsyncSession
):
    """GET /sessions?element_type=... filters by element type."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        await crud_create(db_session, user_id=authed_user.id, element_type="waltz_jump")
        await crud_create(db_session, user_id=authed_user.id, element_type="toe_loop")

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get(
            "/v1/sessions",
            params={"element_type": "waltz_jump"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["sessions"][0]["element_type"] == "waltz_jump"
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_list_sessions_coach_access_denied(
    client, auth_headers, other_user, db_session: AsyncSession
):
    """GET /sessions?user_id=other without coaching connection returns 403."""
    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get(
            "/v1/sessions",
            params={"user_id": other_user.id},
            headers=auth_headers,
        )

    assert response.status_code == 403
    data = response.json()
    assert "Not a coach" in data["message"]


@pytest.mark.asyncio
async def test_get_session(client, auth_headers, authed_user, db_session: AsyncSession):
    """GET /sessions/{id} returns the session."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        session = await crud_create(db_session, user_id=authed_user.id, element_type="axel")

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get(f"/v1/sessions/{session.id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == session.id
    assert data["element_type"] == "axel"


@pytest.mark.asyncio
async def test_get_session_not_found(client, auth_headers):
    """GET /sessions/{id} with nonexistent id returns 404."""
    response = await client.get("/v1/sessions/nonexistent-id", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_session_forbidden(client, other_headers, authed_user, db_session: AsyncSession):
    """GET /sessions/{id} for another user's session returns 403."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        session = await crud_create(db_session, user_id=authed_user.id, element_type="lutz")

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get(f"/v1/sessions/{session.id}", headers=other_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_session(client, auth_headers, authed_user, db_session: AsyncSession):
    """PATCH /sessions/{id} updates element_type."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        session = await crud_create(db_session, user_id=authed_user.id, element_type="flip")

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.patch(
            f"/v1/sessions/{session.id}",
            json={"element_type": "lutz"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["element_type"] == "lutz"


@pytest.mark.asyncio
async def test_patch_session_not_found(client, auth_headers):
    """PATCH /sessions/{id} with nonexistent id returns 404."""
    response = await client.patch(
        "/v1/sessions/nonexistent-id",
        json={"element_type": "lutz"},
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_session(client, auth_headers, authed_user, db_session: AsyncSession):
    """DELETE /sessions/{id} returns 204 and soft-deletes the session."""
    from app.crud.session import create as crud_create
    from app.crud.session import get_by_id

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        session = await crud_create(db_session, user_id=authed_user.id, element_type="salchow")

    response = await client.delete(f"/v1/sessions/{session.id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify soft-deleted (status changed to "deleted")
    await db_session.refresh(session)
    assert session.status == "deleted"


@pytest.mark.asyncio
async def test_delete_session_not_found(client, auth_headers):
    """DELETE /sessions/{id} with nonexistent id returns 404."""
    response = await client.delete("/v1/sessions/nonexistent-id", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_forbidden(
    client, other_headers, authed_user, db_session: AsyncSession
):
    """DELETE /sessions/{id} for another user's session returns 403."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        session = await crud_create(db_session, user_id=authed_user.id, element_type="loop")

    response = await client.delete(f"/v1/sessions/{session.id}", headers=other_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_sessions_coach_allowed(
    client, coach_headers, skater_user, coaching_connection, db_session: AsyncSession
):
    """GET /sessions?user_id=skater with active coaching connection returns 200."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        await crud_create(db_session, user_id=skater_user.id, element_type="waltz_jump")

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get(
            "/v1/sessions",
            params={"user_id": skater_user.id},
            headers=coach_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["sessions"][0]["element_type"] == "waltz_jump"
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_get_session_coach_allowed(
    client, coach_headers, skater_user, coaching_connection, db_session: AsyncSession
):
    """GET /sessions/{id} for student's session returns 200 when coach."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        session = await crud_create(db_session, user_id=skater_user.id, element_type="axel")

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get(f"/v1/sessions/{session.id}", headers=coach_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == session.id


@pytest.mark.asyncio
async def test_list_sessions_cursor_pagination(
    client, auth_headers, authed_user, db_session: AsyncSession
):
    """Cursor pagination: limit=2 on 3 sessions returns has_more + next_cursor,
    and second page returns the remaining session with has_more=False."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        await crud_create(db_session, user_id=authed_user.id, element_type="flip")
        await crud_create(db_session, user_id=authed_user.id, element_type="lutz")
        await crud_create(db_session, user_id=authed_user.id, element_type="axel")

    # First page: limit=2, expect 2 sessions and has_more=True
    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get(
            "/v1/sessions",
            params={"limit": 2},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["sessions"]) == 2
    assert data["has_more"] is True
    assert data["next_cursor"] is not None
    assert data["total"] == 3

    # Second page using cursor
    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response2 = await client.get(
            "/v1/sessions",
            params={"limit": 2, "cursor": data["next_cursor"]},
            headers=auth_headers,
        )

    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["sessions"]) == 1
    assert data2["has_more"] is False
    assert data2["next_cursor"] is None
    assert data2["total"] == 3


@pytest.mark.asyncio
async def test_list_sessions_invalid_cursor(
    client, auth_headers, authed_user, db_session: AsyncSession
):
    """Malformed cursor returns 400."""
    response = await client.get(
        "/v1/sessions",
        params={"cursor": "not-a-valid-cursor"},
        headers=auth_headers,
    )

    assert response.status_code == 400
