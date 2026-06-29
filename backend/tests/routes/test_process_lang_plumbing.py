"""T055 / #417 — `lang` plumbing HTTP→worker.

`POST /process/queue` (routes/process.py) must forward the caller's
``user.language`` into the enqueued ``process_video_task`` kwargs as
``lang``. Issue #417: fix #415 added a ``lang`` param to
``recommender.recommend_with_goe`` (English GOE-summary branch) and
``generate_training_plan`` (picks ``label_en``/``description_en``), but
NO caller wires ``lang`` from the HTTP request — every call defaults to
``"ru"`` so en-US users get Russian recommendations + training plans.

This test covers the enqueue side (route → arq kwargs). The worker →
Vast.ai → gpu_server plumbing is verified by grep (payload +
``ProcessRequest.lang`` + ``recommend_with_goe(..., lang=req.lang)``).

Mirrors the mock pattern from ``test_process_enqueue_session_idor_repro.py``:
mock ``create_task_state`` + ``arq_pool.enqueue_job`` (no real Valkey /
worker run). RED before site 1+2 (``lang`` absent from kwargs), GREEN
after.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from app.auth.security import create_access_token, hash_password
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def en_user(db_session: AsyncSession) -> User:
    user = User(
        email="en-user@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
        language="en",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def ru_user(db_session: AsyncSession) -> User:
    user = User(
        email="ru-user@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
        language="ru",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def en_headers(en_user: User):
    token = create_access_token(user_id=en_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ru_headers(ru_user: User):
    token = create_access_token(user_id=ru_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_process_enqueue_forwards_user_language_en(client, en_headers, en_user: User):
    """POST /process/queue enqueues with lang=user.language ("en")."""
    with patch("app.routes.process.create_task_state", new_callable=AsyncMock):
        response = await client.post(
            "/v1/process/queue",
            json={
                "video_key": "uploads/en/video.mp4",
                "person_click": {"x": 100, "y": 200},
            },
            headers=en_headers,
        )

    assert response.status_code == 200, f"Body: {response.text}"

    enqueue_call = client.app.state.arq_pool.enqueue_job.call_args
    assert enqueue_call is not None, "enqueue_job was not called"
    assert enqueue_call.kwargs.get("lang") == "en", (
        f"BUG (#417): enqueue_job kwargs do not carry the caller's language. "
        f"Expected lang='en' (user.language={en_user.language!r}), got "
        f"lang={enqueue_call.kwargs.get('lang')!r}. The worker → Vast.ai → "
        f"gpu_server recommender call would default to 'ru' — en-US users "
        f"receive Russian GOE summaries."
    )


@pytest.mark.asyncio
async def test_process_enqueue_forwards_default_language_ru(client, ru_headers, ru_user: User):
    """POST /process/queue enqueues with lang='ru' for default users."""
    with patch("app.routes.process.create_task_state", new_callable=AsyncMock):
        response = await client.post(
            "/v1/process/queue",
            json={
                "video_key": "uploads/ru/video.mp4",
                "person_click": {"x": 50, "y": 50},
            },
            headers=ru_headers,
        )

    assert response.status_code == 200, f"Body: {response.text}"

    enqueue_call = client.app.state.arq_pool.enqueue_job.call_args
    assert enqueue_call is not None, "enqueue_job was not called"
    assert enqueue_call.kwargs.get("lang") == "ru", (
        f"BUG (#417): default-language user should enqueue lang='ru' "
        f"(backward compat), got lang={enqueue_call.kwargs.get('lang')!r}."
    )
