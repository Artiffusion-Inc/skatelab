"""#680 repro: delete_sessions_bulk must be all-or-nothing on ownership.

RED contract (before fix): the bulk delete loop soft-deletes each owned
session in turn and raises 403 on the FIRST non-owned id. Sessions processed
before the failure are already soft-deleted → partial state. Caller sees 403
but some of their sessions are gone with no indication. GREEN contract (after
fix): ownership of ALL ids is pre-checked; if any id is non-owned, NO delete
runs and the 403 lists the offending ids.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from app.auth.security import hash_password
from app.crud.session import create as crud_create
from app.crud.session import get_by_id
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


@pytest.mark.asyncio
async def test_bulk_delete_atomic_on_foreign_id(
    client, auth_headers, authed_user, other_user, db_session: AsyncSession
) -> None:
    """Bulk delete with a foreign id in the middle: 403, no owned session deleted."""
    with (
        patch(
            "app.routes.sessions.get_object_url_async",
            new_callable=AsyncMock,
            return_value="https://fake.url",
        ),
    ):
        s1 = await crud_create(db_session, user_id=authed_user.id, element_type="axel")
        s2 = await crud_create(db_session, user_id=authed_user.id, element_type="lutz")
        foreign = await crud_create(db_session, user_id=other_user.id, element_type="flip")

    ids_param = f"{s1.id},{foreign.id},{s2.id}"
    response = await client.delete(f"/v1/sessions/bulk?ids={ids_param}", headers=auth_headers)

    assert response.status_code == 403, response.text

    # #680: no owned session must be soft-deleted when a foreign id is present
    await db_session.refresh(s1)
    await db_session.refresh(s2)
    await db_session.refresh(foreign)
    assert s1.status != "deleted", "partial delete: s1 deleted before 403 raised"
    assert s2.status != "deleted", "partial delete: s2 deleted before 403 raised"
    assert foreign.status != "deleted"


@pytest.mark.asyncio
async def test_bulk_delete_all_owned_succeeds(
    client, auth_headers, authed_user, db_session: AsyncSession
) -> None:
    """Bulk delete of all-owned ids: 204, all soft-deleted."""
    with (
        patch(
            "app.routes.sessions.get_object_url_async",
            new_callable=AsyncMock,
            return_value="https://fake.url",
        ),
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


@pytest.mark.asyncio
async def test_bulk_delete_skips_unknown_ids_atomically(
    client, auth_headers, authed_user, db_session: AsyncSession
) -> None:
    """Unknown ids are skipped (not 404); owned ids in the same batch are deleted."""
    with (
        patch(
            "app.routes.sessions.get_object_url_async",
            new_callable=AsyncMock,
            return_value="https://fake.url",
        ),
    ):
        s1 = await crud_create(db_session, user_id=authed_user.id, element_type="axel")

    ids_param = f"{s1.id},nonexistent-id"
    response = await client.delete(f"/v1/sessions/bulk?ids={ids_param}", headers=auth_headers)

    assert response.status_code == 204, response.text
    await db_session.refresh(s1)
    assert s1.status == "deleted"
    # confirm the unknown id is genuinely absent
    assert await get_by_id(db_session, "nonexistent-id") is None
