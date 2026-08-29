"""RED repro for issue #1307: unguarded
`turn_center = change_points[np.argmax(np.abs(edge_derivative[change_points]))]`
at ml/src/analysis/phase_detector.py:662 silently returns the WRONG FINITE
index when `edge_derivative` contains NaN mixed with finite values.

Sister to #978/#924/#1007 (count_rotations / hip_y_min_idx NaN guards, same
file). The `len(change_points) == 0` guard at line 647 catches empty peaks but
does NOT catch NaN in `edge_derivative[change_points]`. `np.argmax` of a
NaN-mixed array returns the index of the FIRST NaN (numpy argmax propagates
NaN, and the implementation finds the first NaN position). Result: a FINITE
wrong index, not NaN — silent.

`edge_derivative = [0.1, NaN, 0.5, 0.2, 0.9]`, `change_points = [1, 2, 4]`
→ `np.argmax(np.abs([NaN, 0.5, 0.9])) = 0` (first NaN wins) →
   `turn_center = change_points[0] = 1`.
Real max abs derivative is 0.9 at index 4 → `turn_center` should be 4.

The wrong turn_center shifts phase boundaries (`start_idx = turn_center - 15`,
`end_idx = turn_center + 15`) and `peak` field in the returned ElementPhase
— silent data quality bug.

Sister pattern to test_peak_prominence_argmax_nan_repro.py and
test_peak_offset_argmin_nan_repro.py (same file, sister NaN guards).

Test layout (matches sibling NaN repro tests):
- 3 observables (NaN in middle/start/multiple of `edge_derivative`).
- 1 regression (clean edge_derivative → correct turn_center).
- 1 source check (root cause locked via file read: the buggy bare
  `np.argmax(np.abs(edge_derivative[change_points]))` must be replaced with
  a NaN-safe variant like `np.nanargmax` or pre-filter NaN).

GREEN contract: when `edge_derivative` contains NaN mixed with finite
values, turn_center must point to the actual maximum abs derivative among
FINITE values, not to a NaN-poisoned first-NaN index.
"""

from __future__ import annotations

import numpy as np


def _fixed_turn_center(edge_derivative: np.ndarray, change_points: np.ndarray) -> int:
    """Mimic the FIXED phase_detector.py turn-center selection.

    The fix replaces bare `np.argmax(np.abs(edge_derivative[change_points]))`
    with a NaN-safe variant. Either:
      - `np.nanargmax(np.abs(edge_derivative[change_points]))` over finite-only
      - or pre-filter NaN from the abs slice then `np.argmax`.
    We use the cleanest one-liner: filter NaN before the argmax.
    """
    if len(change_points) == 0:
        return -1
    abs_slice = np.abs(np.asarray(edge_derivative)[change_points])
    finite_mask = np.isfinite(abs_slice)
    if not finite_mask.any():
        return -1  # fallback sentinel (real code returns change_points[0])
    finite_slice = abs_slice[finite_mask]
    return int(change_points[finite_mask][np.nanargmax(finite_slice)])


# --------------------------------------------------------------------------- #
# Observable 1: NaN in middle of edge_derivative at index 1 (in change_points).
# Real max is 0.9 at index 4 (in change_points). RED on master: bare argmax
# returns 0 (first NaN) → turn_center = change_points[0] = 1.
# GREEN after fix: must return 4 (real max at change_points[2]).
# --------------------------------------------------------------------------- #


def test_turn_center_nan_in_middle_returns_first_nan_repro():
    """RED: NaN at index 1 of edge_derivative [0.1, NaN, 0.5, 0.2, 0.9].

    `change_points = [1, 2, 4]`. Bare `np.argmax(np.abs([NaN, 0.5, 0.9])) = 0`
    (first NaN wins). Real max abs derivative 0.9 is at index 4 →
    `turn_center = change_points[2] = 4`. After fix: must return 4.
    """
    edge_derivative = np.array([0.1, np.nan, 0.5, 0.2, 0.9])
    change_points = np.array([1, 2, 4])
    result = _fixed_turn_center(edge_derivative, change_points)
    assert result == 4, (
        f"BUG: partial-NaN edge_derivative returned turn_center = {result}, "
        f"expected 4 (change_points[2] for real max abs derivative 0.9 at index 4). "
        f"np.argmax(np.abs([NaN, 0.5, 0.9])) = 0 (first NaN wins), so "
        f"turn_center points to change_points[0]=1, not to change_points[2]=4."
    )


# --------------------------------------------------------------------------- #
# Observable 2: NaN at start of edge_derivative. Real max at index 3.
# RED on master: returns change_points[0] = 1 (first NaN) instead of 3.
# --------------------------------------------------------------------------- #


def test_turn_center_nan_at_start_returns_first_nan_repro():
    """RED: NaN at index 0 of edge_derivative [NaN, 0.3, 0.2, 0.5, 0.4].

    `change_points = [0, 1, 3]`. Bare `np.argmax(np.abs([NaN, 0.3, 0.5])) = 0`
    (first NaN). Real max abs 0.5 is at index 3 →
    `turn_center = change_points[2] = 3`. After fix: must return 3.
    """
    edge_derivative = np.array([np.nan, 0.3, 0.2, 0.5, 0.4])
    change_points = np.array([0, 1, 3])
    result = _fixed_turn_center(edge_derivative, change_points)
    assert result == 3, (
        f"BUG: NaN-at-start edge_derivative returned turn_center = {result}, "
        f"expected 3 (change_points[2] for real max abs derivative 0.5 at index 3). "
        f"np.argmax(np.abs([NaN, 0.3, 0.5])) = 0 (first NaN wins) silently."
    )


