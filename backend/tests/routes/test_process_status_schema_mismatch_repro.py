"""#697 repro: get_process_status must not crash on schema mismatch / missing keys.

RED contract (before fix):
- `result = ProcessResponse(**state["result"])` — bare unpack, no try/except.
  Schema mismatch (worker version drift, corrupt JSON) → pydantic ValidationError → 500.
- `progress=state["progress"]` — KeyError if `progress` key missing (legacy task,
  partial write). Should use `state.get("progress", 0)`.

GREEN contract (after fix): `progress` uses `.get(..., 0)` and `ProcessResponse(**...)`
is wrapped in try/except returning raw dict on failure.
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
    start = src.index("async def get_process_status")
    # next route decorator after get_process_status
    end = src.index("\n    @", start + 1)
    return src[start:end]


def test_progress_uses_get_with_default() -> None:
    """progress is read with .get(..., 0), not state["progress"] (KeyError on legacy)."""
    code_lines = [ln for ln in _body().splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    assert 'state["progress"]' not in code, (
        "state['progress'] raises KeyError on legacy/partial-write task state"
    )
    assert "progress" in code and ".get(" in code, "progress must use .get(..., 0)"


def test_result_unpack_wrapped_in_try_except() -> None:
    """ProcessResponse(**state['result']) is wrapped in try/except — schema mismatch returns raw dict, not 500."""
    body = _body()
    # the actual unpack call — ignore mentions in comments
    pr_idx = body.index("ProcessResponse(")
    assert pr_idx > 0, "ProcessResponse unpack missing"
    try_idx = body.index("try:")
    assert try_idx < pr_idx, "ProcessResponse(**...) must be inside try block"
    assert "except" in body[pr_idx:], "except branch missing after ProcessResponse unpack"


def test_status_uses_get_with_default() -> None:
    """status is read defensively too (state.get('status', ...)) — legacy task missing 'status' key."""
    code_lines = [ln for ln in _body().splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    assert 'state["status"]' not in code, (
        "state['status'] raises KeyError on legacy/partial-write task state"
    )
