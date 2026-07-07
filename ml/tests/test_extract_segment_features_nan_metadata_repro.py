"""Repro for #922: ElementSegmenter._extract_segment_features leaks NaN into
segment metadata features (rotation_speed_max/mean, motion_energy_mean/max/std)
when any keypoint is NaN, causing silent misclassification in _classify_by_rules
(`NaN > 200` = False → jump branch skipped → "unknown").

Contract: _extract_segment_features must return ONLY finite floats for the
metadata feature keys (rotation_speed_max/mean, motion_energy_mean/max/std)
for any input pose array, including ones containing NaN keypoints. Mirrors
the #979 extract_segment_features nan_to_num-at-entry guard pattern.
"""

import inspect

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter


def _finite_segment(T: int = 60) -> np.ndarray:
    """Return a (T, 17, 2) normalized pose array with all-finite values."""
    rng = np.random.default_rng(0)
    poses = rng.standard_normal((T, 17, 2)).astype(np.float32) * 0.05 + 0.5
    return np.clip(poses, 0.0, 1.0).astype(np.float32)


METADATA_KEYS = (
    "rotation_speed_max",
    "rotation_speed_mean",
    "motion_energy_mean",
    "motion_energy_max",
    "motion_energy_std",
)


def test_nan_shoulder_keypoint_produces_finite_rotation_speed() -> None:
    """NaN shoulder → arctan2(NaN)=NaN → rotation_speed_* must still be finite."""
    seg = ElementSegmenter()
    poses = _finite_segment(T=60)
    poses[30, 6, :] = np.nan  # occluded RShoulder
    feats = seg._extract_segment_features(poses, fps=30.0)
    for k in ("rotation_speed_max", "rotation_speed_mean"):
        assert np.isfinite(feats[k]), f"{k}={feats[k]} not finite (NaN leak)"


def test_nan_keypoint_produces_finite_motion_energy() -> None:
    """NaN any joint → norm(NaN)=NaN → motion_energy_* must still be finite."""
    seg = ElementSegmenter()
    poses = _finite_segment(T=60)
    poses[30, 14, :] = np.nan  # occluded joint
    feats = seg._extract_segment_features(poses, fps=30.0)
    for k in ("motion_energy_mean", "motion_energy_max", "motion_energy_std"):
        assert np.isfinite(feats[k]), f"{k}={feats[k]} not finite (NaN leak)"


def test_all_nan_segment_produces_finite_metadata_features() -> None:
    """Entirely occluded segment must return finite (sentinel) metadata features."""
    seg = ElementSegmenter()
    poses = np.full((5, 17, 2), np.nan, dtype=np.float32)
    feats = seg._extract_segment_features(poses, fps=30.0)
    for k in METADATA_KEYS:
        assert k in feats, f"{k} missing from features"
        assert np.isfinite(feats[k]), f"{k}={feats[k]} not finite for all-NaN segment"


def test_finite_poses_metadata_features_unchanged() -> None:
    """Regression: finite input metadata features byte-identical to pre-fix."""
    seg = ElementSegmenter()
    poses = _finite_segment(T=60)
    feats = seg._extract_segment_features(poses, fps=30.0)
    # nan_to_num is a no-op on finite input → features must match direct compute.
    motion_energy = seg._compute_motion_energy(poses)
    assert feats["motion_energy_mean"] == float(np.mean(motion_energy))
    assert feats["motion_energy_max"] == float(np.max(motion_energy))
    assert feats["motion_energy_std"] == float(np.std(motion_energy))
    angles = seg._compute_shoulder_rotation(poses)
    rot_v = np.abs(np.gradient(angles)) * 30.0 * (180.0 / np.pi)
    assert feats["rotation_speed_max"] == float(np.max(rot_v))
    assert feats["rotation_speed_mean"] == float(np.mean(rot_v))


def test_source_has_nan_guard() -> None:
    """Root-cause lock: _extract_segment_features source must reference a NaN guard."""
    src = inspect.getsource(ElementSegmenter._extract_segment_features)
    assert "nan_to_num" in src or "isfinite" in src or "nanmax" in src, (
        "_extract_segment_features lacks NaN guard (root cause unfixed)"
    )
