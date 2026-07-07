"""RED repro — `BiomechanicsAnalyzer._analyze_step` `avg_knee_angle` uses
unguarded `float(np.mean(knee_angles))` (metrics.py:478), which silently
propagates NaN to `MetricResult.value` when any frame of `knee_angles` is
NaN.

Root cause (same NumPy contract as #1275 / #962):

    np.mean([170, NaN, 175, 172]) = NaN
    float(NaN) = NaN
    MetricResult(name="knee_angle", value=NaN, ...)

When the user looks at the result, they see `knee_angle: nan` with
`is_good=False` and no diagnostic. The recommender cannot classify "bent
knees" vs "straight knees" because the value is NaN. The fix idiom is the
same as the other 3 peak sites in `_analyze_step`: filter to
`np.isfinite(knee_angles)` and fall back to a sentinel when ALL frames
are NaN. This file is the repro suite for the avg_knee_angle site (tranche
MK of the unguarded-mean block). The other 5 sites in the block (avg_lean,
edge_change, peak_se, peak_ib, max_spiral) are covered by separate tranches.

The standing-pose fixture from `SyntheticPoseFactory.make_standing_pose`
yields a knee angle near 180 degrees for every frame in clean conditions.
We inject NaN by corrupting the LHIP keypoint — that propagates through
`compute_knee_angle_series` (#868 producer guard) so the series returned
to `_analyze_step` contains exactly one NaN. The unguarded `np.mean` then
returns NaN. After the fix, `avg_knee_angle` must be a finite number close
to 180.

Closes #1312.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from tests.conftest import SyntheticPoseFactory

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _step_phases(n: int = 6) -> ElementPhase:
    return ElementPhase(
        name="three_turn",
        start=0,
        takeoff=0,
        peak=max(1, n // 2),
        landing=max(1, n - 1),
        end=n,
    )


def _get_step_metric(metrics, name: str):
    for m in metrics:
        if m.name == name:
            return m
    raise AssertionError(f"metric {name!r} not in {[m.name for m in metrics]}")


def _poison_left_leg(poses: np.ndarray, frames: tuple[int, ...]) -> np.ndarray:
    """Set LHIP, LKNEE, LFOOT to NaN on the given frames (occluded leg)."""
    out = poses.copy()
    for f in frames:
        out[f, H36Key.LHIP] = np.nan
        out[f, H36Key.LKNEE] = np.nan
        out[f, H36Key.LFOOT] = np.nan
    return out


# --------------------------------------------------------------------------- #
# Observable 1: a single NaN in the knee_angles series poisons the mean.
# Drive the actual _analyze_step code path and assert the MetricResult is
# finite.
# --------------------------------------------------------------------------- #


def test_avg_knee_angle_single_nan_metricresult_finite_repro():
    """CORRECT: MetricResult(name="knee_angle").value is FINITE for 1-of-6 NaN input.

    End-to-end: poison 1 frame of a 6-frame standing pose (occluded LHIP
    slipped past the #868 producer guard at the consumer level) and run
    `_analyze_step`. The "knee_angle" metric must carry a finite value
    close to 180 deg. NaN here means the recommender cannot classify
    "bent vs straight" and the user sees a silent false-bad rating.
    """
    poses = _poison_left_leg(SyntheticPoseFactory.make_standing_pose(n_frames=6), (2,))
    analyzer = BiomechanicsAnalyzer(get_element_def("three_turn"))
    metrics = analyzer.analyze(poses, _step_phases(n=6), fps=30.0)
    knee_metric = _get_step_metric(metrics, "knee_angle")

    assert math.isfinite(knee_metric.value), (
        f"BUG: MetricResult(name='knee_angle').value = {knee_metric.value} "
        f"(NaN) for a 1-of-6 NaN input. The unguarded "
        f"`float(np.mean(knee_angles))` in _analyze_step silently propagates "
        f"NaN to the user. Fix: filter np.isfinite before np.mean, fallback "
        f"0.0 when all-NaN. (#1312)"
    )
    assert knee_metric.value > 170.0, (
        f"BUG: knee_angle expected near 180 (standing, 1 frame poisoned), "
        f"got {knee_metric.value:.1f}"
    )


# --------------------------------------------------------------------------- #
# Observable 2: many NaN frames still produce a finite knee_angle.
# --------------------------------------------------------------------------- #


def test_avg_knee_angle_multi_nan_metricresult_finite_repro():
    """CORRECT: 2-of-6 NaN frames still yield a finite knee_angle.

    Same end-to-end flow as observable 1 but with more occluded frames.
    The mean of the remaining 4 finite frames should still be near 180
    and MUST be finite.
    """
    poses = _poison_left_leg(SyntheticPoseFactory.make_standing_pose(n_frames=6), (1, 4))
    analyzer = BiomechanicsAnalyzer(get_element_def("three_turn"))
    metrics = analyzer.analyze(poses, _step_phases(n=6), fps=30.0)
    knee_metric = _get_step_metric(metrics, "knee_angle")

    assert math.isfinite(knee_metric.value), (
        f"BUG: MetricResult(name='knee_angle').value = {knee_metric.value} "
        f"(NaN) for a 2-of-6 NaN input. (#1312)"
    )


# --------------------------------------------------------------------------- #
# Observable 3: all-NaN knee_angles series must produce a 0.0 sentinel
# (worst case — every frame occluded).
# --------------------------------------------------------------------------- #


def test_avg_knee_angle_all_nan_metricresult_zero_sentinel_repro():
    """CORRECT: all-NaN knee_angles series must produce a 0.0 sentinel.

    Worst case: every frame has an occluded left leg. `np.mean` of an
    all-NaN array is NaN; `float(NaN) = NaN`; MetricResult.value = NaN
    breaks JSON serialization. Sentinel 0.0 matches the convention used
    at the other _analyze_step peak sites (#962, #1275).
    """
    poses = _poison_left_leg(
        SyntheticPoseFactory.make_standing_pose(n_frames=6),
        tuple(range(6)),  # all 6 frames NaN
    )
    analyzer = BiomechanicsAnalyzer(get_element_def("three_turn"))
    metrics = analyzer.analyze(poses, _step_phases(n=6), fps=30.0)
    knee_metric = _get_step_metric(metrics, "knee_angle")

    assert math.isfinite(knee_metric.value), (
        f"BUG: MetricResult(name='knee_angle').value = {knee_metric.value} "
        f"(NaN) for an all-NaN series. Fix: filter np.isfinite before "
        f"np.mean, fallback 0.0 when empty. (#1312)"
    )
    assert knee_metric.value == 0.0, (
        f"BUG: all-NaN knee_angles series produced {knee_metric.value}, "
        f"expected 0.0 sentinel. (#1312)"
    )


# --------------------------------------------------------------------------- #
# Observable 4: regression — clean all-finite input must produce the same
# finite mean under the fix.
# --------------------------------------------------------------------------- #


def test_avg_knee_angle_clean_series_finite_regression_repro():
    """CORRECT: clean standing pose (no NaN) must yield a finite knee_angle.

    Regression: the fix must not break the all-finite path. A standing
    pose has the left leg fully straight, so the angle is near 180 deg.
    """
    poses = SyntheticPoseFactory.make_standing_pose(n_frames=6)
    analyzer = BiomechanicsAnalyzer(get_element_def("three_turn"))
    metrics = analyzer.analyze(poses, _step_phases(n=6), fps=30.0)
    knee_metric = _get_step_metric(metrics, "knee_angle")

    assert math.isfinite(knee_metric.value), (
        f"BUG: clean standing pose produced knee_angle = "
        f"{knee_metric.value} (NaN). The fix must be identity on "
        f"all-finite input. (#1312)"
    )
    assert knee_metric.value > 170.0, (
        f"BUG: clean standing pose expected knee_angle near 180, got "
        f"{knee_metric.value:.1f}. (#1312)"
    )


# --------------------------------------------------------------------------- #
# Source-locking guard: metrics.py must not use unguarded
# `float(np.mean(knee_angles))` for the avg_knee_angle site.
# --------------------------------------------------------------------------- #


def test_avg_knee_angle_no_unguarded_float_np_mean_repro():
    """Lock: the avg_knee_angle site in _analyze_step must not use unguarded
    `float(np.mean(knee_angles))`.

    The bare `np.mean` silently propagates NaN. After the fix the line uses
    `np.isfinite(knee_angles)` to filter the series (with a 0.0 fallback
    when the filtered series is empty) before the mean, mirroring the
    nanmax+isfinite idiom used at the three peak sites (#962, #1275).
    """
    src = Path("ml/src/analysis/metrics.py").read_text()
    needle = 'name="knee_angle"'
    idx = src.find(needle)
    assert idx > 0, "test fixture broken: 'knee_angle' metric name not found"
    # Look back ~600 chars for the mean computation line.
    window = src[max(0, idx - 600) : idx]
    # The unguarded `float(np.mean(knee_angles))` pattern must NOT appear
    # in this window. A guarded pattern that filters to isfinite first is
    # fine.
    assert "float(np.mean(knee_angles))" not in window, (
        f"BUG: unguarded `float(np.mean(knee_angles))` still present near "
        f"{needle!r} in _analyze_step (metrics.py). NaN-contaminated "
        f"knee_angles silently propagates NaN to MetricResult.value. "
        f"Fix: filter np.isfinite(knee_angles) before np.mean, fallback "
        f"0.0 when all-NaN. (#1312)"
    )
