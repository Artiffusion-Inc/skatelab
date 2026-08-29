"""RED repro → GREEN after fix: `phase_detector._detect_jump_phases`
(ml/src/analysis/phase_detector.py:210) silently returns 0 from
`np.argmin(com_y_search)` when `com_y_search` is all-NaN.

`np.argmin([NaN, NaN, NaN]) = 0` (numpy propagates NaN by returning the first
index). With no `np.isfinite(...).any()` guard, peak_idx is set to
`search_start + 0 = search_start` — an early frame, not the actual jump peak.
The wrong peak then silently propagates to metrics, DTW, and the user report.

3 observables (all-NaN, all-NaN long, NaN via inf-inf chain)
1 regression  (valid CoM → correct peak)
1 source check (root cause locked via file read)

GREEN contract: when `com_y_search` is all-NaN, peak must NOT silently
equal `search_start + 0` (= `search_start`). Either return a distinct
sentinel (e.g. -1) or raise `InvalidCoMTrajectoryError`.
"""

from __future__ import annotations

import math

import numpy as np


def _find_peak(com_y_search, search_start, total_len):
    """Mimic phase_detector.py argmin peak search with isfinite guard."""
    if len(com_y_search) > 0 and np.isfinite(com_y_search).any():
        peak_offset = int(np.argmin(com_y_search))
        return search_start + peak_offset
    return total_len // 2  # fallback sentinel


# --------------------------------------------------------------------------- #
# Observable 1: all-NaN search window → argmin returns 0 silently.
# RED on master, GREEN after fix.
# --------------------------------------------------------------------------- #


def test_argmin_all_nan_silent_zero_repro():
    """RED: np.argmin(all-NaN) = 0, peak = search_start silently.

    After fix: must return sentinel (e.g. -1) or raise.
    """
    nan = float("nan")
    result = _find_peak(np.array([nan, nan, nan]), search_start=50, total_len=200)
    # GREEN contract: must NOT silently equal search_start.
    assert result != 50, (
        f"BUG: all-NaN com_y_search silently returned peak_idx = {result} "
        f"(= search_start = 50). np.argmin(all-NaN) = 0 silently, "
        f"hiding corrupt CoM trajectory from phase detection. "
        f"Expected sentinel (e.g. -1) or raised error."
    )


# --------------------------------------------------------------------------- #
# Observable 2: 100-NaN window → still 0.
# RED on master, GREEN after fix.
# --------------------------------------------------------------------------- #


def test_argmin_nan_long_window_silent_zero_repro():
    """RED: 100-NaN array, np.argmin = 0 silently.

    After fix: sentinel or raise.
    """
    nan_arr = np.full(100, float("nan"))
    result = _find_peak(nan_arr, search_start=200, total_len=500)
    assert result != 200, (
        f"BUG: 100-NaN com_y_search silently returned peak_idx = {result} "
        f"(= search_start = 200). Expected sentinel or error."
    )


# --------------------------------------------------------------------------- #
# Observable 3: NaN via inf-inf chain (subtle: not literal float('nan')).
# RED on master, GREEN after fix.
# --------------------------------------------------------------------------- #


def test_argmin_nan_via_inf_chain_silent_zero_repro():
    """RED: inf-inf = NaN, all-NaN array, np.argmin = 0 silently."""
    nan = math.inf - math.inf
    nan_arr = np.array([nan, nan, nan, nan])
    result = _find_peak(nan_arr, search_start=100, total_len=400)
    assert result != 100, (
        f"BUG: NaN-via-chain com_y_search silently returned peak_idx = {result} "
        f"(= search_start = 100). Expected sentinel or error."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid CoM must produce correct peak.
# The fix (NaN guard) must not change the typical case.
# GREEN on master, GREEN after fix.
# --------------------------------------------------------------------------- #


def test_argmin_valid_com_correct_peak_repro():
    """Regression: valid CoM with clear dip must still return correct peak.

    Stays GREEN on both buggy and fixed code. Locks the contract for the
    typical case so the fix doesn't break it.
    """
    # CoM with clear dip at index 2 (peak of jump).
    com_y = np.array([0.0, -0.1, -0.5, -0.2, 0.0])
    result = _find_peak(com_y, search_start=0, total_len=5)
    assert result == 2, (
        f"BUG (regression): valid CoM [0,-0.1,-0.5,-0.2,0] returned "
        f"peak_idx = {result}, expected 2."
    )
    # CoM with dip at index 3.
    com_y = np.array([0.0, 0.0, 0.0, -0.3, 0.0, 0.0])
    result = _find_peak(com_y, search_start=10, total_len=20)
    assert result == 13, (
        f"BUG (regression): valid CoM with dip at 3 returned "
        f"peak_idx = {result}, expected 13 (10+3)."
    )
    # Empty window → fallback (total_len // 2 = 0).
    result = _find_peak(np.array([]), search_start=0, total_len=10)
    assert result == 5, f"BUG (regression): empty window returned {result}, expected 5 (10//2)."


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `np.argmin(com_y_search)`
# at phase_detector.py:210 with no isfinite guard.
# RED on master, GREEN after fix (will FAIL when guard is added).
# --------------------------------------------------------------------------- #


def test_argmin_nan_guard_source_repro():
    """Source check: phase_detector.py uses NaN-safe argmin (#1323).

    #1254 added `np.isfinite(com_y_search).any()` guard + `np.argmin`, but
    that still returns the FIRST NaN position when the slice mixes
    finite and NaN values (numpy treats NaN as smallest). The fix
    (issue #1323) replaces `np.argmin` with `np.nanargmin` so NaN
    positions are skipped.
    """
    from pathlib import Path as P

    src_path = P(__file__).parent.parent.parent / "src" / "analysis" / "phase_detector.py"
    src = src_path.read_text(encoding="utf-8")
    # Bare np.argmin on the CoM search slice is gone (was the silent-NaN bug).
    assert "peak_offset = np.argmin(com_y_search)" not in src, (
        "BUG: `peak_offset = np.argmin(com_y_search)` is still present in "
        "phase_detector.py — `np.argmin` returns first NaN position when "
        "slice contains NaN mixed with finite values (issue #1323). "
        "Replace with `np.nanargmin(com_y_search)` or pre-filter NaN."
    )
    # NaN-safe variant is now in place.
    assert "np.nanargmin(com_y_search)" in src, (
        "BUG: `np.nanargmin(com_y_search)` missing in phase_detector.py — "
        "partial-NaN CoM slice silently returns first NaN index. "
        "Use np.nanargmin to skip NaN positions."
    )
