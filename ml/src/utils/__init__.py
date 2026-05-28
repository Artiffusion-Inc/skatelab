"""Utility modules for video processing, geometry, and smoothing."""

from src.utils.gap_filling import GapFiller, GapReport
from src.utils.geometry import (
    angle_3pt,
    calculate_center_of_mass,
    calculate_com_trajectory,
    calculate_com_trajectory_3d,
    distance,
    get_mid_hip,
    get_mid_shoulder,
    normalize_poses,
    smooth_signal,
)
from src.utils.profiling import PipelineProfiler, StageTiming, profile_stage
from src.utils.smoothing import OneEuroFilter, OneEuroFilterConfig, PoseSmoother
from src.utils.subtitles import ElementEvent, SubtitleParser
from src.utils.video import VideoMeta, extract_frames, get_video_meta, open_video

__all__ = [
    "ElementEvent",
    "GapFiller",
    "GapReport",
    "OneEuroFilter",
    "OneEuroFilterConfig",
    "PipelineProfiler",
    "PoseSmoother",
    "StageTiming",
    "SubtitleParser",
    "VideoMeta",
    "angle_3pt",
    "calculate_center_of_mass",
    "calculate_com_trajectory",
    "calculate_com_trajectory_3d",
    "distance",
    "extract_frames",
    "get_mid_hip",
    "get_mid_shoulder",
    "get_video_meta",
    "normalize_poses",
    "open_video",
    "profile_stage",
    "smooth_signal",
]
