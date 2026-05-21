"""Tests for Litestar auth dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from app.auth.deps import get_current_user, retrieve_user_handler
from app.auth.security import hash_password
from app.models.user import User
from litestar.exceptions import NotAuthorizedException

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_retrieve_user_handler_valid(db_session: AsyncSession):
    """Test retrieve_user_handler returns user for valid token."""
    user = User(email="test@example.com", hashed_password=hash_password("pass"))
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    token = {"sub": user.id, "type": "access"}
    connection = MagicMock()
    connection.app.state.test_db_session = db_session

    result = await retrieve_user_handler(token, connection)
    assert result is not None
    assert result.id == user.id


@pytest.mark.asyncio
async def test_retrieve_user_handler_no_sub(db_session: AsyncSession):
    """Test retrieve_user_handler returns None when token has no sub."""
    token = {"type": "access"}
    connection = MagicMock()
    connection.app.state.test_db_session = db_session

    result = await retrieve_user_handler(token, connection)
    assert result is None


@pytest.mark.asyncio
async def test_retrieve_user_handler_nonexistent_user(db_session: AsyncSession):
    """Test retrieve_user_handler returns None for nonexistent user."""
    token = {"sub": "nonexistent-id", "type": "access"}
    connection = MagicMock()
    connection.app.state.test_db_session = db_session

    result = await retrieve_user_handler(token, connection)
    assert result is None


@pytest.mark.asyncio
async def test_retrieve_user_handler_inactive_user(db_session: AsyncSession):
    """Test retrieve_user_handler returns None for inactive user."""
    user = User(email="inactive@example.com", hashed_password="hash", is_active=False)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    token = {"sub": user.id, "type": "access"}
    connection = MagicMock()
    connection.app.state.test_db_session = db_session

    result = await retrieve_user_handler(token, connection)
    assert result is None


@pytest.mark.asyncio
async def test_get_current_user_skip_auth_mode(db_session: AsyncSession):
    """Test get_current_user returns first active user when skip_auth is enabled."""
    user = User(id="dev-user", email="dev@example.com", hashed_password="hash", is_active=True)
    db_session.add(user)
    await db_session.flush()

    with patch("app.auth.deps.get_settings") as mock_get:
        mock_settings = MagicMock()
        mock_settings.app.skip_auth = True
        mock_get.return_value = mock_settings
        request = MagicMock()
        result = await get_current_user(request=request, db=db_session)
    assert result.id == "dev-user"


@pytest.mark.asyncio
async def test_get_current_user_skip_auth_no_active_users(db_session: AsyncSession):
    """Test get_current_user raises 500 when skip_auth enabled but no active users exist."""
    with patch("app.auth.deps.get_settings") as mock_get:
        mock_settings = MagicMock()
        mock_settings.app.skip_auth = True
        mock_get.return_value = mock_settings
        request = MagicMock()
        with pytest.raises(NotAuthorizedException, match="No active users"):
            await get_current_user(request=request, db=db_session)


@pytest.mark.asyncio
async def test_get_current_user_normal_mode_no_user(db_session: AsyncSession):
    """Test get_current_user raises 401 when not skip_auth and request.user is None."""
    with patch("app.auth.deps.get_settings") as mock_get:
        mock_settings = MagicMock()
        mock_settings.app.skip_auth = False
        mock_get.return_value = mock_settings
        request = MagicMock()
        request.user = None
        with pytest.raises(NotAuthorizedException, match="Could not validate"):
            await get_current_user(request=request, db=db_session)


@pytest.mark.asyncio
async def test_get_current_user_normal_mode_inactive_user(db_session: AsyncSession):
    """Test get_current_user raises 401 when request.user is inactive."""
    user = User(email="inactive@example.com", hashed_password="hash", is_active=False)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    with patch("app.auth.deps.get_settings") as mock_get:
        mock_settings = MagicMock()
        mock_settings.app.skip_auth = False
        mock_get.return_value = mock_settings
        request = MagicMock()
        request.user = user
        with pytest.raises(NotAuthorizedException, match="Could not validate"):
            await get_current_user(request=request, db=db_session)
