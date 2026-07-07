"""Reference data builder from expert videos.

H3.6M Migration:
    Uses H3.6M 17-keypoint format as the primary format.
    2D extraction: PoseExtractor (PersonDetector + MogaNetBatch)

This module provides tools to create reference datasets from
expert skating videos for comparison with user performances.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from ..types import (
    ElementPhase,
    ReferenceData,
    VideoMeta,
)  # type: ignore[import-untyped]
from ..utils.video import get_video_meta

if TYPE_CHECKING:
    from .normalizer import PoseNormalizer  # type: ignore[import-untyped]
    from .pose_estimation import PoseExtractor  # type: ignore[import-untyped]


class ReferenceBuilder:
    """Build reference data from expert skating videos.

    H3.6M Architecture:
        - 2D poses: PoseExtractor (17 keypoints, normalized [0,1])
    """

    def __init__(
        self,
        pose_extractor: "PoseExtractor",  # type: ignore[valid-type]
        normalizer: "PoseNormalizer",  # type: ignore[valid-type]
    ) -> None:
        """Initialize reference builder.

        Args:
            pose_extractor: PoseExtractor instance.
            normalizer: PoseNormalizer instance.
        """
        self._pose_extractor = pose_extractor
        self._normalizer = normalizer

    def build_from_video(
        self,
        video_path: Path,
        element_type: str,
        phases: ElementPhase,
    ) -> ReferenceData:
        """Build reference data from a video.

        Args:
            video_path: Path to expert video.
            element_type: Type of skating element.
            phases: Phase boundaries (manually annotated).

        Returns:
            ReferenceData with normalized poses (H3.6M 17kp format) and metadata.
        """
        # Extract video metadata
        meta = get_video_meta(video_path)

        # Extract poses in H3.6M format (normalized [0,1]) with tracking
        extraction = self._pose_extractor.extract_video_tracked(video_path)
        normalized = self._normalizer.normalize(extraction.poses)

        return ReferenceData(
            element_type=element_type,
            name=video_path.name,
            poses=normalized,
            phases=phases,
            fps=meta.fps,
            meta=meta,
            source=str(video_path),
        )

    def save_reference(self, ref: ReferenceData, output_dir: Path) -> Path:
        """Save reference data to .npz file.

        Args:
            ref: ReferenceData to save.
            output_dir: Directory to save reference file.

        Returns:
            Path to saved .npz file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create filename from element type and source. #802: use .stem so the
        # source extension is stripped — .name kept "expert.mp4" →
        # "waltz_jump_expert.mp4.npz" (double extension), and refs differing
        # only by source extension (expert.mp4 vs expert.mov) collided as
        # distinct filenames for the same logical ref.
        source_path = Path(ref.source)
        filename = f"{ref.element_type}_{source_path.stem}.npz"
        output_path = output_dir / filename

        # Save to .npz format
        save_dict = {
            "element_type": ref.element_type,
            "poses": ref.poses,
            # #492: persist ref.fps directly (not just meta_fps). Pre-fix
            # the save_dict had only `meta_fps`; load_reference used
            # `data.get("fps", meta.fps)` which silently fell back to
            # meta.fps when ref.fps != meta.fps — a 60fps ref loaded as
            # 30fps halved every time-derived metric (airtime, DTW, etc).
            # Persist both: `fps` (the actual fps used for the ref) and
            # `meta_fps` (the source video's fps, for reference).
            "fps": ref.fps,
            "meta_fps": ref.meta.fps if ref.meta else 30.0,
            "meta_width": ref.meta.width if ref.meta else 1920,
            "meta_height": ref.meta.height if ref.meta else 1080,
            "meta_num_frames": ref.meta.num_frames if ref.meta else len(ref.poses),
            "meta_path": str(ref.meta.path) if ref.meta else "",
            "phases_name": ref.phases.name,
            "phases_start": ref.phases.start,
            "phases_takeoff": ref.phases.takeoff,
            "phases_peak": ref.phases.peak,
            "phases_landing": ref.phases.landing,
            "phases_end": ref.phases.end,
            "source": ref.source,
        }
        if ref.poses_3d is not None:
            save_dict["poses_3d"] = ref.poses_3d
        np.savez_compressed(output_path, **save_dict)

        return output_path

    def load_reference(self, path: Path) -> ReferenceData:
        """Load reference data from .npz file.

        Args:
            path: Path to .npz file.

        Returns:
            ReferenceData.

        Raises:
            RuntimeError: If a numeric field in the .npz is non-finite
                (NaN / inf) — corrupt-disk / partial-write path. Mirrors
                the #1041 `get_video_meta` style.
        """

        def _finite_int(key: str) -> int:
            raw = float(data[key])
            if not np.isfinite(raw):
                raise RuntimeError(
                    f"Corrupt reference .npz: non-finite {key}={raw} for path={path}"
                )
            return int(raw)

        def _finite_float(key: str) -> float:
            raw = float(data[key])
            if not np.isfinite(raw):
                raise RuntimeError(
                    f"Corrupt reference .npz: non-finite {key}={raw} for path={path}"
                )
            return raw

        data = np.load(path, allow_pickle=True)

        # Reconstruct VideoMeta
        meta = VideoMeta(
            path=Path(str(data["meta_path"])),
            fps=_finite_float("meta_fps"),
            width=_finite_int("meta_width"),
            height=_finite_int("meta_height"),
            num_frames=_finite_int("meta_num_frames"),
        )

        # Reconstruct ElementPhase
        phases = ElementPhase(
            name=str(data["phases_name"]),
            start=_finite_int("phases_start"),
            takeoff=_finite_int("phases_takeoff"),
            peak=_finite_int("phases_peak"),
            landing=_finite_int("phases_landing"),
            end=_finite_int("phases_end"),
        )

        poses_3d = None
        if "poses_3d" in data:
            poses_3d = data["poses_3d"].astype(np.float32)

        return ReferenceData(
            element_type=str(data["element_type"]),
            # #800: build_from_video set name=video_path.name (basename); load
            # set name=str(data["source"]) (full path) — round-trip changed
            # name from "expert.mp4" to "/data/refs/expert.mp4". Use basename
            # so load matches build. source stays the full string.
            name=Path(str(data["source"])).name,
            poses=data["poses"],
            poses_3d=poses_3d,
            phases=phases,
            fps=_finite_float("fps") if "fps" in data else meta.fps,
            meta=meta,
            source=str(data["source"]),
        )
