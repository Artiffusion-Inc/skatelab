"""Unified visualization pipeline for CLI and Gradio frontends.

Encapsulates shared logic: pose normalization, layer construction,
per-frame rendering, and data export. Callers provide video I/O.
"""

from __future__ import annotations

import csv as _csv
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from src.visualization import (
    BladeLayer,
    HUDLayer,
    JointAngleLayer,
    LayerContext,
    TrailLayer,
    VelocityLayer,
    VerticalAxisLayer,
    draw_skeleton,
    render_layers,
)

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

    from src.types import VideoMeta
    from src.visualization.layers.base import Frame

# ---------------------------------------------------------------------------
# Declarative layer registry
# ---------------------------------------------------------------------------

LAYER_REGISTRY: dict[str, type] = {
    "trail": TrailLayer,
    "velocity": VelocityLayer,
    "joint_angle": JointAngleLayer,
    "vertical_axis": VerticalAxisLayer,
    "hud": HUDLayer,
    "blade": BladeLayer,
}

LEVEL_PRESETS: dict[int, list[str]] = {
    0: [],
    1: ["trail", "velocity"],
    2: ["trail", "velocity", "joint_angle", "vertical_axis"],
    3: ["trail", "velocity", "joint_angle", "vertical_axis", "hud", "blade"],
}


