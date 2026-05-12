"""Pose extraction pipeline — prepare poses for analysis.

Extracted from visualization.pipeline to avoid pulling viz dependencies
into the GPU worker. This module is the core pose extraction utility
shared by CLI, Gradio, and the GPU server.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.types import PersonClick

import numpy as np

from src.utils.video import get_video_meta

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_MODEL_3D_CANDIDATES = [
    _PROJECT_ROOT / "data" / "models" / "motionagformer-s-ap3d.onnx",
    Path("data/models/motionagformer-s-ap3d.onnx"),
]

from src.pose_3d.onnx_extractor import ONNXPoseExtractor  # noqa: E402
from src.pose_estimation.pose_extractor import PoseExtractor  # noqa: E402


@dataclass
class PreparedPoses:
    """Output of the unified pose preparation pipeline.

    Constructed by ``prepare_poses()`` and consumed by analysis or visualization.
    """

    poses_norm: np.ndarray  # (N, 17, 2) corrected normalized [0,1]
    poses_px: np.ndarray  # (N, 17, 3) pixel coords (x, y, confidence)
    poses_3d: np.ndarray | None  # (N, 17, 3) 3D poses for GLB export
    confs: np.ndarray  # (N, 17) per-keypoint confidence
    frame_indices: np.ndarray  # (N,) frame index mapping
    meta: object  # VideoMeta (width, height, fps, num_frames)
    n_valid: int  # valid (non-interpolated) frames
    n_total: int  # total video frames


def _resolve_model_3d(path: Path | str | None = None) -> Path | None:
    """Find the 3D pose model.

    Args:
        path: Explicit path, or None to auto-detect.

    Returns:
        Path to model file, or None if not found.
    """
    if path is not None:
        p = Path(path)
        return p if p.exists() else None
    for candidate in _DEFAULT_MODEL_3D_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def prepare_poses(
    video_path: Path | str,
    person_click: PersonClick | None = None,
    *,
    frame_skip: int = 1,
    tracking: str = "auto",
    model_3d_path: Path | str | None = None,
    device: str = "auto",
    progress_cb: Callable[[float, str], None] | None = None,
) -> PreparedPoses:
    """Unified pose preparation pipeline.

    Extract 2D poses -> fill gaps -> optional 3D lift.

    Args:
        video_path: Path to input video.
        person_click: PersonClick to select target person, or None.
        frame_skip: Process every Nth frame (default 1 = every frame).
        tracking: Tracking mode ("auto", "sports2d", "deepsort").
        model_3d_path: Path to 3D model, or None to auto-detect.
        device: Device string ("auto", "cuda", "cpu").
        progress_cb: Optional callback ``(progress_0_to_1, message)``.

    Returns:
        PreparedPoses with all data needed for analysis or visualization.
    """
    from src.device import DeviceConfig

    video_path = Path(video_path)
    meta = get_video_meta(video_path)
    cfg = DeviceConfig(device=device)

    if progress_cb:
        progress_cb(0.0, "Extracting poses...")

    # --- Step 1: Extract 2D poses ---
    extractor = PoseExtractor(
        output_format="normalized",
        conf_threshold=0.3,
        frame_skip=frame_skip,
        device=cfg.device,
        tracking_mode=tracking,
    )
    extraction = extractor.extract_video_tracked(
        str(video_path),
        person_click=person_click,
        progress_cb=progress_cb,
    )

    raw_poses = extraction.poses  # (N, 17, 3) — may have NaN from frame_skip
    frame_indices = extraction.frame_indices

    nan_mask = np.isnan(raw_poses[:, 0, 0])
    n_valid = int((~nan_mask).sum())

    # --- Step 2: Fill NaN gaps (linear interp, preserves array length) ---
    if nan_mask.any() and n_valid >= 2:
        valid_indices = np.where(~nan_mask)[0]
        n_frames = len(raw_poses)
        for kp in range(raw_poses.shape[1]):
            for dim in range(raw_poses.shape[2]):
                raw_poses[:, kp, dim] = np.interp(
                    np.arange(n_frames),
                    valid_indices,
                    raw_poses[valid_indices, kp, dim],
                )
        logger.info(
            "Filled %d NaN frame(s) via linear interpolation (%d valid)",
            int(nan_mask.sum()),
            n_valid,
        )

    poses_norm = raw_poses[:, :, :2].copy()
    confs = raw_poses[:, :, 2].copy()

    if progress_cb:
        progress_cb(0.4, "3D pose estimation...")

    # --- Step 4: 3D lift ---
    poses_3d = None
    model_path = _resolve_model_3d(model_3d_path)

    if model_path is not None:
        onnx = ONNXPoseExtractor(model_path, device=cfg.device)
        poses_3d = onnx.estimate_3d(poses_norm)
        logger.info("3D poses estimated")
    else:
        logger.warning("No 3D model found. Skeleton will use raw 2D poses without correction.")

    # --- Step 5: Build pixel coordinates from FINAL poses_norm ---
    poses_px = np.zeros((*poses_norm.shape[:2], 3), dtype=np.float32)
    poses_px[:, :, 0] = poses_norm[:, :, 0] * meta.width
    poses_px[:, :, 1] = poses_norm[:, :, 1] * meta.height
    poses_px[:, :, 2] = confs

    if progress_cb:
        progress_cb(0.6, "Poses ready.")

    return PreparedPoses(
        poses_norm=poses_norm,
        poses_px=poses_px,
        poses_3d=poses_3d,
        confs=confs,
        frame_indices=frame_indices,
        meta=meta,
        n_valid=n_valid,
        n_total=meta.num_frames,
    )
