"""RED repro for #1039: normalize_poses np.where NaN-spine bypass.

One occluded spine-defining keypoint (LSHOULDER or LHIP — default
spine_indices) NaN-poisons the ENTIRE (17,2) frame via the
`np.where(spine_length < 1e-6, 1.0, target/spine_length)` guard which is
NaN-blind (`NaN < 1e-6` = False → second branch `target/NaN` = NaN).
"""

import inspect

import numpy as np

from src.types import H36Key
from src.utils.geometry import normalize_poses


def _raw_poses(n: int = 5) -> np.ndarray:
    """All-finite (n, 17, 3) H3.6M poses with a non-degenerate spine."""
    rng = np.random.default_rng(0)
    raw = rng.uniform(0.1, 0.9, size=(n, 17, 3)).astype(np.float32)
    # Ensure hips and shoulders define a real spine (no degeneracy).
    raw[:, H36Key.LHIP, :2] = [0.5, 0.5]
    raw[:, H36Key.RHIP, :2] = [0.55, 0.5]
    raw[:, H36Key.LSHOULDER, :2] = [0.5, 0.2]
    raw[:, H36Key.RSHOULDER, :2] = [0.55, 0.2]
    raw[:, :, 2] = 1.0  # all keypoints confident
    return raw


def test_nan_lshoulder_does_not_poison_whole_frame():
    """NaN LSHOULDER on frame 2 must NOT NaN-poison the other 16 joints.

    The NaN shoulder joint itself may remain NaN (it WAS NaN), but the
    16 finite joints must not be multiplied by a NaN scale.
    """
    raw = _raw_poses()
    raw[2, H36Key.LSHOULDER] = [np.nan, np.nan, 1.0]

    res = normalize_poses(raw)

    # Frame 2 must NOT be all-NaN. The 16 finite joints must stay finite.
    finite_count = np.sum(np.isfinite(res[2]))
    assert finite_count > 0, (
        f"Frame 2 fully NaN-poisoned ({finite_count}/34 finite). "
        "One NaN spine keypoint poisoned the whole frame (#1039)."
    )
    # Stronger: at least the 16 non-shoulder joints must be finite.
    assert finite_count >= 32, f"Frame 2 mostly NaN-poisoned ({finite_count}/34 finite)."


def test_nan_lhip_does_not_poison_whole_frame():
    """NaN LHIP (other default spine joint) must NOT poison the whole frame."""
    raw = _raw_poses()
    raw[2, H36Key.LHIP] = [np.nan, np.nan, 1.0]

    res = normalize_poses(raw)

    finite_count = np.sum(np.isfinite(res[2]))
    assert finite_count >= 32, f"Frame 2 NaN-poisoned by NaN LHIP ({finite_count}/34 finite)."


def test_all_finite_frame_unchanged_regression():
    """All-finite input must remain finite (regression)."""
    raw = _raw_poses()
    res = normalize_poses(raw)
    assert np.all(np.isfinite(res)), "All-finite input produced non-finite output"
    assert res.shape == (5, 17, 2)


def test_zero_spine_fallback_scale_one_regression():
    """Degenerate pose with shoulder==hip → scale=1.0 fallback preserved."""
    raw = _raw_poses(n=2)
    # Frame 1: shoulder == hip → spine_length 0 → existing guard → scale 1.0.
    raw[1, H36Key.LSHOULDER, :2] = raw[1, H36Key.LHIP, :2]
    raw[1, H36Key.RSHOULDER, :2] = raw[1, H36Key.RHIP, :2]

    res = normalize_poses(raw)

    # Frame 1 must be finite (scale=1.0 fallback, not NaN/inf).
    assert np.all(np.isfinite(res[1])), "Zero-spine fallback produced non-finite"


def test_source_has_isfinite_guard():
    """Root-cause lock: normalize_poses source must guard isfinite on spine_length."""
    src = inspect.getsource(normalize_poses)
    assert "isfinite" in src, (
        "normalize_poses missing np.isfinite guard on spine_length — "
        "np.where(spine_length < 1e-6, ...) is NaN-blind (#1039)."
    )
