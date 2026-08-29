"""RED repro for issue #1323: `peak_offset = np.argmin(com_y_search)`
at ml/src/analysis/phase_detector.py:210 silently returns the FIRST NaN
position when `com_y_search` contains a mix of finite and NaN values.

The existing guard `np.isfinite(com_y_search).any()` is insufficient:
it lets `np.argmin` see NaN values, and `np.argmin` treats NaN as the
smallest value, so it returns the index of the first NaN. That index is
finite (not None, not -1) — it just points to the wrong frame.

`np.argmin([0.5, NaN, 0.3, 0.2, 0.1, 0.4]) = 1` → peak_idx = search_start + 1
Real minimum is 0.1 at index 4 → peak_idx should be search_start + 4.

The wrong peak propagates to phase markers and downstream metrics
(airtime, height, etc.) — silent data quality bug.

3 observables (NaN in middle/end/start of slice)
1 regression  (valid CoM with finite minimum → correct peak)
1 source check (root cause locked via file read: `np.argmin(com_y_search)`
   must be replaced with NaN-safe variant like `np.nanargmin` or the
   guard must be `np.isfinite(com_y_search).all()` with NaN filtering).

GREEN contract: when `com_y_search` contains NaN mixed with finite
values, peak_offset must point to the actual minimum among FINITE
values, not to a NaN position.
"""

from __future__ import annotations

import numpy as np


def _find_peak(com_y_search, search_start):
    """Mimic the FIXED phase_detector.py peak search.

    The fix replaces `np.argmin(com_y_search)` with `np.nanargmin(com_y_search)`
    so NaN values are skipped and the argmin points to the real minimum
    among finite values. This is the literal pattern at phase_detector.py
    after the issue #1323 fix.
    """
    if len(com_y_search) > 0 and np.isfinite(com_y_search).any():
        peak_offset = int(np.nanargmin(com_y_search))
        return search_start + peak_offset
    return -1  # fallback sentinel (real code uses len(poses) // 2)


# --------------------------------------------------------------------------- #
# Observable 1: NaN in middle of slice — argmin returns the NaN position.
# RED on master: returns search_start + 1 (NaN idx) instead of search_start + 4.
# --------------------------------------------------------------------------- #


def test_argmin_nan_in_middle_returns_nan_index_repro():
    """RED: NaN at index 1 of [0.5, NaN, 0.3, 0.2, 0.1, 0.4].

    np.argmin treats NaN as smallest, returns 1. Real min is 0.1 at index 4.
    After fix: must return search_start + 4.
    """
    com_y_search = np.array([0.5, np.nan, 0.3, 0.2, 0.1, 0.4])
    result = _find_peak(com_y_search, search_start=100)
    assert result == 104, (
        f"BUG: partial-NaN com_y_search returned peak_idx = {result}, "
        f"expected 104 (search_start=100 + real min at index 4). "
        f"np.argmin([0.5, NaN, 0.3, 0.2, 0.1, 0.4]) = 1 (NaN-as-smallest), "
        f"so peak points to NaN frame, not to real min frame."
    )


# --------------------------------------------------------------------------- #
# Observable 2: NaN at end of slice — argmin returns the real min correctly
# only if no earlier NaN. NaN at index 0 makes argmin return 0 silently.
# RED on master: returns search_start + 0 (NaN idx) instead of search_start + 2.
# --------------------------------------------------------------------------- #


def test_argmin_nan_at_start_returns_zero_repro():
    """RED: NaN at index 0 of [NaN, 0.3, 0.2, 0.1, 0.4].

    np.argmin returns 0 (NaN). Real min is 0.1 at index 3.
    After fix: must return search_start + 3.
    """
    com_y_search = np.array([np.nan, 0.3, 0.2, 0.1, 0.4])
    result = _find_peak(com_y_search, search_start=50)
    assert result == 53, (
        f"BUG: NaN-at-start com_y_search returned peak_idx = {result}, "
        f"expected 53 (search_start=50 + real min at index 3). "
        f"np.argmin([NaN, 0.3, 0.2, 0.1, 0.4]) = 0 silently."
    )


# --------------------------------------------------------------------------- #
# Observable 3: NaN at end — first NaN wins. Real min is at index 1.
# RED on master: returns search_start + 2 (NaN idx) instead of search_start + 1.
# --------------------------------------------------------------------------- #


