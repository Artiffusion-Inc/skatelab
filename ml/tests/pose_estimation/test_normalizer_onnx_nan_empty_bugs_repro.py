"""Regression test: normalizer must not poison frame output when spine is NaN.

Issue #621: ml/src/pose_estimation/normalizer.py lines 72 and 113 compute
`scale = 1.0 if spine_length < 1e-6 else ... / spine_length`. When
spine_length is NaN (NaN comparison returns False), the else branch
runs: 0.4 / NaN = NaN. Entire frame's 17 joints become NaN.
"""

import numpy as np
import pytest

from src.pose_estimation.normalizer import PoseNormalizer
from src.types import H36Key


def _valid_3d_frame() -> np.ndarray:
    """Return a valid (17, 3) H3.6M-like frame with sane hip + thorax."""
    rng = np.random.default_rng(0)
    frame = rng.uniform(0, 1, size=(17, 3)).astype(np.float32)
    frame[H36Key.HIP_CENTER] = [0.5, 0.9, 0.5]
    frame[H36Key.THORAX] = [0.5, 0.7, 0.5]  # 0.2 above hip
    return frame


def test_normalize_2d_with_nan_thorax_does_not_poison_frame():
    """Single NaN keypoint must not corrupt the OTHER 16 joints of the frame."""
    normalizer = PoseNormalizer()
    poses = _valid_3d_frame()[None]  # (1, 17, 3) — normalize() takes 3D
    poses[0, H36Key.THORAX] = [np.nan, np.nan, np.nan]

    out = normalizer.normalize(poses)

    # The frame's other 16 joints should be finite; only thorax stays NaN
    frame = out[0]
    nan_mask = np.isnan(frame)
    # Exactly one row (thorax) should be NaN — the rest must be finite
    nan_rows = np.where(np.any(nan_mask, axis=1))[0]
    assert list(nan_rows) == [H36Key.THORAX], (
        f"normalize() poisoned more than the thorax row with NaN. NaN rows: {list(nan_rows)}"
    )


def test_normalize_2d_with_nan_hip_does_not_poison_frame():
    """NaN hip_center poisons centering (all rows shift by NaN). Acceptable.

    Without valid hip_center we cannot root-center, so the entire frame
    is unrecoverable. The fix scope is: NaN spine (thorax) must not
    poison unrelated frames. With NaN hip, we expect all-NaN output
    because centering is undefined.
    """
    normalizer = PoseNormalizer()
    poses = _valid_3d_frame()[None]
    poses[0, H36Key.HIP_CENTER] = [np.nan, np.nan, np.nan]

    # Document current behavior: with NaN hip, the whole frame is NaN.
    # This is a fundamental limitation of root-centering; no scale guard
    # can rescue it. Test that this is at least consistent (all-NaN).
    out = normalizer.normalize(poses)
    assert np.all(np.isnan(out[0])), (
        "with NaN hip_center, output should be all-NaN (root-centering undefined)"
    )


def test_normalize_3d_with_nan_thorax_does_not_poison_frame():
    """3D normalizer must also guard against NaN spine."""
    normalizer = PoseNormalizer()
    poses = _valid_3d_frame()[None]

    poses[0, H36Key.THORAX] = [np.nan, np.nan, np.nan]
    out = normalizer.normalize_3d(poses)
    nan_mask = np.isnan(out[0])
    nan_rows = np.where(np.any(nan_mask, axis=1))[0]
    assert list(nan_rows) == [H36Key.THORAX], (
        f"normalize_3d() poisoned more than thorax. NaN rows: {list(nan_rows)}"
    )


def test_normalize_2d_with_zero_spine_uses_unit_scale():
    """Sanity check: zero spine (degenerate) should also fall back to scale=1.0."""
    normalizer = PoseNormalizer()
    poses = _valid_3d_frame()[None]
    # Make thorax == hip so spine_length = 0
    poses[0, H36Key.THORAX] = poses[0, H36Key.HIP_CENTER]

    out = normalizer.normalize(poses)
    assert np.all(np.isfinite(out[0])), "normalize() should handle zero spine"
