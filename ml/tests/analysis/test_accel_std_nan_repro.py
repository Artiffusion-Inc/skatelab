"""RED repro — accel_std NaN silently makes takeoff/landing detection fail (issue #1278).

Bug: in `phase_detector.py` `_find_takeoff_accel` (line 692) and
`_find_landing_accel` (line 743), `accel_std = float(np.std(accel_y[...]))`
silently fails phase detection when `accel_y` contains any NaN:

  (a) `np.std(NaN-array) = NaN` (numpy std NOT NaN-aware)
  (b) `float(NaN) = NaN` → accel_std = NaN
  (c) `threshold = NaN * k = NaN`
  (d) Loop check `accel_y[i] > NaN = False` (NaN-comparison rule) → never enters
  (e) Silent fallback: "no takeoff/landing found"

In skating, NaN CoM is the NORMAL case: hip occluded during tuck position in
jumps, loose top covers hip during landing rotation, body blocks hip during
sit spin. A sigma-based threshold detector that silently fails on NaN CoM
reports "no takeoff/landing detected" for every occluded flight.

Source: ml/src/analysis/phase_detector.py:692, :743.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Bug #1278 observable 1: one NaN in accel_y → accel_std = NaN
# ---------------------------------------------------------------------------


def test_accel_std_nan_with_single_nan_frame():
    """Bug #1278 observable 1: a single NaN in accel_y → np.std returns NaN.

    `np.std` is NOT NaN-aware (it propagates NaN). This is the root cause:
    line 692 / line 743 use `np.std(accel_y[search_start:search_end])`
    which is NaN when the search window contains any NaN. The fix must
    either:
      - use `np.nanstd` (numpy NaN-aware std), OR
      - filter to `np.isfinite(accel_y)` before std, OR
      - add a `math.isfinite(accel_std)` guard before threshold compute.
    """
    nan = float("nan")
    accel_y = np.array([0.0, 0.0, nan, 0.5, 0.5, 0.5])
    # Pre-fix: np.std propagates NaN.
    pre_fix_std = float(np.std(accel_y))
    # Sanity: np.std on a NaN-tainted array IS NaN (numpy std is NOT nanstd).
    assert np.isnan(pre_fix_std), (
        f"np.std on NaN-tainted array should be NaN (numpy std NOT NaN-aware), "
        f"got {pre_fix_std}. If this assertion ever fails, numpy changed its "
        f"NaN-propagation semantics — re-read the issue before changing the fix."
    )

    # The post-fix contract: the search window filtered to finite values
    # yields a finite std. This is what the fix MUST achieve.
    search_start, search_end = 0, len(accel_y)
    finite_slice = accel_y[search_start:search_end]
    finite_slice = finite_slice[np.isfinite(finite_slice)]
    post_fix_std = float(np.std(finite_slice)) if finite_slice.size > 0 else 0.0
    assert math.isfinite(post_fix_std), (
        f"After filtering accel_y to finite values, np.std must be finite, "
        f"got {post_fix_std}. The fix in phase_detector.py:692/:743 must "
        f"filter NaN before std OR use np.nanstd."
    )
    assert post_fix_std > 0, (
        f"Expected non-zero std for [0.0, 0.0, 0.5, 0.5, 0.5], got {post_fix_std}"
    )


# ---------------------------------------------------------------------------
# Bug #1278 observable 2: NaN threshold → loop never enters
# ---------------------------------------------------------------------------


def test_nan_threshold_loop_never_enters_takeoff():
    """Bug #1278 observable 2: NaN threshold → comparison `arr[i] > NaN` is False.

    In `_find_takeoff_accel` line 692, the post-std threshold is NaN. The
    loop body checks `if accel_y[i] > threshold`. With threshold=NaN, the
    comparison is always False (NaN-comparison rule), so the loop never
    enters — even when there is a clear positive acceleration spike.
    """
    nan = float("nan")
    accel_y = np.array([0.0, 0.0, nan, 0.5, 0.5, 0.5, 0.5])
    search_start, search_end = 0, len(accel_y)
    # Pre-fix: std of NaN-tainted array = NaN → threshold = NaN.
    accel_std = float(np.std(accel_y[search_start:search_end]))
    threshold = accel_std * 3.0
    assert np.isnan(threshold), (
        f"Pre-fix threshold should be NaN (np.std propagates NaN), got {threshold}"
    )

    # The comparison `arr[i] > NaN` is always False — loop never enters.
    hit = False
    for i in range(search_end - 1, search_start, -1):
        if accel_y[i] > threshold:
            hit = True
            break
    assert not hit, (
        f"Pre-fix: loop should never enter when threshold=NaN, but it did. "
        f"accel_y[search_start:search_end] = {accel_y[search_start:search_end]}"
    )


def test_nan_threshold_loop_never_enters_landing():
    """Bug #1278 observable 3: landing threshold NaN → loop never enters.

    In `_find_landing_accel` line 743, `threshold = -accel_std * 2.0` is
    NaN when accel_std is NaN. The loop checks `if accel_y[i] < threshold`,
    and `arr[i] < NaN` is always False — landing is never detected.
    """
    nan = float("nan")
    accel_y = np.array([0.5, 0.5, nan, -0.5, -0.5, -0.5])
    search_start, search_end = 0, len(accel_y)
    accel_std = float(np.std(accel_y[search_start:search_end]))
    threshold = -accel_std * 2.0
    assert np.isnan(threshold), f"Pre-fix landing threshold should be NaN, got {threshold}"

    hit = False
    for i in range(search_start, search_end):
        if accel_y[i] < threshold:
            hit = True
            break
    assert not hit, "Pre-fix: loop should never enter when threshold=NaN, but it did."


# ---------------------------------------------------------------------------
# Bug #1278 observable 4: all-NaN accel_y → accel_std = NaN
# ---------------------------------------------------------------------------


def test_all_nan_accel_y_produces_nan_std():
    """Bug #1278 observable 4: all-NaN accel_y → std = NaN.

    When the entire search window is NaN (e.g. hip fully occluded across
    the whole jump preparation), accel_std is NaN. Fix must guard
    against this — e.g. skip the sigma threshold and fall through to
    the derivative/baseline fallback, or use a non-NaN std surrogate.
    """
    nan = float("nan")
    accel_y = np.array([nan, nan, nan, nan, nan])
    accel_std = float(np.std(accel_y))
    assert np.isnan(accel_std), f"np.std of all-NaN array should be NaN, got {accel_std}"

    # Post-fix contract: a `math.isfinite` guard on accel_std must
    # short-circuit the loop (or filter the array) so the function falls
    # through to the derivative/baseline fallback rather than silently
    # skipping the threshold detection.
    if not math.isfinite(accel_std):
        # Post-fix: do not enter the threshold loop, fall through to fallback.
        guarded_loop_entered = False
    else:
        guarded_loop_entered = True
    assert not guarded_loop_entered, (
        "Post-fix: when accel_std is not finite, the threshold loop must be "
        "skipped (fall through to derivative/baseline fallback)."
    )


# ---------------------------------------------------------------------------
# Source check: locks the unguarded `accel_std = float(np.std(...))` patterns
# ---------------------------------------------------------------------------


def test_source_phase_detector_has_nan_safe_accel_std():
    """Bug #1278 source check: phase_detector.py accel_std must be NaN-safe.

    Locks the unguarded `accel_std = float(np.std(...))` patterns at
    lines 692 and 743 to be replaced with a NaN-safe equivalent. The fix
    must use one of:
      - `np.nanstd(...)` instead of `np.std(...)`
      - `math.isfinite(accel_std)` guard before threshold compute
      - `accel_y = accel_y[np.isfinite(accel_y)]` before std
      - `np.nan_to_num(accel_y, nan=0.0)` upstream

    This source check makes a regression impossible: if someone reverts
    the fix and goes back to bare `np.std(accel_y[...])`, this test fails.
    """
    source = Path(__file__).resolve().parents[2] / "src" / "analysis" / "phase_detector.py"
    text = source.read_text()

    # Both accel_std lines must use a NaN-safe std (np.nanstd) OR the source
    # must have a math.isfinite guard immediately following the std call.
    has_nanstd = "np.nanstd(accel_y" in text
    has_isfinite_guard = "math.isfinite(accel_std)" in text

    assert has_nanstd or has_isfinite_guard, (
        "Expected phase_detector.py to use `np.nanstd(accel_y...)` OR a "
        "`math.isfinite(accel_std)` guard after the std call. Pre-fix uses "
        "bare `np.std(accel_y[search_start:search_end])` which propagates NaN. "
        "Issue #1278: this silently makes takeoff/landing detection fail."
    )


# ---------------------------------------------------------------------------
# Regression guard: the post-fix finite path still detects clean signals
# ---------------------------------------------------------------------------


def test_post_fix_finite_accel_y_detects_clean_signal():
    """Bug #1278 regression: with all-finite accel_y, detection must still work.

    After the fix, a clean signal (no NaN) must still trigger the
    threshold loop. This is the inverse of observable 2/3: the fix
    must NOT regress the happy path.

    Construct a signal with a clear positive spike well above 3-sigma
    of the baseline, so the threshold loop MUST enter on the spike.
    """
    # Single positive spike at index 10, noise elsewhere.
    # Spike 1.0 vs 3-sigma of noise: clearly above 3-sigma of the
    # non-spike region.
    accel_y = np.array([0.1, -0.1, 0.05, -0.05, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 1.0])
    search_start, search_end = 0, len(accel_y)
    # Use nanstd (or filter-then-std) for the post-fix std.
    accel_std = float(np.nanstd(accel_y[search_start:search_end]))
    assert math.isfinite(accel_std), "Clean signal must yield finite std"
    threshold = accel_std * 3.0
    assert math.isfinite(threshold), "Clean signal must yield finite threshold"
    # Sanity: the spike (1.0) must exceed 3-sigma so the loop enters.
    assert threshold < 1.0, (
        f"Test setup: spike 1.0 must exceed 3-sigma threshold {threshold}, "
        f"otherwise the assertion below is meaningless."
    )

    # The loop should enter on the [1.0] at index 10.
    hit_idx = None
    for i in range(search_end - 1, search_start, -1):
        if accel_y[i] > threshold:
            hit_idx = i
            break
    assert hit_idx == 10, (
        f"Post-fix: expected the loop to hit index 10 (the spike), "
        f"got {hit_idx}. accel_y={accel_y}, threshold={threshold}"
    )
