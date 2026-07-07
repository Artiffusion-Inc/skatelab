"""Repro for #979: tas.extract_segment_features NaN keypoint leak into RF features.

A NaN keypoint (occluded joint) on any frame propagates through non-NaN-aware
reductions (np.max/np.min/np.mean) and np.arctan2 into the feature dict, which
SegmentClassifier.predict silently feeds to sklearn RandomForest →
misclassification without any NaN error signal.

Contract: extract_segment_features must return ONLY finite floats for any
input pose array, including ones containing NaN keypoints.
"""

import inspect

import numpy as np

from src.tas.classifier import extract_segment_features


def _finite_segment(T: int = 10) -> np.ndarray:
    """Return a (T, 17, 2) pose array with all-finite values."""
    rng = np.random.default_rng(0)
    poses = rng.standard_normal((T, 17, 2)).astype(np.float32) * 0.05 + 0.5
    return np.clip(poses, 0.0, 1.0).astype(np.float32)


def test_nan_hip_keypoint_produces_finite_features() -> None:
    """NaN midhip (kp 11/12) must not leak NaN into hip_y_range / motion_energy."""
    poses = _finite_segment(T=10)
    poses[3, 11, :] = np.nan  # occluded LHip
    poses[5, 12, :] = np.nan  # occluded RHip
    feats = extract_segment_features(poses, fps=30.0)
    for k, v in feats.items():
        assert np.isfinite(v), f"feature {k}={v} is not finite (NaN leak)"


def test_nan_shoulder_keypoint_produces_finite_rotation_speed() -> None:
    """NaN shoulder → np.arctan2(NaN)=NaN → rotation_speed must still be finite."""
    poses = _finite_segment(T=10)
    poses[2, 5, :] = np.nan  # occluded LShoulder
    poses[7, 6, :] = np.nan  # occluded RShoulder
    feats = extract_segment_features(poses, fps=30.0)
    assert np.isfinite(feats["rotation_speed"]), (
        f"rotation_speed={feats['rotation_speed']} not finite (NaN leak)"
    )
    assert np.isfinite(feats["motion_energy"]), (
        f"motion_energy={feats['motion_energy']} not finite (NaN leak)"
    )


def test_all_nan_segment_produces_finite_features() -> None:
    """Entirely occluded segment must return finite (sentinel) features, not NaN."""
    poses = np.full((5, 17, 2), np.nan, dtype=np.float32)
    feats = extract_segment_features(poses, fps=30.0)
    for k, v in feats.items():
        assert np.isfinite(v), f"feature {k}={v} not finite for all-NaN segment"


def test_finite_poses_features_unchanged() -> None:
    """Regression: finite input features must be byte-identical to pre-fix output."""
    poses = _finite_segment(T=10)
    feats = extract_segment_features(poses, fps=30.0)
    # Recompute expected directly from the same finite array (no NaN guard
    # needed since input is finite — nan_to_num is a no-op on finite data).
    midhip = poses[:, 11:13, :].mean(axis=1)
    expected_hip_y_range = float(np.max(midhip[:, 1]) - np.min(midhip[:, 1]))
    diff = np.diff(poses, axis=0)
    expected_motion_energy = float(np.mean(np.linalg.norm(diff, axis=(1, 2))))
    shoulders = poses[:, [5, 6], :]
    shoulder_vec = shoulders[:, 1] - shoulders[:, 0]
    angles = np.arctan2(shoulder_vec[:, 1], shoulder_vec[:, 0])
    expected_rot_speed = float(np.max(np.abs(np.gradient(angles)) * 30.0))
    assert feats["hip_y_range"] == expected_hip_y_range
    assert feats["motion_energy"] == expected_motion_energy
    assert feats["rotation_speed"] == expected_rot_speed
    assert feats["num_frames"] == 10


def test_source_has_nan_guard() -> None:
    """Root-cause lock: source must reference an isfinite/nan_to_num guard."""
    src = inspect.getsource(extract_segment_features)
    assert "nan_to_num" in src or "isfinite" in src or "nanmax" in src, (
        "extract_segment_features lacks NaN guard (root cause unfixed)"
    )
