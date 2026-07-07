"""RED repro — `BiomechanicsAnalyzer.compute_landing_smoothness`
(ml/src/analysis/metrics.py:1060+) crashes with uncaught
`ValueError: cannot convert float NaN to integer` when `fps` is
NaN, due to the unguarded `int(0.5 * fps)`.

Root cause (ml/src/analysis/metrics.py:1085):
    window_frames = int(0.5 * fps)
    # ↑ 0.5 * NaN = NaN → int(NaN) = ValueError

Steps before the int conversion (phases.end check, post_landing_start,
post_landing_end) do NOT use `fps`. So with NaN fps, the function reaches
the window-frames calc — the only fps-dependent step in the body before
any return. No `math.isfinite(fps)` guard.

Verified empirically:
    BiomechanicsAnalyzer().compute_landing_smoothness(poses, phases, fps=NaN)
        → ValueError: cannot convert float NaN to integer
    BiomechanicsAnalyzer().compute_landing_smoothness(poses, phases, fps=30.0)
        → valid float smoothness score

Consumer chain: `compute_landing_smoothness` is called by the recommender
and the metrics dict assembly. A NaN fps from corrupt video metadata
crashes the entire smoothness score, which is part of the per-element
metrics dict. The user never sees a landing smoothness score.

Sibling tests in this file (the issue's contract):
  - Observable 1: NaN fps via direct call → int(NaN) crash.
  - Observable 2: NaN fps with longer post-landing window → same crash.
  - Observable 3: regression anchor — early-return path (phases.end <=
    landing+1) is fps-independent, must still return 1.0.
  - Regression: valid fps + valid phases + valid poses → sane smoothness.
  - Source check: `math.isfinite(fps)` guard is present in
    `compute_landing_smoothness` (root cause locked at the source).

Methodology: 3 observables (NaN fps via different paths) + 1 regression
(valid fps unchanged) + 1 source check (root cause locked at the source).
Matches the issue's fix contract: "After the fix, the observable tests
should flip to GREEN: NaN fps should raise a typed error, not a raw
`int(NaN)` ValueError."

Pure-Python + numpy: the function is a per-element compute. We feed
synthetic NaN fps to isolate the int(NaN) crash.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.analysis.element_defs import ElementDef
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase


def _analyzer() -> BiomechanicsAnalyzer:
    return BiomechanicsAnalyzer(
        ElementDef(
            name="test",
            name_ru="test",
            rotations=0,
            has_toe_pick=False,
            key_joints=[],
            ideal_metrics={},
        )
    )


# =========================================================================== #
# Observable 1: NaN fps CRASHES `compute_landing_smoothness` via
# `int(0.5 * NaN)`. The fix must prevent the uncaught int(NaN) crash.
# =========================================================================== #


def test_nan_fps_does_not_crash_with_int_nan_value_error_repro():
    """CORRECT behavior: `BiomechanicsAnalyzer.compute_landing_smoothness`
    with a NaN `fps` must NOT crash with an uncaught
    `ValueError: cannot convert float NaN to integer`. The function
    must either raise a clear typed error (e.g. ValueError with a
    domain message) or treat NaN as a degenerate case (return 1.0).

    RED now: `int(0.5 * NaN) = int(NaN) = ValueError` is uncaught at
    the window-frames calc. The observable contract is: the function
    must NOT raise the raw `cannot convert float NaN to integer`
    ValueError. After the fix: a `math.isfinite(fps)` guard prevents
    the int(NaN) call.
    """
    analyzer = _analyzer()
    poses = np.zeros((30, 17, 2), dtype=np.float32)
    phases = ElementPhase(name="test", start=0, takeoff=10, peak=15, landing=20, end=25)
    try:
        result = analyzer.compute_landing_smoothness(poses, phases, fps=float("nan"))
    except ValueError as ex:
        # The fix must prevent the raw int(NaN) ValueError. A typed
        # error with a domain message is acceptable (and preferred —
        # matches the issue's "raise a typed error, not a raw int(NaN)
        # ValueError" contract). We forbid the specific int(NaN) message.
        assert "cannot convert float NaN to integer" not in str(ex), (
            f"BUG (#1114): compute_landing_smoothness with NaN fps "
            f"crashed with the raw int(NaN) ValueError: {ex}. The fix "
            f"must add a `math.isfinite(fps)` guard before "
            f"`int(0.5 * fps)` to prevent the uncaught int(NaN) crash."
        )
        # Acceptable: a typed domain ValueError. Any other exception
        # type is not acceptable.
        return
    else:
        # Acceptable: graceful return (e.g. 1.0, the no-data default).
        # Must be a finite float in [0.0, 1.0].
        assert 0.0 <= result <= 1.0, (
            f"BUG (#1114): compute_landing_smoothness with NaN fps "
            f"returned {result}, expected a graceful degenerate-case "
            f"value in [0.0, 1.0] (e.g. 1.0) or a typed domain error."
        )


# =========================================================================== #
# Observable 2: NaN fps + longer post-landing window — same crash.
# =========================================================================== #


def test_nan_fps_long_poses_does_not_crash_repro():
    """CORRECT behavior: NaN fps with a longer post-landing window
    must NOT crash with the raw int(NaN) ValueError.

    RED now: same `int(0.5 * NaN) = int(NaN) = ValueError`.
    """
    analyzer = _analyzer()
    poses = np.zeros((100, 17, 2), dtype=np.float32)
    phases = ElementPhase(name="test", start=0, takeoff=10, peak=15, landing=20, end=90)
    try:
        result = analyzer.compute_landing_smoothness(poses, phases, fps=float("nan"))
    except ValueError as ex:
        assert "cannot convert float NaN to integer" not in str(ex), (
            f"BUG (#1114): compute_landing_smoothness with NaN fps + "
            f"long post-landing window crashed with the raw int(NaN) "
            f"ValueError: {ex}. The fix must add a `math.isfinite(fps)` "
            f"guard before `int(0.5 * fps)`."
        )
        return
    else:
        assert 0.0 <= result <= 1.0, (
            f"BUG (#1114): compute_landing_smoothness with NaN fps + "
            f"long poses returned {result}, expected graceful degenerate."
        )


# =========================================================================== #
# Observable 3: regression anchor — early-return path (phases.end ==
# landing+1) returns 1.0 BEFORE reaching the fps-dependent line. The
# function does NOT use fps in the early-return path. This confirms the
# crash is fps-specific AND that the early-return path is robust.
# =========================================================================== #


def test_nan_fps_early_return_path_returns_one_repro():
    """Regression anchor: `phases.end <= phases.landing + 1` triggers
    the early-return (returns 1.0). The function does NOT reach the
    window-frames calc with NaN fps in this case — confirming the
    crash is fps-specific AND that the early-return path is robust
    (it doesn't depend on fps).

    This PASSES on master (early return is fps-independent) and must
    keep passing after the fix.
    """
    analyzer = _analyzer()
    poses = np.zeros((30, 17, 2), dtype=np.float32)
    # end == landing+1 → early return 1.0
    phases = ElementPhase(name="test", start=0, takeoff=10, peak=15, landing=20, end=21)
    result = analyzer.compute_landing_smoothness(poses, phases, fps=float("nan"))
    assert result == 1.0, (
        f"BUG (regression): early-return with NaN fps returned {result}, expected 1.0."
    )


# =========================================================================== #
# Regression guard: valid fps + valid phases + valid poses must
# produce a sane smoothness score. The fix (NaN guard) must not
# change the typical case.
# =========================================================================== #


def test_valid_fps_regression_unchanged_repro():
    """Regression guard: valid fps + valid phases + valid poses
    must produce a sane smoothness score. The fix (NaN guard) must
    not change the typical case.

    This PASSES on master and must keep passing after the fix.
    """
    analyzer = _analyzer()
    poses = np.zeros((30, 17, 2), dtype=np.float32)
    phases = ElementPhase(name="test", start=0, takeoff=10, peak=15, landing=20, end=25)
    result = analyzer.compute_landing_smoothness(poses, phases, fps=30.0)
    # Should be a finite float in [0.0, 1.0].
    assert 0.0 <= result <= 1.0, f"BUG (regression): valid smoothness score {result} out of range."


# =========================================================================== #
# Source check: root cause locked — `math.isfinite(fps)` guard must be
# present in `compute_landing_smoothness`. RED now: the guard is
# absent → this test FAILS on master. After the fix: guard appears →
# PASS. This locks the fix at the source level (no test-suite-level
# regression if someone removes the guard).
# =========================================================================== #


def test_nan_fps_isfinite_guard_present_source_repro():
    """Source check: `BiomechanicsAnalyzer.compute_landing_smoothness`
    must contain a `math.isfinite(fps)` guard before the
    `int(0.5 * fps)` line. The guard prevents the uncaught
    `int(NaN) = ValueError` crash.

    RED now: the guard is absent → this test FAILS on master.
    After the fix: guard appears → PASS. Locks the root cause at
    the source level.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_landing_smoothness)
    assert "isfinite(fps)" in src, (
        "RED (#1114): `math.isfinite(fps)` guard is missing in "
        "compute_landing_smoothness — `int(0.5 * NaN)` crashes with "
        "ValueError. Add a `math.isfinite(fps)` guard (raise ValueError "
        "or early-return 1.0) before `window_frames = int(0.5 * fps)`."
    )
