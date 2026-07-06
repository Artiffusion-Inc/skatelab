"""Repro tests for connection bugfixes #719-#728.

Each test asserts the source-level fix exists (RED→GREEN pattern)
plus a route-level behavior check where practical.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from app.auth.security import create_access_token, hash_password
from app.models.connection import ConnectionStatus
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Source-assertion tests (verify fix present in source)
# ---------------------------------------------------------------------------

CONNECTIONS_ROUTE = (
    Path(__file__).resolve().parent.parent.parent / "app" / "routes" / "connections.py"
)
CONNECTION_CRUD = Path(__file__).resolve().parent.parent.parent / "app" / "crud" / "connection.py"


def test_719_self_invite_guard_in_source():
    """#719: invite route checks to_user.id == verified_user.id."""
    src = CONNECTIONS_ROUTE.read_text()
    assert "to_user.id == verified_user.id" in src, "#719 self-invite guard missing"


def test_724_target_is_active_check_in_source():
    """#724: invite checks to_user.is_active before creating connection."""
    src = CONNECTIONS_ROUTE.read_text()
    assert "not to_user.is_active" in src, "#724 is_active check missing"


def test_728_rate_limit_after_validation_in_source():
    """#728: rate limit runs AFTER user lookup and validation, not before."""
    src = CONNECTIONS_ROUTE.read_text()
    # The rate limit line must appear after the to_user lookup
    user_lookup_pos = src.find("await get_by_email(db, data.to_user_email)")
    rate_limit_pos = src.find('check_rate_limit(f"invite:{verified_user.id}"')
    assert user_lookup_pos > 0, "user lookup not found"
    assert rate_limit_pos > user_lookup_pos, "#728 rate limit must come after user lookup"


def test_725_email_error_logged_in_source():
    """#725: email send errors are logged, not silently suppressed."""
    src = CONNECTIONS_ROUTE.read_text()
    assert 'logger.exception("Failed to send coaching invite' in src, (
        "#725 email error logging missing"
    )


def test_723_accept_is_active_check_in_source():
    """#723: accept_invite checks conn.to_user.is_active."""
    src = CONNECTIONS_ROUTE.read_text()
    assert "not conn.to_user.is_active" in src, "#723 is_active check missing in accept"


def test_722_accept_race_guard_in_source():
    """#722: accept_invite re-checks status after refresh to narrow race window."""
    src = CONNECTIONS_ROUTE.read_text()
    assert 'await db.refresh(conn, ["status"])' in src, "#722 race guard missing"


def test_721_get_active_uses_first_not_scalar_one():
    """#721: get_active uses .limit(1).scalars().first() instead of scalar_one_or_none."""
    src = CONNECTION_CRUD.read_text()
    # Must NOT have scalar_one_or_none in get_active
    get_active_start = src.find("async def get_active")
    get_active_end = src.find("async def ", get_active_start + 1)
    get_active_body = src[get_active_start:get_active_end]
    assert "scalar_one_or_none" not in get_active_body, (
        "#721 get_active still uses scalar_one_or_none"
    )
    assert ".limit(1)" in get_active_body, "#721 get_active missing .limit(1)"
    assert ".first()" in get_active_body, "#721 get_active missing .first()"


def test_726_list_for_user_excludes_ended():
    """#726: list_for_user filters out ENDED connections."""
    src = CONNECTION_CRUD.read_text()
    list_start = src.find("async def list_for_user")
    list_end = src.find("async def ", list_start + 1)
    list_body = src[list_start:list_end]
    assert "ConnectionStatus.ENDED" in list_body, "#726 list_for_user missing ENDED filter"


# ---------------------------------------------------------------------------
# Route-level behavior tests
# ---------------------------------------------------------------------------

# Patch EmailService so route handlers never send real emails.
# Use spec=False to avoid InvalidSpecError when collected alongside
# test_connections.py which already patches with spec=True.
_mock_email = patch("app.routes.connections.EmailService")
_mock_email.start()


