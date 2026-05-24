"""Tests for S3 client pooling."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_get_s3_client_per_thread():
    """get_s3_client() must return per-thread boto3 client."""
    from app.storage import _thread_local, get_s3_client

    with patch("app.storage.get_settings") as mock_get:
        settings = MagicMock()
        settings.s3.endpoint_url = "https://s3.example.com"
        settings.s3.access_key_id.get_secret_value.return_value = "key"
        settings.s3.secret_access_key.get_secret_value.return_value = "secret"
        mock_get.return_value = settings

        # Clear any cached client
        if hasattr(_thread_local, "s3_client"):
            del _thread_local.s3_client

        client1 = get_s3_client()
        assert client1 is not None

        # Same thread = same client
        client2 = get_s3_client()
        assert client2 is client1


def test_get_s3_client_different_threads():
    """get_s3_client() must return different clients in different threads."""
    from app.storage import _thread_local, get_s3_client

    with patch("app.storage.get_settings") as mock_get:
        settings = MagicMock()
        settings.s3.endpoint_url = "https://s3.example.com"
        settings.s3.access_key_id.get_secret_value.return_value = "key"
        settings.s3.secret_access_key.get_secret_value.return_value = "secret"
        mock_get.return_value = settings

        results = {}

        def get_in_thread(name):
            if hasattr(_thread_local, "s3_client"):
                del _thread_local.s3_client
            results[name] = get_s3_client()

        t1 = threading.Thread(target=get_in_thread, args=("t1",))
        t2 = threading.Thread(target=get_in_thread, args=("t2",))
        t1.start()
        t1.join()
        t2.start()
        t2.join()

        # Different threads should get different client instances
        assert results["t1"] is not results["t2"]


@pytest.mark.asyncio
async def test_close_s3_clients_cleans_up():
    """close_s3_clients() must close both async and sync clients."""
    import app.storage as _st

    mock_async = AsyncMock()
    mock_async.__aexit__ = AsyncMock()
    _st._async_client_instance = mock_async

    mock_sync = MagicMock()
    _st._thread_local.s3_client = mock_sync

    await _st.close_s3_clients()

    mock_async.__aexit__.assert_awaited_once()
    assert _st._async_client_instance is None
    assert _st._thread_local.s3_client is None
