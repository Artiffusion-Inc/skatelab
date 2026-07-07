"""Repro for issue #1271: compute_approach_torso_lean silently returns NaN.

When the approach-phase poses contain any NaN keypoint, the underlying
compute_trunk_lean series contains NaN; np.mean(NaN-series) propagates NaN
and float(NaN) is silently returned. No error, no log.

The function is also documented as `compute_approach_trunk_lean` in the
issue title but the actual implementation is `compute_approach_torso_lean`
in ml/src/analysis/metrics.py.
"""

import math

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _make_lean_poses(n_frames: int = 20) -> np.ndarray:
    """Forward-leaning pose sequence (all finite, non-NaN)."""
    poses = np.zeros((n_frames, 17, 2), dtype=np.float32)
    poses[:, H36Key.LSHOULDER, 0] = 0.3
    poses[:, H36Key.RSHOULDER, 0] = 0.3
    poses[:, H36Key.LHIP, 0] = 0.0
    poses[:, H36Key.RHIP, 0] = 0.0
    poses[:, H36Key.LSHOULDER, 1] = -0.5
    poses[:, H36Key.RSHOULDER, 1] = -0.5
    poses[:, H36Key.LHIP, 1] = 0.0
    poses[:, H36Key.RHIP, 1] = 0.0
    return poses


def _analyzer() -> BiomechanicsAnalyzer:
    return BiomechanicsAnalyzer(get_element_def("waltz_jump"))


def test_returns_finite_when_one_pose_has_nan_keypoint():
    """A single NaN keypoint in the approach slice must not leak NaN out."""
    analyzer = _analyzer()
    poses = _make_lean_poses(20)
    # Corrupt one keypoint on one approach frame
    poses[5, H36Key.LSHOULDER, 0] = np.nan

    phases = ElementPhase(name="waltz_jump", start=0, takeoff=10, peak=12, landing=15, end=19)
    lean = analyzer.compute_approach_torso_lean(poses, phases)

    assert isinstance(lean, float)
    assert math.isfinite(lean), f"expected finite float, got {lean!r}"


def test_returns_finite_when_all_approach_poses_are_nan():
    """All-NaN approach slice must not yield NaN (no finite data -> guard)."""
    analyzer = _analyzer()
    poses = _make_lean_poses(20)
    poses[:11, H36Key.LSHOULDER, 0] = np.nan
    poses[:11, H36Key.RSHOULDER, 0] = np.nan
    poses[:11, H36Key.LHIP, 1] = np.nan
    poses[:11, H36Key.RHIP, 1] = np.nan

    phases = ElementPhase(name="waltz_jump", start=0, takeoff=10, peak=12, landing=15, end=19)
    lean = analyzer.compute_approach_torso_lean(poses, phases)

    assert isinstance(lean, float)
    assert math.isfinite(lean), f"expected finite float, got {lean!r}"


def test_nan_in_chain_via_compute_trunk_lean_does_not_propagate():
    """NaN that enters via the underlying trunk_lean series must be guarded."""
    analyzer = _analyzer()
    poses = _make_lean_poses(20)
    # Corrupt a keypoint that feed into compute_trunk_lean for the whole
    # approach window — this is the silent-NaN path the issue describes.
    poses[:11, H36Key.LSHOULDER, 0] = np.nan

    phases = ElementPhase(name="waltz_jump", start=0, takeoff=10, peak=12, landing=15, end=19)
    lean = analyzer.compute_approach_torso_lean(poses, phases)

    assert math.isfinite(lean), f"NaN leaked from compute_trunk_lean chain: {lean!r}"


def test_clean_approach_still_returns_forward_lean():
    """Regression: finite-input path is unchanged (still returns positive lean)."""
    analyzer = _analyzer()
    poses = _make_lean_poses(20)
    phases = ElementPhase(name="waltz_jump", start=0, takeoff=10, peak=12, landing=15, end=19)
    lean = analyzer.compute_approach_torso_lean(poses, phases)
    assert math.isfinite(lean)
    assert lean > 0, f"expected forward lean > 0, got {lean}"


def test_source_site_uses_nan_safe_mean():
    """Source-level guard: the implementation must not call np.mean on the
    trunk_lean series without a NaN-safe variant (np.nanmean or explicit
    finite-filter)."""
    import inspect

    import ml.src.analysis.metrics as metrics_mod

    src = inspect.getsource(metrics_mod.BiomechanicsAnalyzer.compute_approach_torso_lean)
    # If a bare np.mean(trunk_lean) path exists, the fix has not been applied.
    assert "np.nanmean" in src or "isfinite" in src or "~np.isnan" in src, (
        "compute_approach_torso_lean must guard against NaN propagation"
    )
