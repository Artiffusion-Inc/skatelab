"""Pose estimation module for figure skating analysis.

Provides H3.6M 17-keypoint pose extraction as the primary format.
Uses PersonDetector (RF-DETR) + MogaNetBatch (ONNX) top-down pipeline.

Architecture:
    Video -> PersonDetector -> MogaNetBatch -> COCO 17kp -> H3.6M 17kp

Multi-GPU:
    Video -> MultiGPUPoseExtractor -> distribute across GPUs -> H3.6M 17kp
"""

from src.pose_estimation.h36m import (
    H36M_KEYPOINT_NAMES,
    H36M_SKELETON_EDGES,
    H36Key,
)
from src.pose_estimation.multi_gpu_extractor import MultiGPUPoseExtractor
from src.pose_estimation.normalizer import PoseNormalizer
from src.pose_estimation.pose_extractor import PoseExtractor, extract_poses

__all__ = [
    "H36M_KEYPOINT_NAMES",
    "H36M_SKELETON_EDGES",
    "H36Key",
    "MultiGPUPoseExtractor",
    "PoseExtractor",
    "PoseNormalizer",
    "extract_poses",
]