@dataclass
class VizPipeline:
    """Shared visualization pipeline state and rendering logic.

    Callers (CLI, Gradio) construct this with prepared pose data,
    then call ``render_frame()`` in their video loop.

    Args:
        meta: Video metadata object with ``width``, ``height``, ``fps``, ``num_frames``.
        poses_norm: Normalized [0,1] poses (N, 17, 2).
        poses_px: Pixel-coordinate poses (N, 17, 2 or 17, 3). Used for skeleton drawing.
        poses_3d: 3D poses (N, 17, 3) or None.
        layer: HUD layer level (0-3).
        confs: Per-keypoint confidence (N, 17) or None.
        frame_indices: Frame index mapping (N,). Defaults to ``np.arange(N)``.
    """

    meta: VideoMeta
    poses_norm: NDArray[np.float32]
    poses_px: NDArray[np.float32] | None = None
    poses_3d: NDArray[np.float32] | None = None
    layer: int = 0
    confs: NDArray[np.float32] | None = None
    frame_indices: NDArray[np.intp] | None = None
    physics: dict[str, Any] | None = None

    # Internal state
    layers: list = field(default_factory=list, init=False)
    export_frames: list[int] = field(default_factory=list, init=False)
    export_timestamps: list[float] = field(default_factory=list, init=False)
    export_floor_angles: list[float] = field(default_factory=list, init=False)
    export_joint_angles: list[dict] = field(default_factory=list, init=False)
    export_poses: list[NDArray] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        n = len(self.poses_norm)
        if self.frame_indices is None:
            self.frame_indices = np.arange(n)
        if self.poses_px is None:
            w, h = self.meta.width, self.meta.height
            self.poses_px = self.poses_norm.copy()
            self.poses_px[:, :, 0] *= w
            self.poses_px[:, :, 1] *= h
        self.build_layers()

    def build_layers(self) -> None:
        """Construct visualization layers based on ``self.layer`` level."""
        self.layers = []
        preset = LEVEL_PRESETS.get(self.layer, [])
        for name in preset:
            cls = LAYER_REGISTRY.get(name)
            if cls is not None:
                self.layers.append(cls())

    def add_ml_layers(self, ml_layers: list) -> None:
        """Add ML-generated layers to the pipeline."""
        self.layers.extend(ml_layers)

    def render_frame(
        self,
        frame: Frame,
        frame_idx: int,
        pose_idx: int | None,
    ) -> tuple[Frame, LayerContext]:
        """Render one frame with skeleton, layers.

        Args:
            frame: BGR image to draw on (modified in place).
            frame_idx: Current video frame index.
            pose_idx: Index into poses_norm/poses_px, or None if no pose.

        Returns:
            Tuple of (modified frame, LayerContext).
        """
        w, h = self.meta.width, self.meta.height
        total = self.meta.num_frames

        context = LayerContext(
            frame_width=w,
            frame_height=h,
            fps=self.meta.fps,
            frame_idx=frame_idx,
            total_frames=total,
            normalized=True,
            physics=self.physics or {},
        )

        # Skeleton (always drawn when pose available)
        if pose_idx is not None and pose_idx < len(self.poses_norm):
            if self.poses_px is None:
                raise ValueError("poses_px is None but pose_idx is valid")
            skel_pose = self.poses_px[pose_idx].copy()
            frame = draw_skeleton(
                frame,
                skel_pose,
                h,
                w,
                line_width=1,
                joint_radius=3,
            )
            context.pose_2d = self.poses_norm[pose_idx]
            if self.poses_3d is not None and pose_idx < len(self.poses_3d):
                context.pose_3d = self.poses_3d[pose_idx]

        # Layers 1+: velocity, trails, joint angles, axis
        if self.layer >= 1 and pose_idx is not None:
            frame = render_layers(frame, self.layers, context)

        return frame, context

    def draw_frame_counter(
        self,
        frame: Frame,
        frame_idx: int,
    ) -> Frame:
        """Draw frame counter and timestamp at bottom-left."""
        from src.visualization.core.text import draw_text_outlined

        w, h = self.meta.width, self.meta.height
        total = self.meta.num_frames
        fps = self.meta.fps

        # #1105: NaN/inf on EITHER side of `frame_idx / fps` reaches the
        # unguarded `int(time_sec) // 60` and `int((seconds % 1) * 100)`
        # and raises ValueError / OverflowError. The #959 `if fps > 0`
        # guard is NaN-fps-blind-pass by accident (`NaN > 0` is False
        # -> 0.0 branch) but is fps-only - NaN/inf frame_idx with valid
        # fps LEAKS NaN to the int() conversions. Use `math.isfinite`
        # on both inputs - mirror the #1115 sibling at line 215-220
        # and the trust-boundary pattern at `types.py:459
        # VideoMeta.duration_sec`, `phase_detector.py:383`,
        # `physics_engine.py:381/486`. Degrade to 0.0 (mirror the
        # #959 contract): the frame counter (frame_idx/total, fps-
        # independent) is still rendered, only the timestamp is
        # unknowable.
        fps_finite = math.isfinite(fps) and fps > 0
        frame_finite = math.isfinite(float(frame_idx))
        time_sec = frame_idx / fps if fps_finite and frame_finite else 0.0
        minutes = int(time_sec) // 60
        seconds = time_sec % 60
        ms = int((seconds % 1) * 100)
        frame_text = f"{frame_idx}/{total}  {minutes:02d}:{int(seconds):02d}.{ms:02d}"

        info_y = h - 40
        draw_text_outlined(frame, frame_text, (10, info_y - 25), font_scale=0.45, thickness=1)
        return frame

    def collect_export_data(
        self,
        frame_idx: int,
        pose_idx: int | None,
        floor_angle: float = 0.0,
    ) -> None:
        """Collect data for NPY + CSV export."""
        if pose_idx is None:
            return
        # #1115: NaN/inf on EITHER side of `frame_idx / self.meta.fps`
        # silently leaks NaN to the CSV (`round(NaN, 3) = NaN`). The
        # #959 `if fps > 0` guard is NaN-fps-blind-pass by accident
        # (`NaN > 0` is False → 0.0 branch) but inf-fps-blind-fail
        # (`inf > 0` is True → `5/inf = 0.0` indistinguishable from a
        # legitimate fps=0 broken-header video), AND it ignores
        # `frame_idx=nan` entirely (NaN/30 = NaN). Use `math.isfinite`
        # on both inputs — mirror the trust-boundary pattern at
        # `types.py:459 VideoMeta.duration_sec`,
        # `phase_detector.py:383`, `physics_engine.py:381/486`. Degrade
        # to 0.0 (mirror the #959 contract) instead of skipping the
        # frame — the row is still useful (joint angles, floor angle,
        # poses), only the timestamp column is unknowable.
        fps_finite = math.isfinite(self.meta.fps) and self.meta.fps > 0
        frame_finite = math.isfinite(float(frame_idx))
        self.export_frames.append(frame_idx)
        self.export_timestamps.append(
            round(frame_idx / self.meta.fps, 3) if fps_finite and frame_finite else 0.0
        )
        self.export_floor_angles.append(round(floor_angle, 2))
        from src.analysis.angles import compute_joint_angles

        ja = compute_joint_angles(self.poses_norm[pose_idx])
        self.export_joint_angles.append(ja)
        if self.poses_px is not None:
            self.export_poses.append(self.poses_px[pose_idx].copy())

    def save_exports(self, output_path: Path) -> dict[str, str | None]:
        """Save NPY poses and CSV biomechanics data alongside output video.

        Returns:
            Dict with ``poses_path`` and ``csv_path`` keys (None if no data).
        """
        if not self.export_poses:
            return {"poses_path": None, "csv_path": None}

        out_dir = output_path.parent
        stem = output_path.stem

        poses_path = out_dir / f"{stem}_poses.npy"
        np.save(str(poses_path), np.array(self.export_poses))

        csv_path = out_dir / f"{stem}_biomechanics.csv"
        angle_keys = [
            "R Ankle",
            "L Ankle",
            "R Knee",
            "L Knee",
            "R Hip",
            "L Hip",
            "R Shoulder",
            "L Shoulder",
            "R Elbow",
            "L Elbow",
            "R Wrist",
            "L Wrist",
        ]
        header = ["frame", "timestamp_s", "floor_angle_deg", *angle_keys]
        with csv_path.open("w", newline="") as f:
            writer = _csv.writer(f)
            writer.writerow(header)
            for idx in range(len(self.export_frames)):
                ja = self.export_joint_angles[idx]
                row = [
                    self.export_frames[idx],
                    self.export_timestamps[idx],
                    self.export_floor_angles[idx],
                    *(round(ja.get(k, float("nan")), 1) for k in angle_keys),
                ]
                writer.writerow(row)

        return {"poses_path": str(poses_path), "csv_path": str(csv_path)}

    def find_pose_idx(self, frame_idx: int, pose_idx: int) -> tuple[int | None, int]:
        """Advance pose_idx to match frame_idx.

        Returns:
            Tuple of (current_pose_idx_or_None, next_pose_idx).
        """
        if self.frame_indices is None:
            raise ValueError("frame_indices is None")
        while pose_idx < len(self.frame_indices):
            if self.frame_indices[pose_idx] == frame_idx:
                return pose_idx, pose_idx + 1
            elif self.frame_indices[pose_idx] < frame_idx:
                pose_idx += 1
            else:
                break
        return None, pose_idx


# ------------------------------------------------------------------
# Unified pose preparation — re-exported from core module
# ------------------------------------------------------------------

# Import pose_preparation helpers directly when needed (unused re-exports removed)