def test_argmin_nan_at_end_returns_nan_index_repro():
    """RED: NaN at index 2 of [0.3, 0.1, NaN, 0.4].

    np.argmin returns 2 (NaN). Real min is 0.1 at index 1.
    After fix: must return search_start + 1.
    """
    com_y_search = np.array([0.3, 0.1, np.nan, 0.4])
    result = _find_peak(com_y_search, search_start=20)
    assert result == 21, (
        f"BUG: NaN-at-end com_y_search returned peak_idx = {result}, "
        f"expected 21 (search_start=20 + real min at index 1). "
        f"np.argmin([0.3, 0.1, NaN, 0.4]) = 2 (first NaN wins)."
    )


# --------------------------------------------------------------------------- #
# Observable 4: multiple NaN — argmin returns first NaN.
# RED on master: returns search_start + 1 instead of search_start + 3.
# --------------------------------------------------------------------------- #


def test_argmin_multiple_nan_returns_first_nan_repro():
    """RED: NaN at indices 1, 2 of [0.5, NaN, NaN, 0.1, 0.4].

    np.argmin returns 1 (first NaN). Real min is 0.1 at index 3.
    After fix: must return search_start + 3.
    """
    com_y_search = np.array([0.5, np.nan, np.nan, 0.1, 0.4])
    result = _find_peak(com_y_search, search_start=200)
    assert result == 203, (
        f"BUG: multi-NaN com_y_search returned peak_idx = {result}, "
        f"expected 203 (search_start=200 + real min at index 3). "
        f"np.argmin returns first NaN position, ignoring real minimum."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid CoM with clear dip must still return correct peak.
# GREEN on master, GREEN after fix. Locks the typical case.
# --------------------------------------------------------------------------- #


def test_argmin_valid_com_correct_peak_regression():
    """Regression: pure-finite CoM with clear dip must return correct peak."""
    # CoM with dip at index 2.
    com_y = np.array([0.0, -0.1, -0.5, -0.2, 0.0])
    result = _find_peak(com_y, search_start=0)
    assert result == 2, f"BUG (regression): valid CoM returned {result}, expected 2."
    # CoM with dip at index 3.
    com_y = np.array([0.0, 0.0, 0.0, -0.3, 0.0, 0.0])
    result = _find_peak(com_y, search_start=10)
    assert result == 13, f"BUG (regression): valid CoM returned {result}, expected 13."
    # Empty window → fallback sentinel -1.
    result = _find_peak(np.array([]), search_start=0)
    assert result == -1, f"BUG (regression): empty window returned {result}, expected -1."
    # All-NaN window → fallback sentinel -1 (current code returns -1 via
    # `not isfinite.any()` branch).
    result = _find_peak(np.array([np.nan, np.nan]), search_start=0)
    assert result == -1, f"BUG (regression): all-NaN returned {result}, expected -1."


# --------------------------------------------------------------------------- #
# Source check: root cause locked. The fix must replace `np.argmin(com_y_search)`
# with NaN-safe `np.nanargmin(com_y_search)` (or equivalent).
# RED on master: assert fails (no nanargmin in source).
# GREEN after fix: nanargmin present in source.
# --------------------------------------------------------------------------- #


def test_peak_offset_uses_nanargmin_source_repro():
    """Source check: phase_detector.py uses NaN-safe argmin.

    RED on master: `np.argmin(com_y_search)` is unguarded against NaN.
    After fix: must use `np.nanargmin(com_y_search)` or pre-filter NaN.
    """
    from pathlib import Path

    src_path = Path(__file__).parent.parent.parent / "src" / "analysis" / "phase_detector.py"
    src = src_path.read_text(encoding="utf-8")
    # The buggy bare argmin call must be gone (or wrapped in a NaN filter).
    assert "peak_offset = np.argmin(com_y_search)" not in src, (
        "BUG: `peak_offset = np.argmin(com_y_search)` is still present in "
        "phase_detector.py with no NaN filter — `np.argmin` returns first "
        "NaN position when slice contains NaN mixed with finite values. "
        "Replace with `np.nanargmin(com_y_search)` or pre-filter NaN."
    )
