"""Multi-person detection and tracking module."""

from ..types import BoundingBox
from .person_detector import PersonDetector
from .pose_tracker import PoseTracker, Track
from .spatial_reference import CameraPose, SpatialReferenceDetector

__all__ = [
    "BoundingBox",
    "CameraPose",
    "PersonDetector",
    "PoseTracker",
    "SpatialReferenceDetector",
    "Track",
]
