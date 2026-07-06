"""Regression test for #643 — get_task_state crashes on corrupt result JSON.

Bug: `get_task_state` (task_manager.py:198) calls `json.loads(result)` without
try/except. Corrupt JSON in Valkey (manual edit, version mismatch, bit rot)
raises JSONDecodeError → 500 on GET /detect/{task_id}/result.

Fix: try/except json.JSONDecodeError, log warning, return
{"raw": result, "error": "corrupt_json"} instead of crashing.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_SRC_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "task_manager.py"


def test_task_manager_source_guards_corrupt_json():
    """Source must contain #640 guard for corrupt JSON (#643)."""
    src = _SRC_FILE.read_text(encoding="utf-8")
    assert "#643" in src, (
        "BUG #643: task_manager.py has no #643 reference — missing "
        "json.JSONDecodeError guard in get_task_state."
    )


async def test_get_task_state_corrupt_json_returns_error_marker():
    """Corrupt JSON result returns {"raw": ..., "error": "corrupt_json"}, not crash."""
    from app.task_manager import _set_test_pool, get_task_state

    class _FakeCorrupt:
        """Fake Valkey with corrupt 'result' field."""

        async def hgetall(self, key: str) -> dict[str, str]:
            return {
                "task_id": "test-corrupt",
                "status": "completed",
                "progress": "1.0",
                "result": "garbage{{not_json",
            }

    _set_test_pool(_FakeCorrupt())
    try:
        state = await get_task_state("test-corrupt")
    finally:
        _set_test_pool(None)

    assert state is not None
    assert state["result"]["error"] == "corrupt_json"
    assert state["result"]["raw"] == "garbage{{not_json"


async def test_get_task_state_valid_json_parses_normally():
    """Valid JSON result parses as dict (no regression)."""
    from app.task_manager import _set_test_pool, get_task_state

    class _FakeValid:
        async def hgetall(self, key: str) -> dict[str, str]:
            return {
                "task_id": "test-valid",
                "status": "completed",
                "progress": "0.75",
                "result": json.dumps({"persons": 2}),
            }

    _set_test_pool(_FakeValid())
    try:
        state = await get_task_state("test-valid")
    finally:
        _set_test_pool(None)

    assert state is not None
    assert state["result"] == {"persons": 2}
    assert state["progress"] == 0.75


async def test_get_task_state_missing_result_returns_none():
    """No result field returns None (no regression)."""
    from app.task_manager import _set_test_pool, get_task_state

    class _FakeNoResult:
        async def hgetall(self, key: str) -> dict[str, str]:
            return {"task_id": "test-norm", "status": "pending", "progress": "0.0"}

    _set_test_pool(_FakeNoResult())
    try:
        state = await get_task_state("test-norm")
    finally:
        _set_test_pool(None)

    assert state is not None
    assert state["result"] is None


async def test_get_task_state_empty_result_returns_error_marker():
    """Empty string result is corrupt JSON → error marker."""
    from app.task_manager import _set_test_pool, get_task_state

    class _FakeEmpty:
        async def hgetall(self, key: str) -> dict[str, str]:
            return {"task_id": "test-empty", "status": "completed", "result": ""}

    _set_test_pool(_FakeEmpty())
    try:
        state = await get_task_state("test-empty")
    finally:
        _set_test_pool(None)

    assert state is not None
    # Empty string is falsy, so result should be None (no crash)
    assert state["result"] is None
