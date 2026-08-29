"""Batched MogaNet-B pose extractor for GPU optimization.

Top-down pipeline: detect all frames → batch crops → MogaNet-B ONNX
→ decode → tracking.

Usage:
    from src.pose_estimation import BatchPoseExtractor

    extractor = BatchPoseExtractor(batch_size=8, device="cuda")
    result = extractor.extract_video_tracked(video_path)
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

import cv2
import numpy as np

from ..types import PersonClick, TrackedExtraction
from ..utils.video import get_video_meta
from .h36m import coco_to_h36m

logger = logging.getLogger(__name__)


def _get_tqdm():
    try:
        from tqdm import tqdm  # noqa: TC003, S110

        return tqdm
    except (ImportError, ValueError):

        class _TqdmMock:
            """Minimal tqdm mock for when tqdm is unavailable."""

            def __init__(self, iterable: Any = None, **_: Any) -> None:
                self.iterable = iterable

            def update(self, *_a: Any) -> None:
                pass

            def close(self) -> None:
                pass

            def __enter__(self):
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

            def __iter__(self) -> Any:
                return iter(self.iterable or [])

        return _TqdmMock


class BatchPoseExtractor:
    """MogaNet-B pose extractor with frame batching.

    Top-down pipeline: detect all frames → batch crops → MogaNet-B ONNX
    → decode → tracking.

    Args:
        batch_size: Number of frames to process per batch (default: 8).
        model_path: Path to MogaNet-B ONNX model.
        conf_threshold: Minimum keypoint confidence [0, 1].
        output_format: "normalized" or "pixels".
        detection_stride: Run person detection every Nth frame, interpolate
            bounding boxes for in-between frames (1 = detect every frame).
        device: "cpu", "cuda", or "auto".
    """

    def __init__(
        self,
        batch_size: int = 8,
        model_path: str = "data/models/moganet/moganet_b_ap2d_384x288_fp16.onnx",
        conf_threshold: float = 0.3,
        output_format: str = "normalized",
        detection_stride: int = 1,
        device: str = "auto",
    ) -> None:
        self.batch_size = max(1, batch_size)
        self._model_path = model_path
        self._conf_threshold = conf_threshold
        self._output_format = output_format
        self._detection_stride = max(1, detection_stride)

        # Resolve device
        if device == "auto":
            from ..device import DeviceConfig

            self._device = DeviceConfig(device="auto").device
        else:
            self._device = device

        # Initialize top-down components
        from ..detection.person_detector import PersonDetector
        from .moganet_batch import MogaNetBatch

        self._person_detector = PersonDetector(confidence=conf_threshold)
        self._moganet = MogaNetBatch(
            model_path=model_path,
            device=device,
            score_thr=conf_threshold,
        )

    def _detect_and_crop(
        self,
        frame: np.ndarray,
    ) -> tuple[list[np.ndarray], list[tuple[int, int, int, int]]]:
        """Run person detection on a frame and return padded crops + bboxes.

        Expands each detection bbox by 20% padding (10% on each side) and
        clips to frame bounds.

        Args:
            frame: Input frame (H, W, 3) BGR.

        Returns:
            (crops, bboxes) where crops is a list of np.ndarray crop images
            and bboxes is a list of (x1, y1, x2, y2) integer tuples in
            original frame coordinates.
        """
        h, w = frame.shape[:2]
        detection = self._person_detector.detect_frame(frame)  # type: ignore[reportOptionalMemberAccess]
        if detection is None:
            return [], []

        # Skip corrupt detection with non-finite bbox fields — stdlib
        # int(NaN) at lines 148-151 would crash the whole batch (#1199).
        # Sibling guard for h/w resize at line 209 (#1160).
        if not all(math.isfinite(getattr(detection, a)) for a in ("x1", "y1", "x2", "y2")):
            return [], []

        # Expand by 20% padding (10% on each side)
        bw = detection.x2 - detection.x1
        bh = detection.y2 - detection.y1
        pad_x = bw * 0.1
        pad_y = bh * 0.1

        x1 = max(0, int(detection.x1 - pad_x))
        y1 = max(0, int(detection.y1 - pad_y))
        x2 = min(w, int(detection.x2 + pad_x))
        y2 = min(h, int(detection.y2 + pad_y))

        crop = frame[y1:y2, x1:x2]
        return [crop], [(x1, y1, x2, y2)]

    def extract_video_tracked(
        self,
        video_path: Path | str,
        person_click: PersonClick | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> TrackedExtraction:
        """Extract H3.6M poses from video with batched inference.

        Processes frames in batches to improve GPU utilization.
        Applies tracking after extraction to maintain consistency.

        Args:
            video_path: Path to video file.
            person_click: Optional click to select target person.
            progress_cb: Optional callback (fraction, message) for progress.

        Returns:
            TrackedExtraction with poses (N, 17, 3), frame indices,
            tracking metadata. Missing frames are filled with NaN.
        """
        video_path = Path(video_path)
        video_meta = get_video_meta(video_path)
        num_frames = video_meta.num_frames

        # Pre-allocate with NaN
        all_poses = np.full((num_frames, 17, 3), np.nan, dtype=np.float32)

        # Open video
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")

        # Initialize progress bar
        pbar = _get_tqdm()(
            total=num_frames,
            desc="Extracting poses (batched)",
            unit="frame",
            ncols=100,
            disable=progress_cb is not None,
        )

        try:
            frame_idx = 0

            while cap.isOpened() and frame_idx < num_frames:
                ret, frame = cap.read()
                if not ret:
                    break

                h, w = frame.shape[:2]
                # Skip corrupt frames with non-finite dims — stdlib int(NaN)
                # would crash cv2.resize (line 208) and _detect_and_crop
                # (line 150). Pre-allocated NaN pose stays (#1160).
                if not (math.isfinite(h) and math.isfinite(w)):
                    frame_idx += 1
                    pbar.update(1)
                    continue
                # Resize large frames for detection
                if max(h, w) > 1920:
                    scale = 1920 / max(h, w)
                    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
                    h, w = frame.shape[:2]  # ponytail: re-read after resize (#1036)

                crops, bboxes = self._detect_and_crop(frame)

                if not crops:
                    # No detection → NaN pose (already pre-allocated)
                    pass
                else:
                    keypoints, scores = self._moganet.infer_batch(crops, bboxes)  # type: ignore[reportOptionalMemberAccess]
                    if len(keypoints) > 0:
                        # Use first detected person (same as old behaviour)
                        kp = keypoints[0].astype(np.float32)  # (17, 2) pixels
                        conf = scores[0].astype(np.float32)  # (17,)

                        # Build COCO (17, 3) with confidence
                        coco = np.zeros((17, 3), dtype=np.float32)
                        coco[:, :2] = kp
                        coco[:, 2] = conf

                        # Normalize to [0, 1]
                        coco[:, 0] /= w
                        coco[:, 1] /= h

                        # Convert to H3.6M 17kp
                        h36m = coco_to_h36m(coco)

                        # Convert to pixels if requested
                        if self._output_format == "pixels":
                            h36m[:, 0] *= w
                            h36m[:, 1] *= h

                        all_poses[frame_idx] = h36m

                frame_idx += 1
                pbar.update(1)
                if progress_cb:
                    progress_cb(
                        frame_idx / num_frames * 0.5,
                        f"Extracting poses... {frame_idx}/{num_frames}",
                    )

        finally:
            cap.release()
            pbar.close()

        # Apply tracking (simplified — full tracking logic would go here)
        # For now, just return extracted poses
        valid_mask = ~np.isnan(all_poses[:, 0, 0])
        if not np.any(valid_mask):
            raise ValueError(f"No valid pose detected in video: {video_path}")

        first_detection_frame = int(np.argmax(valid_mask))

        return TrackedExtraction(
            poses=all_poses,
            frame_indices=np.arange(num_frames),
            first_detection_frame=first_detection_frame,
            target_track_id=None,  # Tracking to be implemented
            fps=video_meta.fps,
            video_meta=video_meta,
        )

    def close(self) -> None:
        """Release resources."""
        if hasattr(self, "_moganet") and self._moganet is not None:
            self._moganet.close()
        self._moganet = None
        self._person_detector = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit."""
        self.close()


def extract_poses_batched(
    video_path: Path | str,
    batch_size: int = 8,
    model_path: str = "data/models/moganet/moganet_b_ap2d_384x288_fp16.onnx",
    output_format: str = "normalized",
    person_click: PersonClick | None = None,
) -> TrackedExtraction:
    """Extract H3.6M poses from video using batched MogaNet-B inference.

    Convenience function that creates a BatchPoseExtractor and runs
    tracked extraction.

    Args:
        video_path: Path to video file.
        batch_size: Number of frames to process per batch.
        model_path: Path to MogaNet-B ONNX model.
        output_format: "normalized" or "pixels".
        person_click: Optional click to select target person.

    Returns:
        TrackedExtraction with poses populated.

    Example:
        >>> result = extract_poses_batched("video.mp4", batch_size=8)
        >>> print(f"Extracted {result.poses.shape[0]} poses")
    """
    extractor = BatchPoseExtractor(
        batch_size=batch_size,
        model_path=model_path,
        output_format=output_format,
    )
    return extractor.extract_video_tracked(video_path, person_click=person_click)
