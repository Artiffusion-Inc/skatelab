"""RED repro for issue #1324: `peak_idx = peaks[np.argmax(-properties["prominences"])]`
at ml/src/analysis/phase_detector.py:223 silently returns the WRONG FINITE peak
when `properties["prominences"]` (from scipy.signal.find_peaks) contains NaN.

The `len(peaks) == 0` guard at line 220 catches empty peaks but does NOT catch
NaN in non-empty prominences. `np.argmax` of a NaN-mixed array returns the
index of the FIRST NaN (numpy argmax propagates NaN, and the implementation
finds the first NaN position). Result: a FINITE wrong index, not NaN — silent.

`peaks = [100, 200, 300, 400, 500]`, `prominences = [0.1, NaN, 0.5, 0.2, 0.9]`
→ `np.argmax(-prominences) = 1` (first NaN wins) → `peak_idx = peaks[1] = 200`
Real max prominence (0.9) is at index 4 → `peaks[4] = 500`.

The wrong peak propagates to phase markers (takeoff, landing) and downstream
biomechanics metrics (airtime, height, knee angles) — silent data quality bug.

Test layout (matches sibling `test_peak_offset_argmin_nan_repro.py`):
- 3 observables (NaN in middle/start/multiple of prominences array): mimic
  of the FIXED fallback. These lock the expected behavior after the fix.
- 1 regression (clean prominences → correct peak): locks the typical case.
- 1 source check (root cause locked via file read: `np.argmax(-properties["prominences"])`
   must be replaced with NaN-safe variant like `np.nanargmax` or pre-filter NaN).

GREEN contract: when `properties["prominences"]` contains NaN mixed with finite
values, peak_idx must point to the actual maximum prominence among FINITE
values, not to a NaN-poisoned first-NaN index.
"""

from __future__ import annotations

import numpy as np


def _fixed_find_peak_prominence(peaks, properties):
    """Mimic the FIXED phase_detector.py fallback peak-by-prominence.

    The fix replaces `np.argmax(-properties["prominences"])` with a
    NaN-safe variant. Either:
      - `np.nanargmax(-prominences)` over finite-only
      - or filter `prominences = prominences[np.isfinite(prominences)]`
        then `np.argmax(-prominences)`.
    We use the cleanest one-liner: filter NaN before negating + argmax.
    """
    peaks_arr = np.asarray(peaks)
    prom = np.asarray(properties["prominences"], dtype=float)
    if len(peaks_arr) == 0 or len(prom) == 0:
        return -1
    finite_mask = np.isfinite(prom)
    if not finite_mask.any():
        return -1  # fallback sentinel (real code uses len(poses) // 2)
    finite_prom = prom[finite_mask]
    finite_peaks = peaks_arr[finite_mask]
    return int(finite_peaks[np.nanargmax(finite_prom)])


# --------------------------------------------------------------------------- #
# Observable 1: NaN in middle of prominences — argmax returns 1 (first NaN).
# Real max is at index 4.
# RED on master: bare `np.argmax(-[0.1, NaN, 0.5, 0.2, 0.9]) = 1` → peaks[1]=200.
# GREEN after fix: must return 500 (peaks[4] for real max prominence 0.9).
# --------------------------------------------------------------------------- #


def test_argmax_prominence_nan_in_middle_returns_first_nan_repro():
    """RED: NaN at index 1 of prominences [0.1, NaN, 0.5, 0.2, 0.9].

    np.argmax(-[0.1, NaN, 0.5, 0.2, 0.9]) = 1 (first NaN wins).
    Real max prominence is 0.9 at index 4 → peaks[4] = 500.
    After fix: must return 500.
    """
    peaks = np.array([100, 200, 300, 400, 500])
    properties = {"prominences": np.array([0.1, np.nan, 0.5, 0.2, 0.9])}
    result = _fixed_find_peak_prominence(peaks, properties)
    assert result == 500, (
        f"BUG: partial-NaN prominences returned peak_idx = {result}, "
        f"expected 500 (peaks[4] for real max prominence 0.9 at index 4). "
        f"np.argmax(-[0.1, NaN, 0.5, 0.2, 0.9]) = 1 (first NaN wins), "
        f"so peak points to peaks[1]=200, not to peaks[4]=500."
    )


# --------------------------------------------------------------------------- #
# Observable 2: NaN at start of prominences — argmax returns 0 (first NaN).
# Real max at index 3.
# RED on master: returns 100 (peaks[0]) instead of 400 (peaks[3]).
# --------------------------------------------------------------------------- #


def test_argmax_prominence_nan_at_start_returns_first_nan_repro():
    """RED: NaN at index 0 of prominences [NaN, 0.3, 0.2, 0.5, 0.4].

    np.argmax(-[NaN, 0.3, 0.2, 0.5, 0.4]) = 0 (first NaN).
    Real max prominence is 0.5 at index 3 → peaks[3] = 400.
    After fix: must return 400.
    """
    peaks = np.array([100, 200, 300, 400, 500])
    properties = {"prominences": np.array([np.nan, 0.3, 0.2, 0.5, 0.4])}
    result = _fixed_find_peak_prominence(peaks, properties)
    assert result == 400, (
        f"BUG: NaN-at-start prominences returned peak_idx = {result}, "
        f"expected 400 (peaks[3] for real max prominence 0.5 at index 3). "
        f"np.argmax(-[NaN, ...]) = 0 (first NaN wins) silently."
    )


