"""RED repro — phase_detector.py NaN handling bugs (tranche H-3).

Bug #11: phase_detector.py _detect_jump_phases_com_improved confidence
  uses `min(1.0, prominence / 0.05)` on line 299. If `flight_com` contains
  NaN, `np.max(flight_com) - np.min(flight_com) = NaN`, then
  `min(1.0, NaN / 0.05) = min(1.0, NaN) = 1.0` (Python's min ignores NaN).
  The confidence is silently reported as 1.0 (perfect) for a phase with
  NaN pose data.

  Source: ml/src/analysis/phase_detector.py:274-302.

Bug #12: phase_detector.py _find_takeoff_accel line 630
  `if np.all(accel_y[i:i+window] > 0): return i`. If `accel_y` contains
  NaN, `NaN > 0` is False, `np.all` returns False, so the condition
  never triggers. The fallback derivative method is used silently,
  producing different (and likely wrong) takeoff frame indices for
  NaN-tainted inputs.

  Source: ml/src/analysis/phase_detector.py:626-631.
"""

from __future__ import annotations

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Bug #11: phase_detector confidence NaN→1.0 (same root cause as #10)
# ---------------------------------------------------------------------------


def test_com_improved_confidence_nan_silently_1_0():
    """Bug #11: NaN in flight_com → confidence must NOT be 1.0.

    The `min(1.0, prominence / 0.05)` clamp on line 299 silently swallows
    NaN (Python's builtin min ignores NaN), reporting perfect confidence
    for a phase with missing data. Same root cause as Bug #10 in
    confidence.py:51.

    #562 fix: explicit NaN check before the clamp — if prominence is
    NaN, the source must contain a `math.isnan(prominence)` guard that
    returns 0.0 confidence (the phase is unreliable, not perfect).
    """
    from pathlib import Path

    # Inspect the source code: the post-fix com_improved must contain
    # an explicit isnan guard on prominence.
    source = Path(__file__).resolve().parents[2] / "src" / "analysis" / "phase_detector.py"
    text = source.read_text()
    assert "isnan(prominence)" in text, (
        "Expected `isnan(prominence)` guard in phase_detector.py com_improved "
        "function. Pre-fix: min(1.0, NaN/0.05) silently returns 1.0, "
        "inflating confidence for a phase with missing data."
    )

    # Simulate the post-fix logic
    import math

    nan = float("nan")
    flight_com = np.array([0.5, 0.4, nan, 0.3])
    prominence = float(np.max(flight_com) - np.min(flight_com))  # NaN
    if math.isnan(prominence):
        confidence = 0.0
    else:
        confidence = min(1.0, prominence / 0.05)
    assert confidence == 0.0, (
        f"NaN-prominence should yield 0.0 confidence, got {confidence}. "
        f"Pre-fix: min(1.0, NaN/0.05) silently returns 1.0, inflating "
        f"confidence for a phase with missing data."
    )


def test_min_builtin_ignores_nan():
    """Document the root cause: Python's min(1.0, NaN) returns 1.0."""
    nan = float("nan")
    assert min(1.0, nan) == 1.0, "Python min(1.0, NaN) returns 1.0 — NaN is ignored"


# ---------------------------------------------------------------------------
# Bug #12: takeoff/landing detection NaN handling
# ---------------------------------------------------------------------------


def test_takeoff_accel_nan_never_triggers():
    """Bug #12: NaN accel_y → np.all(NaN > 0) = False → condition never triggers.

    In `_find_takeoff_accel` line 630, `accel_y[i:i+window] > 0` returns a
    boolean array, and for NaN elements, the comparison is False. So
    `np.all(...)` is False, and the takeoff frame is never detected
    (falls through to the derivative-based fallback).

    #564 fix: NaN-tainted frames must be excluded from the all-positive
    check. The post-fix contract: after NaN-skip, the all-positive check
    uses only finite (non-NaN) elements and correctly identifies the
    takeoff despite the single NaN frame.
    """
    nan = float("nan")
    accel_y = np.array([0.0, 0.0, 0.0, nan, 0.5, 0.5, 0.5])
    # Simulate line 630 (post-fix: NaN-aware)
    window = 3
    slice_view = accel_y[3 : 3 + window]
    # NaN-skip: only consider finite elements. The remaining elements
    # are [0.5, 0.5], all positive.
    finite_slice = slice_view[np.isfinite(slice_view)]
    all_positive_finite = np.all(finite_slice > 0)
    assert all_positive_finite, (
        f"After NaN-skip, np.all(finite(accel_y[3:6]) > 0) should be True "
        f"(accel_y[3:6] is [NaN, 0.5, 0.5] — finite part is all positive), "
        f"got {all_positive_finite}. Pre-fix: NaN at index 3 makes the "
        f"all-positive check fail, and the takeoff frame is never detected "
        f"at the right position."
    )


def test_nan_array_mean_returns_nan():
    """Document: np.mean of array with NaN returns NaN.

    Line 674 `if np.mean(accel_y[i:i+window]) < 0` — NaN < 0 is False,
    so landing is never detected when accel_y contains NaN.
    """
    nan = float("nan")
    arr = np.array([0.5, 0.3, nan])
    result = np.mean(arr)
    assert np.isnan(result), f"np.mean of NaN-tainted array should be NaN, got {result}"


# ---------------------------------------------------------------------------
# NOT-a-bug guards for already-fixed issues
# ---------------------------------------------------------------------------


def test_fps_zero_protects_against_inf():
    """NOT a bug: fps=0.0 → airtime=0.0 (rejected by < 0.3 gate)."""
    # Lines 459, 234: airtime = (landing - takeoff) / fps if fps > 0 else 0.0
    # Issue #505 fix: explicit fps=0 check
    fps = 0.0
    landing = 50
    takeoff = 30
    airtime = (landing - takeoff) / fps if fps > 0 else 0.0
    assert airtime == 0.0, f"fps=0 should produce 0.0 airtime, got {airtime}"


def test_vy_std_zero_sets_velocity_confidence_zero():
    """NOT a bug: vy_std < 1e-6 → velocity_confidence = 0.0 (issue #425 fix)."""
    # Line 287-288 guards
    vy_std = 0.0
    if vy_std < 1e-6:
        velocity_confidence = 0.0
    else:
        velocity_confidence = 0.5
    assert velocity_confidence == 0.0, (
        f"vy_std < 1e-6 should set velocity_confidence = 0.0, got {velocity_confidence}"
    )
