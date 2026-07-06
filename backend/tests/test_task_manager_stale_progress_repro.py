"""Repro tests — task_manager leaves stale progress/message on FAILED/CANCELLED (#841).

``store_error`` and ``mark_cancelled`` (app/task_manager.py) write a partial
Valkey hash mapping on terminal failure/cancel: they set ``status`` +
``completed_at`` (+ ``error`` / ``message``) but NOT ``progress``. So a task
that last ran ``update_progress(0.7, "Processing frame 120...")`` stays at
``progress=0.7`` after it FAILED — the route ``GET /process/{id}/status``
reads ``state["progress"]`` verbatim and the UI shows a FAILED task at 70%.
``mark_cancelled`` similarly leaves a stale mid-run progress.

``store_result`` (the success path) correctly writes ``progress=1.0,
message="Done"`` — the hole is specific to the failure/cancel path.

Fix (#841): add ``"progress": "0.0"`` to both mappings, and ``"message":
"Failed"`` to ``store_error`` (so the stale "Processing..." message is
overwritten). The success-path contract is unchanged.

Tests use an in-memory dict-backed fake Valkey (hset writes into a dict,
hgetall reads it back) so the round-trip through ``store_error`` →
``get_task_state`` is exercised end-to-end. RED without the fix (progress
stale at 0.7 / 0.42), GREEN with it (progress=0.0).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import app.task_manager as tm_module
import pytest
from app.task_manager import (
    TASK_KEY_PREFIX,
    TaskStatus,
    get_task_state,
    mark_cancelled,
    store_error,
    store_result,
    update_progress,
)


class _FakeValkey:
    """In-memory dict-backed Valkey for hset/hgetall round-trip tests."""

    def __init__(self) -> None:
        self.store: dict[str, dict[str, str]] = {}

    async def hset(self, key: str, *, mapping: dict[str, str]) -> int:
        bucket = self.store.setdefault(key, {})
        bucket.update(mapping)
        return len(mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.store.get(key, {}))

    async def expire(self, key: str, seconds: int) -> None:
        return None


@pytest.fixture(autouse=True)
def reset_pool():
    original_pool = tm_module._pool
    original_test_pool = tm_module._test_pool
    tm_module._pool = None
    tm_module._test_pool = None
    yield
    tm_module._pool = original_pool
    tm_module._test_pool = original_test_pool


@pytest.fixture
def fake_valkey():
    fake = _FakeValkey()
    tm_module._set_test_pool(fake)
    return fake


def _state(fake: _FakeValkey, task_id: str) -> dict[str, str]:
    return fake.store[f"{TASK_KEY_PREFIX}{task_id}"]


@pytest.mark.asyncio
async def test_store_error_resets_progress_after_midrun_update(fake_valkey):
    """#841: after update_progress(0.7) + store_error, progress must be 0.0,
    not the stale 0.7.
    """
    await update_progress("t1", 0.7, "Processing frame 120...")
    await store_error("t1", "GPU OOM")

    state = await get_task_state("t1")
    assert state is not None
    assert state["status"] == TaskStatus.FAILED
    # CONTRACT: a FAILED task shows 0% progress, not the stale mid-run 70%.
    assert state["progress"] == 0.0, (
        f"#841: FAILED task has stale progress={state['progress']!r} (expected "
        f"0.0) — store_error does not reset progress."
    )


@pytest.mark.asyncio
async def test_store_error_overwrites_stale_processing_message(fake_valkey):
    """#841: after a mid-run "Processing frame 120..." message + store_error,
    the message must NOT still be "Processing frame 120...".
    """
    await update_progress("t1", 0.7, "Processing frame 120...")
    await store_error("t1", "GPU OOM")

    state = await get_task_state("t1")
    assert state is not None
    assert state.get("message") != "Processing frame 120...", (
        f"#841: FAILED task still shows stale mid-run message "
        f"{state.get('message')!r} — store_error does not overwrite message."
    )
    assert state.get("error") == "GPU OOM"


@pytest.mark.asyncio
async def test_mark_cancelled_resets_progress_after_midrun_update(fake_valkey):
    """#841: after update_progress(0.42) + mark_cancelled, progress must be 0.0,
    not the stale 0.42.
    """
    await update_progress("t1", 0.42, "Working...")
    await mark_cancelled("t1")

    state = await get_task_state("t1")
    assert state is not None
    assert state["status"] == TaskStatus.CANCELLED
    assert state["progress"] == 0.0, (
        f"#841: CANCELLED task has stale progress={state['progress']!r} "
        f"(expected 0.0) — mark_cancelled does not reset progress."
    )


@pytest.mark.asyncio
async def test_store_result_resets_progress_and_message_contrast(fake_valkey):
    """Contrast: store_result already writes progress=1.0 + message='Done'.
    This pins the success-path contract the failure/cancel path must mirror
    (reset progress + message, just to 0.0 instead of 1.0).
    """
    await update_progress("t1", 0.7, "Processing frame 120...")
    await store_result("t1", {"ok": True})

    state = await get_task_state("t1")
    assert state is not None
    assert state["status"] == TaskStatus.COMPLETED
    assert state["progress"] == 1.0
    assert state["message"] == "Done"


def test_source_store_error_mapping_writes_progress_and_message():
    """#841: store_error mapping must include progress and message keys."""
    import inspect

    src = inspect.getsource(store_error)
    assert '"progress"' in src, "#841: store_error mapping must write progress=0.0"
    assert '"message"' in src, "#841: store_error mapping must overwrite stale message"


def test_source_mark_cancelled_mapping_writes_progress():
    """#841: mark_cancelled mapping must include progress key."""
    import inspect

    src = inspect.getsource(mark_cancelled)
    assert '"progress"' in src, "#841: mark_cancelled mapping must write progress=0.0"
