"""Repro tests — Pose3DNormalizer.get_body_height NaN-unsafe Python min() (#861).

``get_body_height`` (normalizer_3d.py:86) used ``min(left_foot_y, right_foot_y)``.
Python ``min`` is NaN-unsafe and arg-order-dependent: ``min(nan, val) = nan``
(frame silently dropped via ``body_height > 0.1`` → False) while ``min(val, nan)
= val`` (frame kept). A frame with one occluded foot is dropped or kept based on
WHICH foot is NaN, biasing the average toward the tracker's failure side.

Fix (#861, #454 sibling contract): ``np.fmin`` (NaN-safe, falls back to the
finite operand) + ``np.isfinite`` guard so one-NaN-foot frames are kept and
both-NaN frames still drop.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.pose_3d.normalizer_3d import Pose3DNormalizer
from src.types import H36Key


def _poses(head_y: float, foot_y: float, *, lfoot_nan: bool, rfoot_nan: bool) -> np.ndarray:
    """4 frames, HEAD=head_y, LFOOT/RFOOT=foot_y (NaN per flags)."""
    poses = np.full((4, 17, 3), 0.0, dtype=np.float32)
    poses[:, H36Key.HEAD, 1] = head_y
    poses[:, H36Key.LFOOT, 1] = np.nan if lfoot_nan else foot_y
    poses[:, H36Key.RFOOT, 1] = np.nan if rfoot_nan else foot_y
    return poses


def test_left_nan_foot_frame_not_dropped_repro():
    """#861: a frame with NaN LFOOT, valid RFOOT must be kept (real body_height)."""
    norm = Pose3DNormalizer()
    poses = _poses(head_y=2.0, foot_y=0.2, lfoot_nan=True, rfoot_nan=False)
    height = norm.get_body_height(poses)
    # head_y - foot_y = 1.8; the NaN LFOOT must not drop the frame.
    assert abs(height - 1.8) < 0.05, (
        f"#861 RED: get_body_height={height} — min(nan, 0.2)=nan dropped the "
        "LFOOT-NaN frames (asymmetric: RFOOT-NaN frames are kept). The average "
        "biases by which foot the tracker lost, not by anatomy. Use np.fmin."
    )


def test_right_nan_foot_frame_not_dropped_repro():
    """#861: a frame with NaN RFOOT, valid LFOOT must be kept (symmetric)."""
    norm = Pose3DNormalizer()
    poses = _poses(head_y=2.0, foot_y=0.2, lfoot_nan=False, rfoot_nan=True)
    height = norm.get_body_height(poses)
    assert abs(height - 1.8) < 0.05, (
        f"#861 RED: get_body_height={height} — RFOOT-NaN frame kept by Python "
        "min(val, nan)=val but LFOOT-NaN dropped. Must be symmetric via np.fmin."
    )


def test_both_nan_feet_frame_dropped_repro():
    """#861 regression guard: both feet NaN → frame dropped → default 1.7."""
    norm = Pose3DNormalizer()
    poses = _poses(head_y=2.0, foot_y=0.2, lfoot_nan=True, rfoot_nan=True)
    height = norm.get_body_height(poses)
    assert height == 1.7, (
        f"#861: both-NaN-feet get_body_height={height} — must fall back to the "
        "1.7 default (np.isfinite(nan) False drops the frame)."
    )


def test_get_body_height_uses_fmin_not_python_min_source_repro():
    """#861 GREEN source check: get_body_height uses np.fmin (NaN-safe), not
    Python min — matches the #454 contract on sibling normalize/calculate."""
    src = inspect.getsource(Pose3DNormalizer.get_body_height)
    assert "np.fmin" in src, (
        "#861: get_body_height must use np.fmin (NaN-safe) per the #454 contract "
        "shared with normalize() and calculate_body_heights() in this file."
    )
    # Python ``min`` (not ``np.fmin``) is the NaN-unsafe call. Match the bare
    # ``min(left_foot_y`` form, not ``np.fmin(left_foot_y`` (which contains the
    # ``min(left_foot_y`` substring — fmin shadows it).
    assert "= min(left_foot_y" not in src, (
        "#861: NaN-unsafe Python min(left_foot_y, right_foot_y) removed — "
        "min(nan,val)=nan silently drops LFOOT-NaN frames asymmetrically."
    )
