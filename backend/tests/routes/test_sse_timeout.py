"""Tests for SSE timeout in process routes."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SSE_STREAM_TIMEOUT = 60  # seconds


def _parse_sse(event_bytes: bytes) -> dict:
    """Parse a single SSE chunk from Litestar's iterator into a dict.

    Litestar returns raw SSE wire format: b'data: {"key": "value"}\n\n'
    """
    text = event_bytes.decode()
    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            return json.loads(line[6:])
    return {}


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.valkey.host = "localhost"
    settings.valkey.port = 6379
    settings.valkey.db = 0
    settings.valkey.password = MagicMock(get_secret_value=MagicMock(return_value=""))
    return settings


@pytest.mark.asyncio
async def test_sse_stream_exists():
    """stream_process_status should be a callable on the process controller."""
    from app.routes.process import ProcessController

    assert callable(ProcessController.stream_process_status)


@pytest.mark.asyncio
async def test_sse_stream_times_out_after_no_messages(mock_settings):
    """SSE stream should timeout after 60s of no messages, then yield final state with _timeout flag."""
    with (
        patch("app.routes.process.get_valkey", new_callable=MagicMock) as mock_valkey_fn,
        patch("app.routes.process.get_task_state", new_callable=AsyncMock) as mock_state,
        patch("app.routes.process.SSE_STREAM_TIMEOUT", 0.01),  # 10ms for fast test
    ):
        mock_valkey = MagicMock()
        mock_pubsub = MagicMock()

        # Block longer than the patched timeout so the timeout path is exercised.
        async def get_message_hang(*_args, **_kwargs):
            await asyncio.sleep(10)

        mock_pubsub.get_message = get_message_hang
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()
        mock_valkey.pubsub.return_value = mock_pubsub
        mock_valkey_fn.return_value = mock_valkey

        mock_state.return_value = {"status": "running", "progress": 0.5, "user_id": "test-user-id"}

        from app.routes.process import ProcessController

        mock_user = MagicMock(id="test-user-id")

        # stream_process_status is async, returns ServerSentEvent
        request = MagicMock(is_connected=True)
        response = await ProcessController.stream_process_status.fn(
            MagicMock(), request=request, user=mock_user, task_id="proc_test123"
        )

        # ServerSentEvent.iterator yields raw SSE wire-format bytes
        events = []
        async for event in response.iterator:
            events.append(event)

        # Should have at least the timeout event with _timeout flag
        assert len(events) >= 1
        timeout_data = _parse_sse(events[-1])
        assert timeout_data.get("_timeout") is True


@pytest.mark.asyncio
async def test_sse_stream_yields_progress_events(mock_settings):
    """SSE stream should yield progress updates from pubsub."""
    with (
        patch("app.routes.process.get_valkey", new_callable=MagicMock) as mock_valkey_fn,
        patch("app.routes.process.get_task_state", new_callable=AsyncMock) as mock_state,
    ):
        mock_valkey = MagicMock()
        mock_pubsub = MagicMock()

        # Simulate one progress message then a completed message.
        mock_pubsub.get_message = AsyncMock(
            side_effect=[
                {"type": "message", "data": b'{"status": "running", "progress": 0.5}'},
                {"type": "message", "data": b'{"status": "completed"}'},
            ]
        )
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()
        mock_valkey.pubsub.return_value = mock_pubsub
        mock_valkey_fn.return_value = mock_valkey

        mock_state.return_value = {"status": "running", "progress": 0.0, "user_id": "test-user-id"}

        from app.routes.process import ProcessController

        mock_user = MagicMock(id="test-user-id")

        request = MagicMock(is_connected=True)
        response = await ProcessController.stream_process_status.fn(
            MagicMock(), request=request, user=mock_user, task_id="proc_test456"
        )

        events = []
        async for event in response.iterator:
            events.append(event)

        # Should have initial state + progress + completed events
        assert len(events) >= 3
        # Initial state event
        initial_data = _parse_sse(events[0])
        assert initial_data["status"] == "running"
        # Last event should be completed
        last_data = _parse_sse(events[-1])
        assert last_data["status"] == "completed"
