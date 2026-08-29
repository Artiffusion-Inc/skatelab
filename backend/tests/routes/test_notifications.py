"""Tests for the notifications API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from app.auth.security import create_access_token, hash_password
from app.crud.notifications import create as create_notification
from app.models.notifications import Notification
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    user = User(email="notifications-other@example.com", hashed_password=hash_password("pass"))
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_notifications_list_is_owned_and_includes_action(
    client, auth_headers, authed_user, db_session
):
    await create_notification(
        db_session,
        user_id=authed_user.id,
        event_type="analysis.completed",
        title="Анализ готов",
        body="Ваш анализ завершён",
        deep_link="skatelab://session/session-1",
        payload={"session_id": "session-1"},
    )
    await create_notification(
        db_session,
        user_id=authed_user.id,
        event_type="training.assigned",
        title="Новая тренировка",
        body="Откройте план",
        deep_link="skatelab://training/plan-1",
        payload={"training_plan_id": "plan-1"},
    )

    response = await client.get("/v1/notifications", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["unread_count"] == 2
    notification = next(
        item for item in data["notifications"] if item["event_type"] == "training.assigned"
    )
    assert notification["deep_link"] == "skatelab://training/plan-1"
    assert notification["payload"] == {"training_plan_id": "plan-1"}
    assert notification["is_read"] is False
    assert notification["read_at"] is None


@pytest.mark.asyncio
async def test_notifications_unread_count_and_mark_read(
    client, auth_headers, authed_user, db_session
):
    notification = await create_notification(
        db_session,
        user_id=authed_user.id,
        event_type="coach.comment",
        title="Комментарий тренера",
        body="Проверьте комментарий",
        deep_link="skatelab://coach-comments/comment-1",
        payload={"comment_id": "comment-1"},
    )

    count = await client.get("/v1/notifications/unread-count", headers=auth_headers)
    assert count.status_code == 200
    assert count.json() == {"unread_count": 1}

    marked = await client.post(f"/v1/notifications/{notification.id}/read", headers=auth_headers)
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True
    assert marked.json()["read_at"] is not None

    count = await client.get("/v1/notifications/unread-count", headers=auth_headers)
    assert count.json() == {"unread_count": 0}


@pytest.mark.asyncio
async def test_notifications_read_all_and_unread_filter(
    client, auth_headers, authed_user, db_session
):
    first = await create_notification(
        db_session,
        user_id=authed_user.id,
        event_type="export.ready",
        title="Экспорт готов",
        body="Скачайте отчёт",
        deep_link="skatelab://exports/export-1",
        payload={"export_id": "export-1"},
    )
    await create_notification(
        db_session,
        user_id=authed_user.id,
        event_type="analysis.failed",
        title="Ошибка анализа",
        body="Попробуйте ещё раз",
        deep_link="skatelab://session/session-2",
        payload={"session_id": "session-2"},
    )
    await client.post(f"/v1/notifications/{first.id}/read", headers=auth_headers)

    unread = await client.get(
        "/v1/notifications", params={"unread_only": "true"}, headers=auth_headers
    )
    assert unread.status_code == 200
    assert unread.json()["total"] == 1
    assert unread.json()["notifications"][0]["event_type"] == "analysis.failed"

    marked = await client.post("/v1/notifications/read-all", headers=auth_headers)
    assert marked.status_code == 200
    assert marked.json() == {"marked_read": 1}


@pytest.mark.asyncio
async def test_notifications_pagination_and_limit_validation(
    client, auth_headers, authed_user, db_session
):
    for index in range(3):
        await create_notification(
            db_session,
            user_id=authed_user.id,
            event_type="analysis.completed",
            title=f"Анализ {index}",
            body="Готово",
            deep_link=f"skatelab://session/{index}",
            payload={"session_id": str(index)},
        )

    page = await client.get(
        "/v1/notifications",
        params={"page": 1, "page_size": 2},
        headers=auth_headers,
    )
    assert page.status_code == 200
    assert len(page.json()["notifications"]) == 2
    assert page.json()["pages"] == 2
    assert page.json()["has_next"] is True

    too_large = await client.get(
        "/v1/notifications", params={"page_size": 101}, headers=auth_headers
    )
    assert too_large.status_code in {400, 422}


@pytest.mark.asyncio
async def test_notifications_cannot_read_another_users_notification(
    client, auth_headers, other_user, db_session
):
    notification = await create_notification(
        db_session,
        user_id=other_user.id,
        event_type="analysis.completed",
        title="Чужой анализ",
        body="Не показывать",
        deep_link="skatelab://session/secret",
        payload={"session_id": "secret"},
    )

    response = await client.post(f"/v1/notifications/{notification.id}/read", headers=auth_headers)

    assert response.status_code == 404
    assert (await client.get("/v1/notifications", headers=auth_headers)).json()["total"] == 0


@pytest.mark.asyncio
async def test_notifications_route_is_registered(client, auth_headers):
    response = await client.get("/v1/notifications", headers=auth_headers)
    assert response.status_code == 200
