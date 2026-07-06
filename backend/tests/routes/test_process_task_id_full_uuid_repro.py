"""#698 repro: process task_id must use full uuid4 hex, not 12-char truncation.

RED contract (before fix): `f"proc_{uuid.uuid4().hex[:12]}"` used only 12 hex
chars (48 bits). Birthday paradox: at ~10M tasks, collision probability ≈16%,
clobbering two tasks' Valkey state — one user's cancel signal could kill
another's task. GREEN contract (after fix): full `uuid.uuid4().hex` (128 bits).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _src() -> str:
    if "app.routes.process" not in sys.modules:
        importlib.import_module("app.routes.process")
    return Path(sys.modules["app.routes.process"].__file__).read_text()


def _body() -> str:
    src = _src()
    start = src.index("async def enqueue_process")
    end = src.index("\n    @", start + 1)
    return src[start:end]


def test_no_hex_truncation_in_task_id() -> None:
    """task_id does not slice the uuid hex down to 12 chars."""
    code_lines = [ln for ln in _body().splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    assert "hex[:12]" not in code, (
        "12-char truncation still present — 48-bit task_id collides at ~10M tasks"
    )
    assert "uuid.uuid4().hex" in code, "full uuid4 hex not used for task_id"


def test_truncation_comment_documents_why() -> None:
    """A comment records why the truncation was removed (defense against revert)."""
    src = _src()
    assert "#698" in src, "#698 rationale comment missing"
