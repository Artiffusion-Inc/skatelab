"""Tests for DB session DI behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_provide_db_rollback_on_any_exception():
    """provide_db() must rollback on any Exception."""
    from app.di import provide_db

    mock_session = AsyncMock()
    mock_session.rollback = AsyncMock()

    with patch("app.di.async_session_factory") as mock_factory:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        gen = provide_db()
        session = await gen.__anext__()
        assert session is mock_session

        with pytest.raises(IntegrityError):
            await gen.athrow(IntegrityError("stmt", "params", Exception("orig")))

        mock_session.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_provide_db_auto_commit_on_success():
    """provide_db() must auto-commit on success."""
    from app.di import provide_db

    mock_session = AsyncMock()

    with patch("app.di.async_session_factory") as mock_factory:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        gen = provide_db()
        session = await gen.__anext__()
        assert session is mock_session

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        mock_session.commit.assert_awaited_once()


def test_no_dbsessionproxy_in_di():
    """DbSessionProxy must not exist in di module."""
    import app.di as di_mod

    assert not hasattr(di_mod, "DbSessionProxy"), "DbSessionProxy should be removed"
    assert not hasattr(di_mod, "db_proxy"), "db_proxy should be removed"
    assert not hasattr(di_mod, "db_session_proxy"), "db_session_proxy should be removed"
