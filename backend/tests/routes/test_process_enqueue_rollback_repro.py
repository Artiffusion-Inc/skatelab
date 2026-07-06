"""#700 repro: enqueue_process must roll back task state when enqueue_job fails.

RED contract (before fix): `create_task_state` (line 58) ran BEFORE
`enqueue_job` (line 69); if `enqueue_job` raised (Valkey full, queue missing,
serialization error), the task_state hash stayed "pending" in Valkey for the
TTL — orphaned forever. GREEN contract (after fix): `enqueue_job` is wrapped in
try/except and `delete_task_state(task_id)` runs on failure before re-raising.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _mod():
    if "app.routes.process" not in sys.modules:
        importlib.import_module("app.routes.process")
    return sys.modules["app.routes.process"]


def _src() -> str:
    return Path(_mod().__file__).read_text()


def _body() -> str:
    src = _src()
    start = src.index("async def enqueue_process")
    end = src.index("\n    @", start + 1)
    return src[start:end]


def test_enqueue_job_wrapped_in_try_except() -> None:
    """enqueue_job is inside a try/except so failures trigger rollback."""
    body = _body()
    # the actual call is `await ...enqueue_job(` — ignore mentions in comments
    ej_idx = body.index("enqueue_job(")
    assert ej_idx > 0, "enqueue_job call missing"
    # the try block must open before the actual call
    try_idx = body.index("try:")
    assert try_idx < ej_idx, "enqueue_job must be inside try block"


def test_delete_task_state_called_on_failure() -> None:
    """delete_task_state runs in the except branch on enqueue failure."""
    body = _body()
    assert "delete_task_state" in body, (
        "rollback missing — create_task_state orphan stays pending on enqueue failure"
    )
    # delete_task_state must be after the actual enqueue_job call, in except
    ej_idx = body.index("enqueue_job(")
    del_idx = body.index("delete_task_state")
    assert del_idx > ej_idx, "delete_task_state must run after enqueue_job (in except)"


def test_task_manager_exposes_delete_task_state() -> None:
    """task_manager has the delete_task_state helper used for rollback."""
    import app.task_manager as tm

    assert hasattr(tm, "delete_task_state"), "delete_task_state helper missing from task_manager"