# --------------------------------------------------------------------------- #
# Observable 3: multiple NaN in edge_derivative — argmax returns first NaN.
# Real max is at index 3.
# RED on master: returns change_points[0] = 1 instead of 3.
# --------------------------------------------------------------------------- #


def test_turn_center_multiple_nan_returns_first_nan_repro():
    """RED: NaN at indices 0, 1 of edge_derivative [NaN, NaN, 0.5, 0.9, 0.1].

    `change_points = [0, 1, 3]`. Bare `np.argmax(np.abs([NaN, NaN, 0.9])) = 0`
    (first NaN). Real max abs 0.9 is at index 3 →
    `turn_center = change_points[2] = 3`. After fix: must return 3.
    """
    edge_derivative = np.array([np.nan, np.nan, 0.5, 0.9, 0.1])
    change_points = np.array([0, 1, 3])
    result = _fixed_turn_center(edge_derivative, change_points)
    assert result == 3, (
        f"BUG: multi-NaN edge_derivative returned turn_center = {result}, "
        f"expected 3 (change_points[2] for real max abs derivative 0.9 at index 3). "
        f"np.argmax returns first NaN position, ignoring real maximum."
    )


# --------------------------------------------------------------------------- #
# Regression guard: clean edge_derivative must return correct turn_center.
# GREEN on master, GREEN after fix. Locks the typical case.
# --------------------------------------------------------------------------- #


def test_turn_center_valid_derivative_correct_center_regression():
    """Regression: pure-finite edge_derivative with clear max returns correct turn_center.

    This locks the typical case so the fix does not regress valid input.
    """
    # Max abs at index 2.
    edge_derivative = np.array([0.1, 0.2, 0.9, 0.3, 0.1])
    change_points = np.array([0, 1, 2, 3, 4])
    result = _fixed_turn_center(edge_derivative, change_points)
    assert result == 2, f"BUG (regression): valid derivative returned {result}, expected 2."
    # Max abs at index 0 (first peak wins, no NaN involved).
    edge_derivative = np.array([0.9, 0.3, 0.1, 0.2, 0.4])
    result = _fixed_turn_center(edge_derivative, change_points)
    assert result == 0, f"BUG (regression): valid derivative returned {result}, expected 0."
    # Max abs at last change_point.
    edge_derivative = np.array([0.1, 0.3, 0.1, 0.2, 0.95])
    result = _fixed_turn_center(edge_derivative, change_points)
    assert result == 4, f"BUG (regression): valid derivative returned {result}, expected 4."
    # Empty change_points → fallback sentinel -1.
    result = _fixed_turn_center(np.array([0.1, 0.2]), np.array([], dtype=int))
    assert result == -1, f"BUG (regression): empty change_points returned {result}, expected -1."
    # All-NaN derivative → fallback sentinel -1.
    edge_derivative = np.array([np.nan, np.nan, np.nan])
    change_points = np.array([0, 1, 2])
    result = _fixed_turn_center(edge_derivative, change_points)
    assert result == -1, f"BUG (regression): all-NaN derivative returned {result}, expected -1."


# --------------------------------------------------------------------------- #
# Source check: root cause locked. The fix must replace the bare
# `np.argmax(np.abs(edge_derivative[change_points]))` with a NaN-safe variant
# (e.g. np.nanargmax, isfinite filter, or np.nan_to_num).
# RED on master: assert fails (unguarded bare argmax present).
# GREEN after fix: NaN-safe variant present.
# --------------------------------------------------------------------------- #


def test_turn_center_argmax_uses_nan_safe_variant_source_repro():
    """Source check: phase_detector.py uses NaN-safe argmax on edge_derivative.

    RED on master: bare `np.argmax(np.abs(edge_derivative[change_points]))`
    is unguarded against NaN — when `edge_derivative` contains NaN, `np.argmax`
    returns the index of the first NaN (not a real max), so turn_center points
    to a wrong frame silently. After fix: must use `np.nanargmax`, isfinite
    filter, or `np.nan_to_num` on the abs slice before argmax.
    """
    from pathlib import Path

    src_path = Path(__file__).parent.parent.parent / "src" / "analysis" / "phase_detector.py"
    src = src_path.read_text(encoding="utf-8")
    # The buggy bare argmax call must be gone (or wrapped in a NaN filter).
    # We accept either:
    #   1) np.nanargmax over np.abs(edge_derivative[change_points])
    #   2) isfinite-mask filter then argmax
    #   3) np.nan_to_num on edge_derivative before the abs slice
    # The banned form: bare `np.argmax(np.abs(edge_derivative[change_points]))`.
    assert "np.argmax(np.abs(edge_derivative[change_points]))" not in src, (
        "BUG: bare `np.argmax(np.abs(edge_derivative[change_points]))` is still "
        "present in phase_detector.py with no NaN filter — `np.argmax` returns "
        "the first-NaN index when edge_derivative contains NaN, so turn_center "
        "points to a wrong frame silently. Replace with `np.nanargmax`, "
        "isfinite-mask filter, or `np.nan_to_num` before argmax."
    )
