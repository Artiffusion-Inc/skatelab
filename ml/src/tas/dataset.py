"""MCFS data loading with coarse label mapping for TAS.

Loads OpenPose 25 keypoints, converts to COCO17 -> H3.6M, normalizes,
and returns frame-wise coarse labels (None/Jump/Spin/Step).
"""

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import torch
from torch.utils.data import Dataset

from ..pose_estimation.h36m import coco_to_h36m

if TYPE_CHECKING:
    from numpy.typing import NDArray


# OP25 -> COCO17 index mapping (13 keypoints)
OP25_TO_COCO17 = {
    0: 0,
    2: 5,
    3: 6,
    4: 7,
    5: 8,
    6: 9,
    7: 10,
    9: 11,
    10: 12,
    11: 13,
    12: 14,
    13: 15,
    14: 16,
}
OP25_MIDHIP_SRC = [9, 12]  # RHip, LHip in OP25


def coarse_label(fine_label: str) -> int:
    """Map 130-class MCFS label to 4 coarse classes.

    Returns:
        0: None, 1: Jump, 2: Spin, 3: Step
    """
    if fine_label == "NONE":
        return 0
    if any(
        s in fine_label for s in ("Axel", "Salchow", "Toeloop", "Lutz", "Loop", "Flip", "Euler")
    ):
        return 1
    if "Spin" in fine_label:
        return 2
    if any(s in fine_label for s in ("StepSequence", "ChoreoSequence")):
        return 3
    return 0  # Default to None for unmapped


def op25_to_coco17(poses_op25: "NDArray[np.float64]") -> "NDArray[np.float32]":
    """Convert OpenPose 25 keypoints to COCO 17 keypoints.

    Args:
        poses_op25: (T, 25, 3) array with x, y, confidence.

    Returns:
        poses_coco17: (T, 17, 2) array with x, y only.
    """
    T = poses_op25.shape[0]
    # Compute mid-hip from left/right hip
    midhip = poses_op25[:, OP25_MIDHIP_SRC, :2].mean(axis=1, keepdims=True)  # (T, 1, 2)
    out = np.zeros((T, 17, 2), dtype=np.float32)
    for op_idx, coco_idx in OP25_TO_COCO17.items():
        out[:, coco_idx, :] = poses_op25[:, op_idx, :2].astype(np.float32)
    # COCO index 11 is mid-hip
    out[:, 11, :] = midhip.squeeze(1)
    return out


def normalize_poses(poses: "NDArray[np.float32]") -> "NDArray[np.float32]":
    """Root-center + spine-length scale normalization.

    Args:
        poses: (T, 17, 2) COCO17 or H3.6M format.

    Returns:
        Normalized poses.
    """
    # Use mid-hip (COCO idx 11, H36M idx 0 after conversion)
    # For COCO17, mid-hip is idx 11
    mid = poses[:, 11:13, :].mean(axis=1, keepdims=True)  # (T, 1, 2)
    p = poses - mid
    # Spine: shoulder midpoint to hip midpoint
    sh = p[:, 5:7, :].mean(axis=1, keepdims=True)  # (T, 1, 2)
    spine = np.linalg.norm(sh, axis=2, keepdims=True)  # (T, 1, 1)
    return p / np.maximum(spine, 0.01)


class MCFSCoarseDataset(Dataset):
    """PyTorch dataset for MCFS continuous routines with coarse labels.

    Loads .npy features + .txt ground truth, converts OP25 -> COCO17 -> H3.6M,
    normalizes, and returns (poses, labels, length) tuples.
    """

    def __init__(
        self,
        features_dir: Path,
        labels_dir: Path,
        normalize: bool = True,
    ) -> None:
        self.features_dir = features_dir
        self.labels_dir = labels_dir
        self.normalize = normalize
        # Match features and labels by stem (e.g., n01_p01)
        feature_files = {p.stem: p for p in features_dir.glob("*.npy")}
        label_files = {p.stem: p for p in labels_dir.glob("*.txt")}
        self.samples = sorted(set(feature_files.keys()) & set(label_files.keys()))
        self.feature_paths = {s: feature_files[s] for s in self.samples}
        self.label_paths = {s: label_files[s] for s in self.samples}

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple["NDArray[np.float32]", "NDArray[np.int64]", int]:
        stem = self.samples[idx]
        # Load poses: (T, 25, 3) OP25
        poses_op25 = np.load(self.feature_paths[stem])  # (T, 25, 3)
        # Load labels
        fine_labels = [line.strip() for line in self.label_paths[stem].read_text().splitlines()]
        # Convert OP25 -> COCO17
        poses_coco17 = op25_to_coco17(poses_op25)  # (T, 17, 2)
        # Convert COCO17 -> H3.6M
        poses_h36m = np.stack([coco_to_h36m(p) for p in poses_coco17])  # (T, 17, 2)
        # Coarse labels
        coarse = np.array([coarse_label(label) for label in fine_labels], dtype=np.int64)
        # Normalize
        if self.normalize:
            poses_h36m = normalize_poses(poses_h36m)
        return poses_h36m.astype(np.float32), coarse, len(coarse)

    def get_fine_labels(self, idx: int) -> list[str]:
        """Get raw fine labels for a sample (for RF classifier training)."""
        stem = self.samples[idx]
        return [line.strip() for line in self.label_paths[stem].read_text().splitlines()]


def pad_collate(batch: list[tuple]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Pad batch of variable-length sequences to max length.

    Returns:
        poses: (B, T_max, 17, 2) padded with zeros
        labels: (B, T_max) padded with -1 (ignore index)
        lengths: (B,) original lengths
    """
    poses_list, labels_list, lengths = zip(*batch, strict=True)
    max_len = max(lengths)
    B = len(batch)
    poses_padded = torch.zeros(B, max_len, 17, 2, dtype=torch.float32)
    labels_padded = torch.full((B, max_len), -1, dtype=torch.long)
    for i, (p, lbl, le) in enumerate(zip(poses_list, labels_list, lengths, strict=True)):
        poses_padded[i, :le] = torch.from_numpy(p)
        labels_padded[i, :le] = torch.from_numpy(lbl)
    lengths_tensor = torch.tensor(lengths, dtype=torch.long)
    return poses_padded, labels_padded, lengths_tensor


__all__ = [
    "MCFSCoarseDataset",
    "coarse_label",
    "normalize_poses",
    "op25_to_coco17",
    "pad_collate",
]
