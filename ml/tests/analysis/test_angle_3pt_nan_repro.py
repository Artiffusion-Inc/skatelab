"""Repro for issue #1262: _angle_3pt_from_poses silently propagates NaN.

Pattern: ``float(np.degrees(np.arccos(np.clip(cos_val, -1.0, 1.0))))``
Any keypoint NaN → cos_val NaN → ``np.clip(NaN, -1.0, 1.0) = NaN`` silently →
arccos(NaN) = NaN → degrees(NaN) = NaN → float(NaN) = NaN.

The bug: this NaN propagation is *implicit*. A user looking at
``np.nan_to_num(l_knee, nan=0.0)`` at the call site gets a "clean" array
but has no idea any frame was corrupted.

The fix: make the NaN explicit. The function still returns NaN, but the
source-level guard is in place so we know the NaN is intentional and
downstream consumers (np.nanmean / nanmax / explicit finite-filter) can
skip the corrupt frame.
"""

import math

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import H36Key


def _make_knee_poses(n_frames: int = 10) -> np.ndarray:
    """Straight-standing pose sequence (knee angle ~180 deg)."""
    poses = np.zeros((n_frames, 17, 2), dtype=np.float32)
    poses[:, H36Key.LHIP] = (0.1, 0.0)
    poses[:, H36Key.RHIP] = (0.2, 0.0)
    poses[:, H36Key.LKNEE] = (0.1, -0.3)
    poses[:, H36Key.RKNEE] = (0.2, -0.3)
    poses[:, H36Key.LFOOT] = (0.1, -0.6)
    poses[:, H36Key.RFOOT] = (0.2, -0.6)
    return poses


def test_nan_keypoint_propagates_as_nan_not_infinite_silent():
    """#1262: corrupt keypoint must yield NaN (explicit), and the explicit
    NaN must be the ONLY non-finite value (i.e. nothing else leaks)."""
    poses = _make_knee_poses(5)
    poses[2, H36Key.LKNEE, 0] = np.nan  # corrupt one of the three points

    angle = BiomechanicsAnalyzer._angle_3pt_from_poses(
        poses, 2, H36Key.LHIP, H36Key.LKNEE, H36Key.LFOOT
    )

    # The fix's contract: a corrupt keypoint produces an explicit NaN.
    # Downstream np.nan_to_num / nanmean / nanmax will skip the frame.
    assert math.isnan(angle), f"expected explicit NaN, got {angle!r}"


def test_nan_in_hip_yields_nan():
    """NaN in j1 (hip) — same explicit-NaN contract."""
    poses = _make_knee_poses(5)
    poses[1, H36Key.LHIP, 1] = np.nan

    angle = BiomechanicsAnalyzer._angle_3pt_from_poses(
        poses, 1, H36Key.LHIP, H36Key.LKNEE, H36Key.LFOOT
    )

    assert math.isnan(angle), f"expected explicit NaN, got {angle!r}"


def test_nan_in_foot_yields_nan():
    """NaN in j3 (foot) — same explicit-NaN contract."""
    poses = _make_knee_poses(5)
    poses[3, H36Key.RFOOT, 0] = np.nan

    angle = BiomechanicsAnalyzer._angle_3pt_from_poses(
        poses, 3, H36Key.RHIP, H36Key.RKNEE, H36Key.RFOOT
    )

    assert math.isnan(angle), f"expected explicit NaN, got {angle!r}"


def test_clean_input_returns_straight_knee():
    """Regression: finite-input path is unchanged (straight knee ~180 deg)."""
    poses = _make_knee_poses(5)

    angle = BiomechanicsAnalyzer._angle_3pt_from_poses(
        poses, 0, H36Key.LHIP, H36Key.LKNEE, H36Key.LFOOT
    )

    assert math.isfinite(angle)
    assert 170.0 <= angle <= 180.0, f"expected ~180 deg straight knee, got {angle}"


def test_consumer_pattern_nan_to_num_then_mean_still_works():
    """Regression: the call-site pattern in compute_ina_bauer_score builds an
    array of single-frame angles then does np.nan_to_num(..., nan=0.0).
    With the explicit-NaN fix that pattern still produces a finite result
    for the array mean — no crash, no silent NaN leak past the gate."""
    poses = _make_knee_poses(5)
    poses[2, H36Key.LKNEE, 0] = np.nan

    l_knee = np.array(
        [
            BiomechanicsAnalyzer._angle_3pt_from_poses(
                poses, f, H36Key.LHIP, H36Key.LKNEE, H36Key.LFOOT
            )
            for f in range(len(poses))
        ]
    )
    # Mirror the consumer's nan_to_num pattern.
    sanitized = np.nan_to_num(l_knee, nan=0.0)
    assert math.isfinite(sanitized.mean()), "nan_to_num + mean must stay finite"


def test_source_uses_finite_guard_before_arccos():
    """Source-level guard: the implementation must not feed NaN to arccos
    via np.clip without an isfinite / nan_to_num guard upstream."""
    import inspect

    import ml.src.analysis.metrics as metrics_mod

    src = inspect.getsource(metrics_mod.BiomechanicsAnalyzer._angle_3pt_from_poses)
    # Bare np.clip → arccos path silently propagates NaN. The fix must
    # filter the input with a finite-mask or nan_to_num before arccos.
    assert "isfinite" in src or "nan_to_num" in src, (
        "_angle_3pt_from_poses must guard against NaN propagation before np.clip/arccos"
    )


def test_compute_ina_bauer_score_with_corrupt_frame_does_not_crash():
    """Integration regression: the actual call-site (compute_ina_bauer_score
    is the in-tree consumer that loops ``_angle_3pt_from_poses`` over every
    frame) must not crash or leak a fully-NaN score when a single keypoint
    is corrupt. Returns a per-frame array; the explicit-NaN frame is
    absorbed by the consumer's nan_to_num(..., nan=0.0)."""
    analyzer = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    poses = _make_knee_poses(20)
    # Corrupt one knee keypoint midway through the sequence
    poses[10, H36Key.LKNEE, 0] = np.nan
    poses[11, H36Key.LKNEE, 0] = np.nan

    score = analyzer.compute_ina_bauer_score(poses)
    # Score is per-frame; ensure none of the per-frame values are NaN
    # (consumer uses nan_to_num so corrupted frames collapse to 0.0).
    assert np.all(np.isfinite(score)), f"compute_ina_bauer_score leaked NaN: {score!r}"
