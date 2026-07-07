"""#964 repro: delete_sessions_bulk DoS guard (max-length bound + batch delete).

RED contract (before fix):
- `ids` list has NO upper bound → a client sending 10 000 ids forces 20 000
  sequential DB round-trips (N+1: 1 SELECT + 1 UPDATE per id) in a single
  request. No rate limit on the route either (unlike `create_session`).
- Source: `backend/app/routes/sessions.py` `delete_sessions_bulk`.

GREEN contract (after fix):
- A `MAX_BULK_DELETE_IDS` constant caps the parsed ids list; >MAX → HTTP 422
  (rejected before any DB work).
- Deletion is a SINGLE batched UPDATE (`WHERE id IN (...)`), not a per-id
  `soft_delete` loop.
- Within-bound, all-owned requests still succeed (regression guard).
- Empty ids list is rejected (400).
"""

from __future__ import annotations

import importlib
import inspect
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from app.auth.security import hash_password
from app.crud.session import create as crud_create
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _sessions_module():
    """app.routes.sessions is shadowed by a Router instance in __init__.py,
    so `from app.routes import sessions` returns the Router, not the module.
    import_module resolves the actual submodule."""
    return importlib.import_module("app.routes.sessions")


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    user = User(email="other@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


def test_source_has_max_bulk_delete_ids_constant() -> None:
    """GREEN: a max-length cap constant exists in the routes module."""
    sessions_module = _sessions_module()
    assert hasattr(sessions_module, "MAX_BULK_DELETE_IDS"), (
        "MAX_BULK_DELETE_IDS constant missing — no DoS cap on ids list"
    )
    cap = sessions_module.MAX_BULK_DELETE_IDS
    assert isinstance(cap, int) and cap > 0, "MAX_BULK_DELETE_IDS must be a positive int"


def test_source_uses_batch_delete_not_per_id_loop() -> None:
    """GREEN: delete_sessions_bulk source must batch-delete, not loop `soft_delete`."""
    sessions_module = _sessions_module()
    src = inspect.getsource(sessions_module.SessionsController.delete_sessions_bulk.fn)
    # The per-id `await soft_delete(db, session)` loop must be gone; instead the
    # route delegates to soft_delete_many (a single batched UPDATE).
    assert "for session in sessions" not in src, (
        "per-session soft_delete loop still present — N+1 not eliminated"
    )
    assert "soft_delete_many" in src, (
        "bulk delete must delegate to soft_delete_many (batch UPDATE), not a per-id loop"
    )
    # And soft_delete_many in the CRUD layer must be a single batched UPDATE.
    from app.crud import session as crud_session

    crud_src = inspect.getsource(crud_session.soft_delete_many)
    assert ".in_(" in crud_src, (
        "soft_delete_many must use a single batched `WHERE id IN (...)` update"
    )


@pytest.mark.asyncio
async def test_bulk_delete_rejects_ids_above_cap(
    client, auth_headers, authed_user, db_session: AsyncSession
) -> None:
    """ids list exceeding MAX_BULK_DELETE_IDS → 422 (rejected, no DB work)."""
    cap = getattr(_sessions_module(), "MAX_BULK_DELETE_IDS", 0)
    assert cap > 0, "MAX_BULK_DELETE_IDS not defined — test cannot assert the bound"

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        # one real session so the request isn't all-unknown
        s1 = await crud_create(db_session, user_id=authed_user.id, element_type="axel")

    too_many = ",".join([s1.id, *(f"fake-{i}" for i in range(cap))])
    response = await client.delete(f"/v1/sessions/bulk?ids={too_many}", headers=auth_headers)

    assert response.status_code == 422, (
        f">MAX ids must be rejected with 422, got {response.status_code}: {response.text}"
    )
    await db_session.refresh(s1)
    assert s1.status != "deleted", "over-cap request must not delete anything"


@pytest.mark.asyncio
async def test_bulk_delete_rejects_empty_ids(
    client, auth_headers, authed_user, db_session: AsyncSession
) -> None:
    """Empty ids list → 400 (no-op rejected)."""
    response = await client.delete("/v1/sessions/bulk?ids=", headers=auth_headers)
    assert response.status_code in (400, 422), (
        f"empty ids must be rejected, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
async def test_bulk_delete_within_bound_all_owned_succeeds(
    client, auth_headers, authed_user, db_session: AsyncSession
) -> None:
    """Regression: a small all-owned list is batch-deleted (204)."""
    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        s1 = await crud_create(db_session, user_id=authed_user.id, element_type="axel")
        s2 = await crud_create(db_session, user_id=authed_user.id, element_type="lutz")
        s3 = await crud_create(db_session, user_id=authed_user.id, element_type="flip")

    ids_param = f"{s1.id},{s2.id},{s3.id}"
    response = await client.delete(f"/v1/sessions/bulk?ids={ids_param}", headers=auth_headers)

    assert response.status_code == 204, response.text
    for s in (s1, s2, s3):
        await db_session.refresh(s)
        assert s.status == "deleted"
