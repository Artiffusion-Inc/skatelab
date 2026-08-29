"""Contract tests for coach comments."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from app.auth.security import create_access_token, hash_password
from app.crud.notifications import count_by_user, list_by_user
from app.crud.session import create as create_session
from app.models.comment import CoachComment
from app.models.connection import Connection, ConnectionStatus, ConnectionType
from app.models.user import User
from app.services.notification_events import coach_comment_created
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def comment_coach(db_session: AsyncSession) -> User:
    coach = User(
        email="comment-coach@example.com",
        hashed_password=hash_password("pass"),
        display_name="Comment Coach",
        is_verified=True,
    )
    db_session.add(coach)
    await db_session.flush()
    await db_session.refresh(coach)
    return coach


@pytest_asyncio.fixture
async def comment_skater(db_session: AsyncSession) -> User:
    skater = User(
        email="comment-skater@example.com",
        hashed_password=hash_password("pass"),
        display_name="Comment Skater",
        is_verified=True,
    )
    db_session.add(skater)
    await db_session.flush()
    await db_session.refresh(skater)
    return skater


@pytest.fixture
def comment_coach_headers(comment_coach: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id=comment_coach.id)}"}


@pytest_asyncio.fixture
async def comment_session(db_session: AsyncSession, comment_skater: User):
    session = await create_session(
        db_session,
        user_id=comment_skater.id,
        element_type="axel",
        status="done",
    )
    return session


@pytest_asyncio.fixture
async def active_comment_connection(
    db_session: AsyncSession, comment_coach: User, comment_skater: User
) -> Connection:
    connection = Connection(
        from_user_id=comment_coach.id,
        to_user_id=comment_skater.id,
        connection_type=ConnectionType.COACHING,
        status=ConnectionStatus.ACTIVE,
        initiated_by=comment_coach.id,
    )
    db_session.add(connection)
    await db_session.flush()
    await db_session.refresh(connection)
    return connection


@pytest.mark.asyncio
async def test_coach_can_post_comment_for_connected_skater(
    client,
    comment_coach_headers: dict[str, str],
    comment_coach: User,
    comment_skater: User,
    comment_session,
    active_comment_connection: Connection,
    db_session: AsyncSession,
) -> None:
    response = await client.post(
        f"/v1/sessions/{comment_session.id}/comments",
        json={"content": "Keep your landing knee aligned."},
        headers=comment_coach_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"]
    assert data["session_id"] == comment_session.id
    assert data["coach_id"] == comment_coach.id
    assert data["content"] == "Keep your landing knee aligned."
    assert data["created_at"]

    result = await db_session.execute(select(CoachComment).where(CoachComment.id == data["id"]))
    comment = result.scalar_one()
    assert comment.session_id == comment_session.id
    assert comment.coach_id == comment_coach.id

    notifications = await list_by_user(db_session, comment_skater.id)
    assert len(notifications) == 1
    assert notifications[0].event_type == "coach.comment"
    assert notifications[0].source_id == comment.id
    assert notifications[0].deep_link == f"skatelab://coach-comments/{comment.id}"
    assert notifications[0].payload == {
        "comment_id": comment.id,
        "session_id": comment_session.id,
    }


@pytest.mark.asyncio
async def test_unconnected_coach_cannot_post_comment(
    client,
    comment_coach_headers: dict[str, str],
    comment_skater: User,
    comment_session,
    db_session: AsyncSession,
) -> None:
    response = await client.post(
        f"/v1/sessions/{comment_session.id}/comments",
        json={"content": "Private feedback"},
        headers=comment_coach_headers,
    )

    assert response.status_code == 403
    assert (
        await db_session.scalar(
            select(CoachComment).where(CoachComment.session_id == comment_session.id)
        )
        is None
    )
    assert await count_by_user(db_session, comment_skater.id) == 0


@pytest.mark.asyncio
async def test_invited_coach_cannot_post_comment(
    client,
    comment_coach_headers: dict[str, str],
    comment_coach: User,
    comment_skater: User,
    comment_session,
    db_session: AsyncSession,
) -> None:
    db_session.add(
        Connection(
            from_user_id=comment_coach.id,
            to_user_id=comment_skater.id,
            connection_type=ConnectionType.COACHING,
            status=ConnectionStatus.INVITED,
            initiated_by=comment_coach.id,
        )
    )
    await db_session.flush()

    response = await client.post(
        f"/v1/sessions/{comment_session.id}/comments",
        json={"content": "Private feedback"},
        headers=comment_coach_headers,
    )

    assert response.status_code == 403
    assert (
        await db_session.scalar(
            select(CoachComment).where(CoachComment.session_id == comment_session.id)
        )
        is None
    )


@pytest.mark.asyncio
async def test_comment_notification_producer_is_idempotent(
    db_session: AsyncSession, comment_skater: User, comment_session
) -> None:
    first = await coach_comment_created(
        db_session,
        user_id=comment_skater.id,
        comment_id="comment-retry",
        session_id=comment_session.id,
    )
    second = await coach_comment_created(
        db_session,
        user_id=comment_skater.id,
        comment_id="comment-retry",
        session_id=comment_session.id,
    )

    assert second.id == first.id
    assert await count_by_user(db_session, comment_skater.id) == 1


@pytest.mark.asyncio
async def test_comment_for_missing_session_returns_404(
    client, comment_coach_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/v1/sessions/missing-session/comments",
        json={"content": "No target"},
        headers=comment_coach_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_comment_content_is_required_and_bounded(
    client,
    comment_coach_headers: dict[str, str],
    comment_session,
    active_comment_connection: Connection,
) -> None:
    response = await client.post(
        f"/v1/sessions/{comment_session.id}/comments",
        json={"content": "   "},
        headers=comment_coach_headers,
    )

    assert response.status_code in {400, 422}

    response = await client.post(
        f"/v1/sessions/{comment_session.id}/comments",
        json={"content": "x" * 2001},
        headers=comment_coach_headers,
    )
    assert response.status_code in {400, 422}
