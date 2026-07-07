"""MCFS data loading with coarse label mapping for TAS.

Loads OpenPose 25 keypoints, converts to COCO17 -> H3.6M, normalizes,
and returns frame-wise coarse labels (None/Jump/Spin/Step).
"""

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import torch
from torch.utils.data import Dataset

from ..pose_estimation.h36m import coco_to_h36m_batch

if TYPE_CHECKING:
    from numpy.typing import NDArray


# OP25 -> COCO17 index mapping (13 keypoints). OP25 L/R conventions match
# COCO L/R; only the 13 OP25 joints that have a direct COCO counterpart are mapped.
OP25_TO_COCO17 = {
    0: 0,  # Nose
    2: 6,  # RShoulder -> COCO RShoulder
    3: 8,  # RElbow   -> COCO RElbow
    4: 10,  # RWrist   -> COCO RWrist
    5: 5,  # LShoulder -> COCO LShoulder
    6: 7,  # LElbow   -> COCO LElbow
    7: 9,  # LWrist   -> COCO LWrist
    9: 12,  # RHip     -> COCO RHip
    10: 14,  # RKnee    -> COCO RKnee
    11: 16,  # RAnkle   -> COCO RAnkle
    12: 11,  # LHip     -> COCO LHip
    13: 13,  # LKnee    -> COCO LKnee
    14: 15,  # LAnkle   -> COCO LAnkle
}


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
    out = np.zeros((T, 17, 2), dtype=np.float32)
    for op_idx, coco_idx in OP25_TO_COCO17.items():
        out[:, coco_idx, :] = poses_op25[:, op_idx, :2].astype(np.float32)
    # COCO17 has no mid-hip keypoint — LHip/RHip slots keep their mapped values;
    # coco_to_h36m_batch derives HIP_CENTER from L+R hip itself.
    return out


def normalize_poses(poses: "NDArray[np.float32]") -> "NDArray[np.float32]":
    """Root-center + spine-length scale normalization on H3.6M poses.

    Called after ``coco_to_h36m_batch``, so ``poses`` are H3.6M 17kp:
    0=HIP_CENTER, 1=RHIP, 4=LHIP, 8=THORAX, 9=NECK, ... (see H36Key).

    Args:
        poses: (T, 17, 2) H3.6M format keypoints.

    Returns:
        Normalized poses (root at hip, scaled by hip->thorax spine length).
    """
    # H3.6M hip root: midpoint of RHIP(1) and LHIP(4). Falls back to HIP_CENTER(0)
    # alone if one hip is zero/degenerate, but both are present in normal data.
    mid = poses[:, [1, 4], :].mean(axis=1, keepdims=True)  # (T, 1, 2)
    p = poses - mid
    # Spine length: distance from hip root to THORAX(8). Use NECK(9) as fallback
    # anchor if THORAX is degenerate; both are torso joints (not a leg segment).
    spine = np.linalg.norm(p[:, 8, :], axis=1, keepdims=True)  # (T, 1)
    return p / np.maximum(spine[:, :, None], 0.01)


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
        preload: bool = True,
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
        # Pre-load all samples into RAM if requested
        self._cache: dict[int, tuple] = {}
        if preload:
            for idx in range(len(self.samples)):
                self._cache[idx] = self._load_sample(idx)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple["NDArray[np.float32]", "NDArray[np.int64]", int]:
        if idx in self._cache:
            return self._cache[idx]
        return self._load_sample(idx)

    def _load_sample(self, idx: int) -> tuple["NDArray[np.float32]", "NDArray[np.int64]", int]:
        stem = self.samples[idx]
        # Load poses: (T, 25, 3) OP25
        poses_op25 = np.load(self.feature_paths[stem])  # (T, 25, 3)
        # Load labels
        fine_labels = [line.strip() for line in self.label_paths[stem].read_text().splitlines()]
        # Convert OP25 -> COCO17
        poses_coco17 = op25_to_coco17(poses_op25)  # (T, 17, 2)
        # Convert COCO17 -> H3.6M (vectorized)
        poses_h36m = coco_to_h36m_batch(poses_coco17)  # (T, 17, 2)
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
    poses_padded = torch.zeros(B, max_len, 17, 2, dtype=torch.float32)  # type: ignore[reportPrivateImportUsage]
    labels_padded = torch.full((B, max_len), -1, dtype=torch.long)  # type: ignore[reportPrivateImportUsage]
    for i, (p, lbl, le) in enumerate(zip(poses_list, labels_list, lengths, strict=True)):
        poses_padded[i, :le] = torch.from_numpy(p)  # type: ignore[reportPrivateImportUsage]
        labels_padded[i, :le] = torch.from_numpy(lbl)  # type: ignore[reportPrivateImportUsage]
    lengths_tensor = torch.tensor(lengths, dtype=torch.long)  # type: ignore[reportPrivateImportUsage]
    return poses_padded, labels_padded, lengths_tensor


class BucketBatchSampler:
    """Batch sampler that groups similar-length samples into bins for efficient padding.

    Uses epoch-aware shuffling via set_epoch() to produce different orderings
    across training epochs, compatible with PyTorch's distributed training pattern.
    """

    def __init__(
        self,
        lengths: list[int],
        batch_size: int = 8,
        bin_size: int = 50,
        shuffle: bool = True,
        seed: int = 42,
    ) -> None:
        self.lengths = lengths
        self.batch_size = batch_size
        self.bin_size = bin_size
        self.shuffle = shuffle
        self.seed = seed
        self.epoch = 0
        self._build_bins()

    def _build_bins(self) -> None:
        """Group sample indices into bins by sequence length."""
        self.bins: dict[int, list[int]] = {}
        for idx, length in enumerate(self.lengths):
            bin_key = length // self.bin_size
            if bin_key not in self.bins:
                self.bins[bin_key] = []
            self.bins[bin_key].append(idx)

    def set_epoch(self, epoch: int) -> None:
        """Set the epoch for deterministic shuffling across epochs."""
        self.epoch = epoch

    def __iter__(self):  # type: ignore[override]
        rng = np.random.default_rng(self.seed + self.epoch)
        # Flatten all bins, optionally shuffling within each bin
        indices: list[int] = []
        for bin_key in sorted(self.bins.keys()):
            bin_indices = list(self.bins[bin_key])
            if self.shuffle:
                rng.shuffle(bin_indices)
            indices.extend(bin_indices)
        # Shuffle globally across bins too
        if self.shuffle:
            rng.shuffle(indices)
        # Batch
        for i in range(0, len(indices), self.batch_size):
            yield indices[i : i + self.batch_size]

    def __len__(self) -> int:
        return (len(self.lengths) + self.batch_size - 1) // self.batch_size


__all__ = [
    "BucketBatchSampler",
    "MCFSCoarseDataset",
    "coarse_label",
    "normalize_poses",
    "op25_to_coco17",
    "pad_collate",
]