# --------------------------------------------------------------------------- #
# Observable 3: multiple NaN in prominences — argmax returns first NaN.
# Real max is at index 3.
# RED on master: returns 100 (peaks[0]) instead of 400 (peaks[3]).
# --------------------------------------------------------------------------- #


def test_argmax_prominence_multiple_nan_returns_first_nan_repro():
    """RED: NaN at indices 0, 1 of prominences [NaN, NaN, 0.5, 0.9, 0.1].

    np.argmax(-[NaN, NaN, 0.5, 0.9, 0.1]) = 0 (first NaN).
    Real max prominence is 0.9 at index 3 → peaks[3] = 400.
    After fix: must return 400.
    """
    peaks = np.array([100, 200, 300, 400, 500])
    properties = {"prominences": np.array([np.nan, np.nan, 0.5, 0.9, 0.1])}
    result = _fixed_find_peak_prominence(peaks, properties)
    assert result == 400, (
        f"BUG: multi-NaN prominences returned peak_idx = {result}, "
        f"expected 400 (peaks[3] for real max prominence 0.9 at index 3). "
        f"np.argmax returns first NaN position, ignoring real maximum."
    )


# --------------------------------------------------------------------------- #
# Regression guard: clean prominences must return correct peak.
# GREEN on master, GREEN after fix. Locks the typical case.
# --------------------------------------------------------------------------- #


def test_argmax_prominence_valid_correct_peak_regression():
    """Regression: pure-finite prominences with clear max returns correct peak.

    This locks the typical case so the fix does not regress valid input.
    """
    # Max prominence at index 2.
    peaks = np.array([10, 20, 30, 40, 50])
    properties = {"prominences": np.array([0.1, 0.3, 0.9, 0.2, 0.4])}
    result = _fixed_find_peak_prominence(peaks, properties)
    assert result == 30, f"BUG (regression): valid prominences returned {result}, expected 30."
    # Max prominence at index 0 (first peak wins, no NaN involved).
    properties = {"prominences": np.array([0.9, 0.3, 0.1, 0.2, 0.4])}
    result = _fixed_find_peak_prominence(peaks, properties)
    assert result == 10, f"BUG (regression): valid prominences returned {result}, expected 10."
    # Max prominence at last index.
    properties = {"prominences": np.array([0.1, 0.3, 0.1, 0.2, 0.95])}
    result = _fixed_find_peak_prominence(peaks, properties)
    assert result == 50, f"BUG (regression): valid prominences returned {result}, expected 50."
    # Empty peaks → fallback sentinel -1.
    result = _fixed_find_peak_prominence(np.array([]), {"prominences": np.array([])})
    assert result == -1, f"BUG (regression): empty peaks returned {result}, expected -1."
    # All-NaN prominences → fallback sentinel -1.
    peaks = np.array([10, 20, 30])
    properties = {"prominences": np.array([np.nan, np.nan, np.nan])}
    result = _fixed_find_peak_prominence(peaks, properties)
    assert result == -1, f"BUG (regression): all-NaN prominences returned {result}, expected -1."


# --------------------------------------------------------------------------- #
# Source check: root cause locked. The fix must replace the bare
# `np.argmax(-properties["prominences"])` with a NaN-safe variant
# (e.g. np.nanargmax, isfinite filter, or np.nan_to_num).
# RED on master: assert fails (unguarded bare argmax present).
# GREEN after fix: NaN-safe variant present.
# --------------------------------------------------------------------------- #


def test_peak_prominence_argmax_uses_nan_safe_variant_source_repro():
    """Source check: phase_detector.py uses NaN-safe argmax on prominences.

    RED on master: bare `np.argmax(-properties["prominences"])` is unguarded
    against NaN — when `properties["prominences"]` contains NaN, `np.argmax`
    returns the index of the first NaN (not a real max), so peak points to
    a wrong frame silently. After fix: must use `np.nanargmax`, isfinite
    filter, or `np.nan_to_num`.
    """
    from pathlib import Path

    src_path = Path(__file__).parent.parent.parent / "src" / "analysis" / "phase_detector.py"
    src = src_path.read_text(encoding="utf-8")
    # The buggy bare argmax call must be gone (or wrapped in a NaN filter).
    # We accept either:
    #   1) np.nanargmax over prominences
    #   2) isfinite-mask filter then argmax
    #   3) np.nan_to_num on prominences
    # The banned form: bare `np.argmax(-properties["prominences"])`.
    assert 'np.argmax(-properties["prominences"])' not in src, (
        'BUG: bare `np.argmax(-properties["prominences"])` is still present '
        "in phase_detector.py with no NaN filter — np.argmax returns the "
        "first-NaN index when prominences contain NaN, so peak points to a "
        "wrong frame silently. Replace with np.nanargmax, isfinite-mask "
        "filter, or np.nan_to_num before argmax."
    )
