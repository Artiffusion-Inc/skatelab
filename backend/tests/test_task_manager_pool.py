"""Tests for Valkey connection pool lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_valkey_raises_before_init():
    import app.task_manager as _tm
    from app.task_manager import get_valkey

    orig_pool = _tm._pool
    orig_test = _tm._test_pool
    _tm._pool = None
    _tm._test_pool = None
    try:
        with pytest.raises(RuntimeError, match="Call init_valkey_pool"):
            get_valkey()
    finally:
        _tm._pool = orig_pool
        _tm._test_pool = orig_test


@pytest.mark.asyncio
async def test_set_test_pool_overrides():
    from app.task_manager import _set_test_pool, get_valkey

    mock = MagicMock()
    _set_test_pool(mock)
    try:
        assert get_valkey() is mock
    finally:
        _set_test_pool(None)


@pytest.mark.asyncio
async def test_init_valkey_pool_validates_ping():
    import app.task_manager as _tm

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=OSError("Connection refused"))
    mock_redis.aclose = AsyncMock()

    with patch("app.task_manager._create_redis", return_value=mock_redis):
        with pytest.raises(OSError, match="Connection refused"):
            await _tm.init_valkey_pool()
    mock_redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_valkey_pool_resets():
    import app.task_manager as _tm

    mock_redis = AsyncMock()
    mock_redis.aclose = AsyncMock()

    _tm._pool = mock_redis
    await _tm.close_valkey_pool()
    mock_redis.aclose.assert_awaited_once()
    assert _tm._pool is None
