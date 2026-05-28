"""3D pose estimation."""

# Re-export H3.6M types from pose_estimation module (primary source)
from src.pose_estimation import H36M_KEYPOINT_NAMES, H36M_SKELETON_EDGES, H36Key

from .model_downloader import resolve_model
from .normalizer_3d import (
    Pose3DNormalizer,
    calculate_body_heights,
    get_head_center_3d,
    get_hip_center_3d,
)
from .onnx_extractor import ONNXPoseExtractor
from .tcpformer_extractor import TCPFormerExtractor

__all__ = [
    "H36M_KEYPOINT_NAMES",
    "H36M_SKELETON_EDGES",
    "H36Key",
    "ONNXPoseExtractor",
    "Pose3DNormalizer",
    "TCPFormerExtractor",
    "calculate_body_heights",
    "get_head_center_3d",
    "get_hip_center_3d",
    "resolve_model",
]
