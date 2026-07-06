"""#701 repro: cancel_queued_process must check terminal state before signalling.

RED contract (before fix): `set_cancel_signal` ran unconditionally — a cancel
hitting an already-completed/failed/cancelled task was a no-op but the route
returned `{"status": "cancel_requested"}`, misleading the client and the audit
trail. GREEN contract (after fix): `get_task_state` is fetched first; if the
status is already terminal, the route returns `{"status": "already_terminal"}`
without setting the signal.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _mod():
    # `app.routes.__init__` rebinds `process = Router(...)`, shadowing the
    # submodule attribute. The real module lives in sys.modules.
    if "app.routes.process" not in sys.modules:
        importlib.import_module("app.routes.process")
    return sys.modules["app.routes.process"]


def _src() -> str:
    return Path(_mod().__file__).read_text()


def _body() -> str:
    src = _src()
    start = src.index("async def cancel_queued_process")
    # end at the next method def
    end = src.index("\n    @", start + 1)
    return src[start:end]


def test_get_task_state_called_before_set_cancel_signal() -> None:
    """Source fetches state and checks terminal status before signalling."""
    body = _body()
    assert "get_task_state" in body, "get_task_state call missing (no status check)"
    assert "already_terminal" in body, (
        "terminal-state short-circuit missing — cancel still always signals"
    )
    # ordering: get_task_state must come before set_cancel_signal
    gs_idx = body.index("get_task_state")
    sig_idx = body.index("set_cancel_signal")
    assert gs_idx < sig_idx, "status check must run before setting the cancel signal"


def test_terminal_statuses_covered() -> None:
    """All three terminal TaskStatus values are checked."""
    body = _body()
    for terminal in ("TaskStatus.COMPLETED", "TaskStatus.FAILED", "TaskStatus.CANCELLED"):
        assert terminal in body, f"{terminal} missing from terminal-state check"
