"""Temporal Action Segmentation (TAS) for figure skating.

Coarse segmentation: Jump / Spin / Step / None.
Fine classifier: Random Forest on extracted segment features.
"""

from .classifier import SegmentClassifier, extract_segment_features
from .dataset import MCFSCoarseDataset, coarse_label, normalize_poses, op25_to_coco17, pad_collate
from .inference import TASElementSegmenter
from .metrics import OverlapF1
from .model import BiGRUTAS, BiGRUTASRefiner, BoundaryRefinerCNN

__all__ = [
    "BiGRUTAS",
    "BiGRUTASRefiner",
    "BoundaryRefinerCNN",
    "MCFSCoarseDataset",
    "OverlapF1",
    "SegmentClassifier",
    "TASElementSegmenter",
    "coarse_label",
    "extract_segment_features",
    "normalize_poses",
    "op25_to_coco17",
    "pad_collate",
]
