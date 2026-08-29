"""Repro tests — compute_landing_quality crashes on NaN knee keypoint (#863).

``compute_landing_quality`` (metrics.py:822) calls ``angle_3pt`` on the
landing-frame knee keypoints and returns ``min(left_angle, right_angle)``.
``angle_3pt`` delegates to the ``@njit(fastmath=True)`` ``angle_3pt_rad``,
whose division ``np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) +
1e-8)`` does NOT propagate NaN under fastmath — when any knee keypoint is NaN
(the frequent free-leg occlusion case), Numba raises ``ZeroDivisionError``
that propagates through ``analyze()`` and kills the whole session, not just
the landing metric.

Fix (#863): NaN-guard before the jitted division (return ``np.nan``) so the
crash becomes a NaN value, and ``compute_landing_quality`` uses ``np.nanmin``
(not Python ``min`` — ``min(nan, val) = nan`` per #454 asymmetry) to take the
valid leg's angle when one is NaN.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _analyzer() -> BiomechanicsAnalyzer:
    return BiomechanicsAnalyzer(get_element_def("waltz_jump"))


def _pose_with_nan_knee(nan_side: str) -> np.ndarray:
    """10 frames, waltz_jump; landing frame 7; one knee side NaN at landing.

    The valid knee forms ~90 deg; the NaN side must not crash analyze().
    """
    n = 10
    poses = np.full((n, 17, 2), 0.5, dtype=np.float32)
    # Valid ~90 deg knee on both sides for all frames.
    poses[:, H36Key.LHIP, :] = [0.0, 0.5]
    poses[:, H36Key.LKNEE, :] = [0.0, 0.0]
    poses[:, H36Key.LFOOT, :] = [0.5, 0.0]
    poses[:, H36Key.RHIP, :] = [0.5, 0.5]
    poses[:, H36Key.RKNEE, :] = [0.5, 0.0]
    poses[:, H36Key.RFOOT, :] = [1.0, 0.0]
    # NaN the requested knee side at the landing frame (frame 7).
    if nan_side == "right":
        poses[7, H36Key.RKNEE, :] = np.nan
    elif nan_side == "left":
        poses[7, H36Key.LKNEE, :] = np.nan
    return poses


def test_nan_right_knee_does_not_crash_analyze_repro():
    """#863: NaN right knee on landing frame must not crash analyze()."""
    analyzer = _analyzer()
    poses = _pose_with_nan_knee("right")
    phases = ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=5, landing=7, end=10)
    results = analyzer.analyze(poses, phases, fps=30.0)
    # analyze returned metrics (did not raise) — landing_knee_angle present.
    names = {r.name for r in results}
    assert "landing_knee_angle" in names, (
        f"#863 RED: analyze() raised ZeroDivisionError on NaN right knee — "
        f"session killed. Expected landing_knee_angle metric, got {names}."
    )


def test_nan_left_knee_does_not_crash_analyze_repro():
    """#863: NaN left knee on landing frame must not crash analyze() (symmetric)."""
    analyzer = _analyzer()
    poses = _pose_with_nan_knee("left")
    phases = ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=5, landing=7, end=10)
    results = analyzer.analyze(poses, phases, fps=30.0)
    names = {r.name for r in results}
    assert "landing_knee_angle" in names, (
        f"#863 RED: analyze() raised ZeroDivisionError on NaN left knee — "
        f"session killed (#454 asymmetry: this side was missed). Expected "
        f"landing_knee_angle metric, got {names}."
    )


def test_valid_landing_returns_knee_angle_repro():
    """#863 regression guard: all-valid keypoints → landing_knee_angle ~90 deg."""
    analyzer = _analyzer()
    poses = _pose_with_nan_knee("none")
    phases = ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=5, landing=7, end=10)
    results = analyzer.analyze(poses, phases, fps=30.0)
    angle = next(r for r in results if r.name == "landing_knee_angle")
    assert 80.0 < angle.value < 100.0, (
        f"#863: all-valid landing_knee_angle={angle.value} — must be ~90 deg."
    )


def test_landing_quality_nanmin_guard_source_repro():
    """#863 GREEN source check: compute_landing_quality reduces with np.nanmin
    (not Python min — #454 NaN asymmetry) so a NaN leg does not propagate."""
    src = inspect.getsource(BiomechanicsAnalyzer.compute_landing_quality)
    assert "np.nanmin" in src, (
        "#863: compute_landing_quality must use np.nanmin to ignore a NaN leg's "
        "angle — Python min(nan, val) = nan (#454 asymmetry)."
    )
    assert "min(left_angle, right_angle)" not in src, (
        "#863: unguarded Python min(left_angle, right_angle) removed — it crashes "
        "(angle_3pt ZeroDivisionError on NaN) or propagates NaN asymmetry."
    )
    # angle_3pt wrapper guards NaN before the jitted fastmath division.
    from src.utils import geometry

    rad_src = inspect.getsource(geometry.angle_3pt)
    assert "np.isfinite" in rad_src, (
        "#863: angle_3pt must guard NaN before the @njit(fastmath=True) core — "
        "NaN/NaN under fastmath raises ZeroDivisionError instead of propagating NaN."
    )
