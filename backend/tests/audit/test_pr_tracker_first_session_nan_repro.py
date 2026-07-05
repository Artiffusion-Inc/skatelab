"""RED repro — pr_tracker.check_pr marks NaN as PR on first session.

backend/app/services/pr_tracker.py:19-20:
    if current_best is None:
        return True, None

First session has no history (`current_best is None`). The early-return
fires BEFORE any NaN check, so `float('nan')` is incorrectly classified
as a personal record. Result: `(True, None)` propagates to
`SessionMetric.is_pr = True` in DB and triggers the "Новый PR!"
diagnostic on a NaN value (check_new_pr at backend/app/services/diagnostics.py:117).

Sister issue: #630 (session_saver NaN deflates overall_score).
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PR_TRACKER_PATH = BACKEND_ROOT / "app" / "services" / "pr_tracker.py"


def _load_pr_tracker_source() -> str:
    return PR_TRACKER_PATH.read_text(encoding="utf-8")


def _load_module():
    spec = importlib.util.spec_from_file_location("_pr_tracker_under_test", PR_TRACKER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_source_has_nan_guard_before_none_check():
    """Source must check math.isfinite(new_value) before the None early-return.

    RED if guard is missing or placed after the `if current_best is None:` branch.
    """
    src = _load_pr_tracker_source()
    assert "math.isfinite" in src, (
        "pr_tracker.check_pr must guard against NaN/inf via math.isfinite "
        "before the current_best is None early-return (#629)."
    )
    # Match the executable lines (not comment text). The guard is
    # `if not math.isfinite(new_value):` and the branch is
    # `if current_best is None:`. Anchor on the trailing colon to skip any
    # text mention in comments / docstrings.
    import re

    guard = re.search(r"if\s+not\s+math\.isfinite\s*\(\s*new_value\s*\)\s*:", src)
    branch = re.search(r"if\s+current_best\s+is\s+None\s*:", src)
    assert guard is not None, "expected `if not math.isfinite(new_value):` line in pr_tracker"
    assert branch is not None, "expected `if current_best is None:` line in pr_tracker"
    assert guard.start() < branch.start(), (
        f"`if not math.isfinite(new_value):` must come BEFORE "
        f"`if current_best is None:`. guard_offset={guard.start()} "
        f"branch_offset={branch.start()}"
    )


def test_check_pr_first_session_nan_marked_as_pr():
    """NaN on first session must NOT be marked as PR.

    RED now: returns (True, None) — NaN is a PR.
    """
    mod = _load_module()
    is_pr, prev = mod.check_pr(direction="higher", current_best=None, new_value=float("nan"))
    assert is_pr is False, (
        f"NaN must never be a PR; check_pr returned is_pr={is_pr!r} "
        f"(should be False). The current_best is None branch fired before "
        "the NaN guard."
    )
    assert prev is None, f"prev should be None when value is NaN (no comparison made); got {prev!r}"


def test_check_pr_first_session_inf_marked_as_pr():
    """+inf/-inf on first session must NOT be marked as PR either."""
    mod = _load_module()
    is_pr_pos, _ = mod.check_pr(direction="higher", current_best=None, new_value=float("inf"))
    is_pr_neg, _ = mod.check_pr(direction="lower", current_best=None, new_value=float("-inf"))
    assert is_pr_pos is False, "inf must not be a PR"
    assert is_pr_neg is False, "-inf must not be a PR"


def test_check_pr_first_session_finite_still_pr():
    """Finite first-session value must still be a PR (regression on the fix)."""
    mod = _load_module()
    is_pr, prev = mod.check_pr(direction="higher", current_best=None, new_value=5.0)
    assert is_pr is True, "5.0 on first session IS a PR; guard must not break this"
    assert prev is None, "first-session PR has no previous best"


def test_check_pr_subsequent_nan_does_not_overwrite_pr():
    """NaN after a real PR must not clobber the existing best."""
    mod = _load_module()
    is_pr, prev = mod.check_pr(direction="higher", current_best=7.0, new_value=float("nan"))
    assert is_pr is False, "NaN vs existing best must not be a PR"
    assert prev == 7.0, f"prev should preserve existing best (7.0), got {prev!r}"


def test_source_does_not_allow_nan_in_comparison():
    """Sanity: the `new_value > current_best` branch must not be reached with NaN.

    If math.isfinite guards the function entry, no NaN can ever reach the
    comparison — even in the not-None path.
    """
    mod = _load_module()
    # Sanity: math.isfinite is in the module source so we know the guard exists.
    src = _load_pr_tracker_source()
    assert "math.isfinite" in src
    # And calling the function with NaN on a subsequent session returns False,
    # not the silently-wrong result of `nan > 7.0 == False` (which happens to
    # be correct by accident) — verify the explicit guard.
    is_pr, _ = mod.check_pr(direction="higher", current_best=7.0, new_value=float("nan"))
    assert is_pr is False
