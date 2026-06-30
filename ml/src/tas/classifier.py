"""Random Forest classifier for fine element types from segment features.

Maps TAS coarse segments to fine labels (top 30 most frequent classes).
"""

from typing import TYPE_CHECKING

import numpy as np
import torch
from torch import nn

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

    # #467: np.gradient on a 1-element array raises ValueError (needs >=
    # edge_order+1 elements), and np.diff on a single frame is empty →
    # np.mean([]) = NaN. A single-frame segment is reachable at low fps
    # (duration filter passes end-start==1 at fps<=2.0). Guard T<2: no
    # motion/rotation can be measured from one frame, so report zeros.
    if T < 2:
        return {
            "duration": duration,
            "hip_y_range": hip_y_range,
            "motion_energy": 0.0,
            "rotation_speed": 0.0,
            "num_frames": T,
        }

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


class Skeleton1DCNN(nn.Module):
    """1D CNN classifier for fine element types from skeleton sequences.

    Input: (B, T, 34) — flattened (17, 2) per frame, variable length.
    Output: (B, num_classes) logits.

    Duration feature is concatenated after pooling to preserve temporal info.
    """

    def __init__(
        self,
        input_dim: int = 34,
        num_classes: int = 15,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(input_dim, 128, kernel_size=7, padding=3)
        self.bn1 = nn.BatchNorm1d(128)
        self.conv2 = nn.Conv1d(128, 256, kernel_size=5, padding=2)
        self.bn2 = nn.BatchNorm1d(256)
        self.conv3 = nn.Conv1d(256, 512, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm1d(512)
        self.pool = nn.AdaptiveMaxPool1d(1)
        self.fc = nn.Sequential(
            nn.Linear(513, 256),  # 512 CNN features + 1 duration feature
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        """Classify skeleton sequences.

        Args:
            x: (B, T, 34) flattened poses
            lengths: (B,) actual sequence lengths

        Returns:
            logits: (B, num_classes)
        """
        x = x.permute(0, 2, 1)  # (B, 34, T)
        x = torch.relu(self.bn1(self.conv1(x)))
        x = torch.relu(self.bn2(self.conv2(x)))
        x = torch.relu(self.bn3(self.conv3(x)))
        x = self.pool(x).squeeze(-1)  # (B, 512)
        # Concatenate normalized duration — prevents losing temporal info in AdaptiveMaxPool
        dur = (lengths.float() / lengths.max().float()).unsqueeze(1)  # (B, 1)
        x = torch.cat([x, dur], dim=1)  # (B, 513)
        return self.fc(x)


__all__ = ["SegmentClassifier", "Skeleton1DCNN", "extract_segment_features"]