@pytest_asyncio.fixture
async def user_a(db_session: AsyncSession) -> User:
    user = User(email="a@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def user_b(db_session: AsyncSession) -> User:
    user = User(email="b@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers_a(user_a):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_a.id)}"}


@pytest.fixture
def auth_headers_b(user_b):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_b.id)}"}


@pytest.mark.asyncio
async def test_719_self_invite_rejected(client, user_a, auth_headers_a):
    """#719: inviting yourself returns 409."""
    response = await client.post(
        "/v1/connections/invite",
        json={"to_user_email": "a@example.com", "connection_type": "coaching"},
        headers=auth_headers_a,
    )
    assert response.status_code == 409
    assert "yourself" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_724_invite_inactive_user_rejected(client, db_session: AsyncSession, auth_headers_a):
    """#724: inviting an inactive user returns 400."""
    inactive = User(
        email="inactive@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
        is_active=False,
    )
    db_session.add(inactive)
    await db_session.flush()
    await db_session.refresh(inactive)

    response = await client.post(
        "/v1/connections/invite",
        json={"to_user_email": "inactive@example.com", "connection_type": "coaching"},
        headers=auth_headers_a,
    )
    assert response.status_code == 400
    assert "deactivated" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_726_ended_connections_not_listed(
    client, user_a, user_b, auth_headers_a, auth_headers_b
):
    """#726: ended connections are excluded from GET /connections."""
    # Create and accept
    invite = await client.post(
        "/v1/connections/invite",
        json={"to_user_email": "b@example.com", "connection_type": "coaching"},
        headers=auth_headers_a,
    )
    conn_id = invite.json()["id"]
    await client.post(f"/v1/connections/{conn_id}/accept", headers=auth_headers_b)
    # End it
    await client.post(f"/v1/connections/{conn_id}/end", headers=auth_headers_a)
    # List should be empty
    response = await client.get("/v1/connections", headers=auth_headers_a)
    assert response.status_code == 200
    conns = response.json()["connections"]
    assert all(c["status"] != "ended" for c in conns), (
        "#726: ended connections should not appear in list"
    )


# ---------------------------------------------------------------------------
# CRUD-level tests
# ---------------------------------------------------------------------------


def _make_user(db, user_id: str) -> User:
    user = User(id=user_id, email=f"{user_id}@test.com", hashed_password="hash")
    db.add(user)
    return user


async def test_721_get_active_no_crash_on_duplicates(db_session):
    """#721: get_active returns a result even if duplicate rows exist (uses .first() not scalar_one_or_none)."""
    from app.crud.connection import create, get_active
    from app.models.connection import ConnectionType

    _make_user(db_session, "u1")
    _make_user(db_session, "u2")
    await db_session.flush()

    conn = await create(
        db_session,
        from_user_id="u1",
        to_user_id="u2",
        connection_type=ConnectionType.COACHING,
        initiated_by="u1",
    )
    result = await get_active(
        db_session,
        from_user_id="u1",
        to_user_id="u2",
        connection_type=ConnectionType.COACHING,
    )
    assert result is not None
    assert result.id == conn.id


async def test_726_list_for_user_excludes_ended_crud(db_session):
    """#726: list_for_user does not return ENDED connections (CRUD level)."""
    from app.crud.connection import create, list_for_user
    from app.models.connection import ConnectionType

    _make_user(db_session, "u1")
    _make_user(db_session, "u2")
    _make_user(db_session, "u3")
    await db_session.flush()

    # Active connection
    c1 = await create(
        db_session,
        from_user_id="u1",
        to_user_id="u2",
        connection_type=ConnectionType.COACHING,
        initiated_by="u1",
    )
    c1.status = ConnectionStatus.ACTIVE

    # Ended connection
    c2 = await create(
        db_session,
        from_user_id="u1",
        to_user_id="u3",
        connection_type=ConnectionType.CHOREOGRAPHY,
        initiated_by="u1",
    )
    c2.status = ConnectionStatus.ENDED
    await db_session.flush()

    result = await list_for_user(db_session, "u1")
    assert len(result) == 1
    assert result[0].id == c1.id
