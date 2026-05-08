"""Random Forest classifier for fine element types from segment features.

Maps TAS coarse segments to fine labels (top 30 most frequent classes).
"""

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


def extract_segment_features(
    poses: "NDArray[np.float32]",  # (T, 17, 2) normalized H3.6M
    fps: float = 30.0,
) -> dict[str, float]:
    """Extract biomechanical features from a segment for RF classification.

    Features: duration, hip_y_range, motion_energy, rotation_speed, num_frames.
    """
    T = poses.shape[0]
    duration = T / fps

    # Hip Y trajectory (for jumps)
    midhip = poses[:, 11:13, :].mean(axis=1)  # (T, 2)
    hip_y_range = float(np.max(midhip[:, 1]) - np.min(midhip[:, 1]))

    # Motion energy
    diff = np.diff(poses, axis=0)
    motion_energy = float(np.mean(np.linalg.norm(diff, axis=(1, 2))))

    # Shoulder rotation speed
    shoulders = poses[:, [5, 6], :]  # LSHOULDER, RSHOULDER
    shoulder_vec = shoulders[:, 1] - shoulders[:, 0]
    angles = np.arctan2(shoulder_vec[:, 1], shoulder_vec[:, 0])
    rot_speed = float(np.max(np.abs(np.gradient(angles)) * fps))

    return {
        "duration": duration,
        "hip_y_range": hip_y_range,
        "motion_energy": motion_energy,
        "rotation_speed": rot_speed,
        "num_frames": T,
    }


class SegmentClassifier:
    """Random Forest classifier for fine element types from segment features."""

    def __init__(self, n_estimators: int = 200, max_depth: int = 20):
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import LabelEncoder

        self.clf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=42,
            n_jobs=-1,
        )
        self.feature_names = [
            "duration",
            "hip_y_range",
            "motion_energy",
            "rotation_speed",
            "num_frames",
        ]
        self.label_encoder = LabelEncoder()

    def fit(self, segments: list[dict]) -> None:
        """Train on list of {features: dict, label: str} segments."""
        X = np.array([[s["features"][f] for f in self.feature_names] for s in segments])
        y = self.label_encoder.fit_transform([s["label"] for s in segments])
        self.clf.fit(X, y)

    def predict(self, features: dict[str, float]) -> tuple[str, float]:
        """Predict fine label and confidence from features."""
        x = np.array([[features[f] for f in self.feature_names]])
        proba = self.clf.predict_proba(x)[0]
        pred_idx = proba.argmax()
        label = self.label_encoder.inverse_transform([pred_idx])[0]
        confidence = float(proba[pred_idx])
        return label, confidence


__all__ = ["SegmentClassifier", "extract_segment_features"]
