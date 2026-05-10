"""Top-down pose extractor using PersonDetector + MogaNetBatch.

Architecture:
    Video → PersonDetector (YOLOv11n) → crop → MogaNetBatch (ONNX)
    → COCO 17kp → H3.6M 17kp

Key advantages:
    - Top-down: better accuracy on single-person sports
    - ONNX Runtime inference (no PyTorch dependency)
    - Existing tracking/post-processing preserved
"""

import importlib.util
import logging
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any

import cv2
import numpy as np

from ..detection.person_detector import PersonDetector
from ..tracking.skeletal_identity import compute_2d_skeletal_ratios
from ..tracking.tracklet_merger import TrackletMerger, build_tracklets
from ..types import PersonClick, TrackedExtraction
from ..utils.frame_buffer import AsyncFrameReader
from ..utils.video import get_video_meta
from ._frame_processor import FrameProcessor
from ._target_selector import TargetSelector
from ._track_state import TrackState
from ._track_validator import TrackValidator
from .h36m import coco_to_h36m
from .moganet_batch import MogaNetBatch

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


class PoseExtractor:
    """COCO pose extractor using PersonDetector + MogaNetBatch (top-down).

    Provides H3.6M 17-keypoint poses.

    Args:
        model_path: Path to MogaNet-B ONNX model.
        tracking_backend: "custom" feeds detections into our PoseTracker
            (OC-SORT + biometric Re-ID).
        tracking_mode: "auto", "sports2d", or "deepsort".
        conf_threshold: Minimum keypoint confidence to accept [0, 1].
        output_format: "normalized" for [0, 1] coords, "pixels" for absolute.
        frame_skip: Process every Nth frame (1 = every frame).
        device: "cpu", "cuda", or "auto".
    """

    def __init__(
        self,
        model_path: str = "data/models/moganet/moganet_b_ap2d_384x288.onnx",
        tracking_backend: str = "custom",
        tracking_mode: str = "auto",
        conf_threshold: float = 0.3,
        output_format: str = "normalized",
        frame_skip: int = 1,
        device: str = "auto",
    ) -> None:
        self._model_path = model_path
        self._tracking_backend = tracking_backend
        self._tracking_mode = tracking_mode
        self._conf_threshold = conf_threshold
        self._output_format = output_format
        self._frame_skip = max(1, frame_skip)
        self._device = device

        # Resolve device
        if device == "auto":
            from ..device import DeviceConfig

            self._device = DeviceConfig(device="auto").device

        self._person_detector = PersonDetector(confidence=conf_threshold)
        self._moganet = MogaNetBatch(
            model_path=model_path,
            device=self._device,
            score_thr=conf_threshold,
        )

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def _detect_and_crop(
        self,
        frame: np.ndarray,
        padding: float = 0.2,
    ) -> tuple[list[np.ndarray], list[tuple[int, int, int, int]]]:
        """Detect persons, expand bbox, crop from frame.

        Args:
            frame: BGR frame (H, W, 3).
            padding: Fraction to expand bbox on each side.

        Returns:
            (crops, bboxes) where crops is list of BGR crops and
            bboxes is list of (x1, y1, x2, y2) in original frame coords.
        """
        h, w = frame.shape[:2]
        detections = self._person_detector.detect_frame(frame)
        if detections is None:
            return [], []

        # PersonDetector returns single best detection
        # Convert to list for uniform handling
        if hasattr(detections, "x1"):
            detections = [detections]

        crops: list[np.ndarray] = []
        bboxes: list[tuple[int, int, int, int]] = []

        for det in detections:
            x1, y1, x2, y2 = float(det.x1), float(det.y1), float(det.x2), float(det.y2)
            bw = x2 - x1
            bh = y2 - y1

            # Expand by padding fraction
            pad_x = bw * padding
            pad_y = bh * padding
            x1 = max(0, int(x1 - pad_x))
            y1 = max(0, int(y1 - pad_y))
            x2 = min(w, int(x2 + pad_x))
            y2 = min(h, int(y2 + pad_y))

            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            crops.append(crop)
            bboxes.append((x1, y1, x2, y2))

        return crops, bboxes

    # ------------------------------------------------------------------
    # Core extraction
    # ------------------------------------------------------------------

    def extract_video_tracked(
        self,
        video_path: Path | str,
        person_click: PersonClick | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
        use_batch: bool = True,
        batch_size: int = 8,
    ) -> TrackedExtraction:
        """Extract H3.6M poses from video with tracking.

        Runs PersonDetector + MogaNetBatch on every frame, tracks all
        persons, and selects a single target person for output.

        Args:
            video_path: Path to video file.
            person_click: Optional click to select target person by
                proximity to the click point in the first few frames.
            progress_cb: Optional callback ``(fraction, message)`` for
                progress reporting (e.g. Gradio progress bar).
            use_batch: If True, collect all crops and run single batch.
            batch_size: Ignored (MogaNetBatch handles batching internally).

        Returns:
            TrackedExtraction with poses (N, 17, 3), frame_indices,
            tracking metadata.  Missing frames are filled with NaN.

        Raises:
            ValueError: If no pose is detected in any frame.
        """
        if use_batch:
            return self._extract_batch(
                video_path,
                person_click=person_click,
                progress_cb=progress_cb,
            )
        return self._extract_per_frame(
            video_path,
            person_click=person_click,
            progress_cb=progress_cb,
        )

    def _extract_per_frame(
        self,
        video_path: Path | str,
        person_click: PersonClick | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> TrackedExtraction:
        """Per-frame extraction path."""
        video_path = Path(video_path)
        video_meta = get_video_meta(video_path)
        num_frames = video_meta.num_frames

        all_poses = np.full((num_frames, 17, 3), np.nan, dtype=np.float32)

        track_state = TrackState(
            fps=video_meta.fps,
            tracking_backend=self._tracking_backend,
            tracking_mode=self._tracking_mode,
        )
        target_selector = TargetSelector(
            click_norm=(
                person_click.to_normalized(video_meta.width, video_meta.height)
                if person_click is not None
                else None
            ),
        )
        validator = TrackValidator()
        frame_processor = FrameProcessor(output_format=self._output_format)

        last_target_pose: np.ndarray | None = None
        last_target_ratios: np.ndarray | None = None
        target_lost_frame: int | None = None

        # Cache first frame for spatial reference
        cap_first = cv2.VideoCapture(str(video_path))
        if not cap_first.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")
        ret, first_frame = cap_first.read()
        cap_first.release()
        if not ret:
            raise RuntimeError(f"Failed to read first frame from video: {video_path}")

        pbar = _get_tqdm()(
            total=num_frames,
            desc="Extracting poses",
            unit="frame",
            ncols=100,
            disable=progress_cb is not None,
        )

        reader = AsyncFrameReader(
            video_path,
            buffer_size=16,
            frame_skip=self._frame_skip,
        )
        reader.start()

        try:
            while True:
                result = reader.get_frame()
                if result is None:
                    break
                frame_idx, frame = result
                h, w = frame.shape[:2]

                crops, bboxes = self._detect_and_crop(frame)
                if not crops:
                    pbar.update(self._frame_skip)
                    continue

                keypoints, scores = self._moganet.infer_batch(crops, bboxes)

                if keypoints.shape[0] == 0:
                    pbar.update(self._frame_skip)
                    continue

                h36m_poses = frame_processor.convert_keypoints(keypoints, scores, w, h)
                track_ids = track_state.update_tracking(
                    h36m_poses, frame=frame, frame_width=w, frame_height=h
                )
                track_state.record_frame(frame_idx, h36m_poses, track_ids)

                # Target selection via click
                selected = target_selector.select_target(h36m_poses, track_ids, frame_idx)
                if selected is not None:
                    track_state.target_track_id = selected

                # Fill target data
                if track_state.target_track_id is not None:
                    self._fill_target_pose(
                        all_poses,
                        frame_idx,
                        h36m_poses,
                        track_ids,
                        track_state,
                        validator,
                        last_target_pose,
                        last_target_ratios,
                        target_lost_frame,
                    )

                pbar.update(self._frame_skip)
                if progress_cb:
                    progress_cb(
                        frame_idx / num_frames * 0.3,
                        f"Extracting poses... {frame_idx}/{num_frames}",
                    )
        finally:
            reader.join()
            pbar.close()

        # Deferred auto-select by hits
        if track_state.target_track_id is None and track_state.track_hit_counts:
            track_state.target_track_id = track_state.auto_select_target()
            if track_state.target_track_id is not None:
                track_state.retroactive_fill(all_poses, track_state.target_track_id)

        # Post-hoc tracklet merging
        self._post_hoc_merge(all_poses, track_state.frame_track_data, track_state.target_track_id)

        valid_mask = ~np.isnan(all_poses[:, 0, 0])
        if not np.any(valid_mask):
            raise ValueError(f"No valid pose detected in video: {video_path}")
        first_detection_frame = int(np.argmax(valid_mask))

        return TrackedExtraction(
            poses=all_poses,
            frame_indices=np.arange(num_frames),
            first_detection_frame=first_detection_frame,
            target_track_id=track_state.target_track_id,
            fps=video_meta.fps,
            video_meta=video_meta,
            first_frame=first_frame,
        )

    def _extract_batch(
        self,
        video_path: Path | str,
        person_click: PersonClick | None = None,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> TrackedExtraction:
        """Batch extraction path: detect all frames, batch infer, then track."""
        video_path = Path(video_path)
        video_meta = get_video_meta(video_path)
        num_frames = video_meta.num_frames

        all_poses = np.full((num_frames, 17, 3), np.nan, dtype=np.float32)

        track_state = TrackState(
            fps=video_meta.fps,
            tracking_backend=self._tracking_backend,
            tracking_mode=self._tracking_mode,
        )
        target_selector = TargetSelector(
            click_norm=(
                person_click.to_normalized(video_meta.width, video_meta.height)
                if person_click is not None
                else None
            ),
        )
        validator = TrackValidator()
        frame_processor = FrameProcessor(output_format=self._output_format)

        last_target_pose: np.ndarray | None = None
        last_target_ratios: np.ndarray | None = None
        target_lost_frame: int | None = None

        # Read first frame for spatial reference
        cap_first = cv2.VideoCapture(str(video_path))
        if not cap_first.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")
        ret, first_frame = cap_first.read()
        cap_first.release()
        if not ret:
            raise RuntimeError(f"Failed to read first frame from video: {video_path}")

        # Read all frames (respecting frame_skip)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")

        frames_to_process: list[np.ndarray] = []
        frame_indices: list[int] = []

        try:
            for idx in _get_tqdm()(
                range(num_frames), desc="Reading frames", unit="frame", ncols=100
            ):
                if idx % self._frame_skip != 0:
                    continue
                ret, frame = cap.read()
                if not ret:
                    break
                frames_to_process.append(frame)
                frame_indices.append(idx)
        finally:
            cap.release()

        if not frames_to_process:
            raise ValueError(f"No frames read from video: {video_path}")

        # Detect + collect crops across all frames
        all_crops: list[np.ndarray] = []
        all_bboxes: list[tuple[int, int, int, int]] = []
        frame_detection_counts: list[int] = []

        for frame in frames_to_process:
            crops, bboxes = self._detect_and_crop(frame)
            all_crops.extend(crops)
            all_bboxes.extend(bboxes)
            frame_detection_counts.append(len(crops))

        # Batch inference on all crops at once
        if all_crops:
            batch_keypoints, batch_scores = self._moganet.infer_batch(all_crops, all_bboxes)
        else:
            batch_keypoints = np.zeros((0, 17, 2), dtype=np.float32)
            batch_scores = np.zeros((0, 17), dtype=np.float32)

        # Distribute results back to frames
        pbar = _get_tqdm()(
            total=len(frames_to_process),
            desc="Batch extracting poses",
            unit="frame",
            ncols=100,
            disable=progress_cb is not None,
        )

        kp_offset = 0
        for frame_idx, frame in zip(frame_indices, frames_to_process, strict=True):
            h, w = frame.shape[:2]
            n_det = frame_detection_counts.pop(0)

            if n_det == 0:
                pbar.update(1)
                if progress_cb:
                    progress_cb(
                        frame_idx / num_frames * 0.3,
                        f"Batch extracting poses... {frame_idx}/{num_frames}",
                    )
                continue

            keypoints = batch_keypoints[kp_offset : kp_offset + n_det]
            scores = batch_scores[kp_offset : kp_offset + n_det]
            kp_offset += n_det

            h36m_poses = frame_processor.convert_keypoints(keypoints, scores, w, h)
            track_ids = track_state.update_tracking(
                h36m_poses, frame=frame, frame_width=w, frame_height=h
            )
            track_state.record_frame(frame_idx, h36m_poses, track_ids)

            # Target selection via click
            selected = target_selector.select_target(h36m_poses, track_ids, frame_idx)
            if selected is not None:
                track_state.target_track_id = selected

            # Fill target data
            if track_state.target_track_id is not None:
                self._fill_target_pose(
                    all_poses,
                    frame_idx,
                    h36m_poses,
                    track_ids,
                    track_state,
                    validator,
                    last_target_pose,
                    last_target_ratios,
                    target_lost_frame,
                )

            pbar.update(1)
            if progress_cb:
                progress_cb(
                    frame_idx / num_frames * 0.3,
                    f"Batch extracting poses... {frame_idx}/{num_frames}",
                )

        pbar.close()

        # Deferred auto-select by hits
        if track_state.target_track_id is None and track_state.track_hit_counts:
            track_state.target_track_id = track_state.auto_select_target()
            if track_state.target_track_id is not None:
                track_state.retroactive_fill(all_poses, track_state.target_track_id)

        # Post-hoc tracklet merging
        self._post_hoc_merge(all_poses, track_state.frame_track_data, track_state.target_track_id)

        valid_mask = ~np.isnan(all_poses[:, 0, 0])
        if not np.any(valid_mask):
            raise ValueError(f"No valid pose detected in video: {video_path}")
        first_detection_frame = int(np.argmax(valid_mask))

        return TrackedExtraction(
            poses=all_poses,
            frame_indices=np.arange(num_frames),
            first_detection_frame=first_detection_frame,
            target_track_id=track_state.target_track_id,
            fps=video_meta.fps,
            video_meta=video_meta,
            first_frame=first_frame,
        )

    def _fill_target_pose(
        self,
        all_poses: np.ndarray,
        frame_idx: int,
        h36m_poses: np.ndarray,
        track_ids: list[int],
        track_state: TrackState,
        validator: TrackValidator,
        last_target_pose: np.ndarray | None,
        last_target_ratios: np.ndarray | None,
        target_lost_frame: int | None,
    ) -> None:
        """Fill target pose for current frame, handling stolen detection."""
        target_track_id = track_state.target_track_id
        found = False
        stolen = False
        for p, tid in enumerate(track_ids):
            if tid == target_track_id:
                if last_target_pose is not None and validator.is_stolen(
                    h36m_poses[p], last_target_pose, last_target_ratios
                ):
                    stolen = True
                    break
                all_poses[frame_idx] = h36m_poses[p]
                last_target_pose = h36m_poses[p].copy()
                last_target_ratios = compute_2d_skeletal_ratios(h36m_poses[p])
                target_lost_frame = None
                found = True
                break

        if stolen:
            all_poses[frame_idx] = np.full((17, 3), np.nan, dtype=np.float32)
            found = False

        if (not found or stolen) and last_target_pose is not None:
            if target_lost_frame is None:
                target_lost_frame = frame_idx
            if frame_idx - target_lost_frame <= TrackValidator.MAX_LOST_FRAMES:
                best_dist = float("inf")
                best_new_tid: int | None = None
                best_new_pose: np.ndarray | None = None
                for p, tid in enumerate(track_ids):
                    if stolen and tid == target_track_id:
                        continue
                    score = validator.migration_score(
                        h36m_poses[p],
                        last_target_pose,
                        elapsed=frame_idx - target_lost_frame,
                    )
                    if score < best_dist:
                        best_dist = score
                        best_new_tid = tid
                        best_new_pose = h36m_poses[p]
                if (
                    best_new_tid is not None
                    and best_dist < TrackValidator.MIGRATION_THRESHOLD
                    and best_new_pose is not None
                ):
                    track_state.target_track_id = best_new_tid
                    all_poses[frame_idx] = best_new_pose
                    last_target_pose = best_new_pose.copy()
                    last_target_ratios = compute_2d_skeletal_ratios(best_new_pose)
                    target_lost_frame = None
                    track_state.retroactive_fill(all_poses, track_state.target_track_id)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    @staticmethod
    def _build_person_grid(
        best_frame: np.ndarray,
        persons: list[dict],
    ) -> str:
        """Нарисовать bbox + номер на полном кадре.

        Авто-контраст: измеряет яркость фона и выбирает светлую/тёмную рамку.
        Анти-перекрытие: сдвигает метки при наложении.

        Args:
            best_frame: Кадр (H, W, 3) BGR.
            persons: Список dict с ключами:
                - best_kps: (17, 3) нормализованные H3.6M ключевые точки
                - hits: int
                - best_conf: float

        Returns:
            Путь к сохранённому изображению.
        """
        if not persons:
            return ""

        import tempfile

        preview = best_frame.copy()
        frame_h, frame_w = best_frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        thickness = 1

        # Собираем данные для рисования
        placements: list[tuple[int, int, int, int, int, int, float, int]] = []
        for person in persons:
            kps = person["best_kps"]
            valid = kps[kps[:, 2] > 0.1]
            if len(valid) < 3:
                continue
            bx1 = int(np.min(valid[:, 0]) * frame_w)
            by1 = int(np.min(valid[:, 1]) * frame_h)
            bx2 = int(np.max(valid[:, 0]) * frame_w)
            by2 = int(np.max(valid[:, 1]) * frame_h)
            cx = (bx1 + bx2) // 2
            iy = int(np.clip(by1, 0, frame_h - 1))
            ix = int(np.clip(cx, 0, frame_w - 1))
            brightness = float(preview[iy, ix].mean())
            hits = person["hits"]
            placements.append((cx, 0, bx1, by1, bx2, by2, brightness, hits))

        # Анти-перекрытие меток
        occupied: list[tuple[int, int, int, int]] = []

        for i, (_cx, _cy, bx1, by1, bx2, by2, bg_brightness, hits) in enumerate(placements):
            is_dark = bg_brightness < 128
            color = (255, 255, 255) if is_dark else (0, 0, 0)

            # Bbox
            cv2.rectangle(preview, (bx1, by1), (bx2, by2), color, 1, cv2.LINE_AA)

            # Метка с номером
            label = f" {i + 1} ({hits}) "
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            pad = 3
            tag_w = tw + 2 * pad
            tag_h = th + baseline + 2 * pad

            lx = bx1
            ly = by1 - tag_h - 2
            lx = max(2, min(lx, frame_w - tag_w - 2))
            ly = max(2, ly)

            # Анти-перекрытие
            for _ in range(10):
                overlap = False
                for ox1, oy1, ox2, oy2 in occupied:
                    if lx < ox2 and lx + tag_w > ox1 and ly < oy2 and ly + tag_h > oy1:
                        ly = oy2 + 2
                        overlap = True
                        break
                if not overlap:
                    break

            occupied.append((lx, ly, lx + tag_w, ly + tag_h))

            # Полупрозрачная плашка
            overlay = preview.copy()
            cv2.rectangle(overlay, (lx, ly), (lx + tag_w, ly + tag_h), color, -1)
            cv2.addWeighted(overlay, 0.7, preview, 0.3, 0, dst=preview)

            # Текст (инвертированный цвет)
            text_color = (0, 0, 0) if is_dark else (255, 255, 255)
            cv2.putText(
                preview,
                label,
                (lx + pad, ly + pad + th),
                font,
                font_scale,
                text_color,
                thickness,
                cv2.LINE_AA,
            )

        preview_path = str(
            Path(tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name).with_name("person_preview.jpg")  # noqa: SIM115
        )
        cv2.imwrite(preview_path, preview)
        return preview_path

    def preview_persons(
        self,
        video_path: Path | str,
        num_frames: int = 30,
    ) -> list[dict]:
        """Preview all detected persons in the first few frames.

        Runs PersonDetector + MogaNetBatch on the first ``num_frames``
        frames and returns a summary for each tracked person so the user
        can choose which one to follow.

        Args:
            video_path: Path to video file.
            num_frames: Number of frames to scan (default 30).

        Returns:
            Tuple of (list of dicts, preview_path)::

                {
                    "track_id": int,
                    "hits": int,
                    "bbox": (x1, y1, x2, y2),  # normalized [0,1]
                    "first_frame": int,
                    "mid_hip": (x, y),          # normalized
                }

            preview_path: Path to person grid preview image.
        """
        video_path = Path(video_path)
        video_meta = get_video_meta(video_path)

        if self._tracking_backend == "custom":
            from ..detection.pose_tracker import PoseTracker as CustomPoseTracker

            custom_tracker = CustomPoseTracker(max_disappeared=30, min_hits=2, fps=video_meta.fps)
        else:
            custom_tracker = None  # type: ignore[assignment]

        # Новый трекинг (Sports2D / DeepSORT)
        resolved_mode = self._resolve_tracking_mode()
        sports2d_tracker = None
        deepsort_tracker = None
        if resolved_mode == "sports2d":
            from ..tracking.sports2d import Sports2DTracker

            sports2d_tracker = Sports2DTracker(max_disappeared=30, fps=video_meta.fps)
        elif resolved_mode == "deepsort":
            from ..tracking.deepsort_tracker import DeepSORTTracker

            deepsort_tracker = DeepSORTTracker(max_age=30, embedder_gpu=True)

        next_internal_id = 0
        person_data: dict[int, dict] = {}

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")

        best_frame: np.ndarray | None = None

        try:
            for frame_idx in _get_tqdm()(
                range(num_frames), desc="Previewing persons", unit="frame", ncols=100
            ):
                ret, frame = cap.read()
                if not ret:
                    break

                h, w = frame.shape[:2]
                if best_frame is None:
                    best_frame = frame.copy()

                crops, bboxes = self._detect_and_crop(frame)
                if not crops:
                    if custom_tracker is not None:
                        custom_tracker.update(np.empty((0, 17, 2), dtype=np.float32))
                    continue

                keypoints, scores = self._moganet.infer_batch(crops, bboxes)
                if keypoints.shape[0] == 0:
                    continue

                n_persons = keypoints.shape[0]
                h36m_poses = np.zeros((n_persons, 17, 3), dtype=np.float32)

                for p in range(n_persons):
                    coco = np.zeros((17, 3), dtype=np.float32)
                    coco[:, :2] = keypoints[p].astype(np.float32)
                    coco[:, 2] = scores[p].astype(np.float32)
                    coco[:, 0] /= w
                    coco[:, 1] /= h
                    h36m_poses[p] = coco_to_h36m(coco)

                # Track association
                if sports2d_tracker is not None:
                    track_ids = sports2d_tracker.update(h36m_poses[:, :, :2], h36m_poses[:, :, 2])
                elif deepsort_tracker is not None:
                    track_ids = deepsort_tracker.update(
                        h36m_poses[:, :, :2],
                        h36m_poses[:, :, 2],
                        frame=frame,
                        frame_width=w,
                        frame_height=h,
                    )
                elif custom_tracker is not None:
                    track_ids = custom_tracker.update(h36m_poses[:, :, :2], h36m_poses[:, :, 2])
                else:
                    track_ids = list(range(next_internal_id, next_internal_id + n_persons))
                    next_internal_id += n_persons

                for p, tid in enumerate(track_ids):
                    if tid not in person_data:
                        person_data[tid] = {
                            "hits": 0,
                            "best_conf": 0.0,
                            "best_kps": None,
                            "best_frame": frame_idx,
                            "first_frame": frame_idx,
                        }
                    person_data[tid]["hits"] += 1
                    avg_conf = float(np.mean(h36m_poses[p, :, 2]))
                    if avg_conf > person_data[tid]["best_conf"]:
                        person_data[tid]["best_conf"] = avg_conf
                        person_data[tid]["best_kps"] = h36m_poses[p].copy()
                        person_data[tid]["best_frame"] = frame_idx
        finally:
            cap.release()

        # Build person grid preview
        preview_path: str | None = None
        if best_frame is not None and person_data:
            persons_for_grid = []
            for _tid, data in sorted(
                person_data.items(), key=lambda kv: kv[1]["hits"], reverse=True
            ):
                if data["best_kps"] is not None:
                    valid = data["best_kps"][data["best_kps"][:, 2] > 0.1]
                    if len(valid) >= 3:
                        persons_for_grid.append(data)
            if persons_for_grid:
                preview_path = PoseExtractor._build_person_grid(best_frame, persons_for_grid)

        # Build output with deduplication
        output: list[dict] = []
        preview_path_out = preview_path
        min_hits = max(2, num_frames // 10)

        for tid, data in sorted(person_data.items(), key=lambda kv: kv[1]["hits"], reverse=True):
            if data["hits"] < min_hits:
                continue
            kps = data["best_kps"]
            if kps is None:
                continue
            valid = kps[kps[:, 2] > 0.1]
            if len(valid) < 3:
                continue
            x1, y1 = float(np.min(valid[:, 0])), float(np.min(valid[:, 1]))
            x2, y2 = float(np.max(valid[:, 0])), float(np.max(valid[:, 1]))

            # NMS: skip if this bbox overlaps heavily with a better (more hits) one
            skip = False
            for existing in output:
                ex1, ey1, ex2, ey2 = existing["bbox"]
                ix1 = max(x1, ex1)
                iy1 = max(y1, ey1)
                ix2 = min(x2, ex2)
                iy2 = min(y2, ey2)
                inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                area_a = (x2 - x1) * (y2 - y1)
                area_b = (ex2 - ex1) * (ey2 - ey1)
                union = area_a + area_b - inter
                if union > 0 and inter / union > 0.5:
                    skip = True
                    break
            if skip:
                continue

            # Mid-hip (H3.6M: LHIP=4, RHIP=1)
            mid_hip_x = float((kps[4, 0] + kps[1, 0]) / 2)
            mid_hip_y = float((kps[4, 1] + kps[1, 1]) / 2)
            output.append(
                {
                    "track_id": tid,
                    "hits": data["hits"],
                    "bbox": (x1, y1, x2, y2),
                    "first_frame": data["first_frame"],
                    "mid_hip": (mid_hip_x, mid_hip_y),
                }
            )

        return output, preview_path_out  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_tracking_mode(self) -> str:
        """Разрешить 'auto' в конкретный режим трекинга."""
        if self._tracking_mode != "auto":
            return self._tracking_mode
        try:
            if importlib.util.find_spec("deep_sort_realtime") is not None:
                logger.info("Авто-выбор: DeepSORT (deep-sort-realtime доступен)")
                return "deepsort"
        except (ImportError, ModuleNotFoundError):
            pass
        logger.info("Авто-выбор: Sports2D (Венгерский алгоритм)")
        return "sports2d"

    def _post_hoc_merge(
        self,
        all_poses: np.ndarray,
        frame_track_data: dict[int, dict[int, np.ndarray]],
        target_track_id: int | None,
    ) -> None:
        """Post-hoc tracklet merging for occlusion recovery."""
        valid_mask_pre = ~np.isnan(all_poses[:, 0, 0])
        if valid_mask_pre.all() or not frame_track_data or target_track_id is None:
            return
        model_3d = Path("data/models/motionagformer-s-ap3d.onnx")
        identity_ext = None
        if model_3d.exists():
            from ..tracking.skeletal_identity import SkeletalIdentityExtractor

            identity_ext = SkeletalIdentityExtractor(
                model_path=model_3d,
                device="auto",
            )
        merger = TrackletMerger(
            identity_extractor=identity_ext,
            similarity_threshold=0.80,
        )
        tracklets = build_tracklets(frame_track_data)
        target_tracklet = None
        for t in tracklets:
            if t.track_id == target_track_id:
                target_tracklet = t
                break
        if target_tracklet is None:
            return
        valid_frames = np.where(valid_mask_pre)[0]
        if len(valid_frames) == 0:
            return
        last_valid = int(valid_frames[-1])
        num_frames = all_poses.shape[0]
        if last_valid >= num_frames - 1:
            return
        candidates = [t for t in tracklets if t.track_id != target_track_id]
        match = merger.find_best_match(target_tracklet, candidates)
        if match is None:
            return
        for f in match.frames:
            if f < num_frames and np.isnan(all_poses[f, 0, 0]):
                all_poses[f] = match.poses.get(f, all_poses[f])
        logger.info(
            "Post-hoc merge: filled %d frames from track %d",
            sum(1 for f in match.frames if f < num_frames and np.isnan(all_poses[f, 0, 0])),
            match.track_id,
        )

    def close(self) -> None:
        """Release resources."""
        self._moganet.close()

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


def extract_poses(
    video_path: Path | str,
    model_path: str = "data/models/moganet/moganet_b_ap2d_384x288.onnx",
    output_format: str = "normalized",
    person_click: PersonClick | None = None,
) -> TrackedExtraction:
    """Extract H3.6M poses from video using PersonDetector + MogaNetBatch.

    Convenience function that creates a PoseExtractor and runs
    tracked extraction.

    Args:
        video_path: Path to video file.
        model_path: Path to MogaNet-B ONNX model.
        output_format: ``"normalized"`` or ``"pixels"``.
        person_click: Optional click to select target person.

    Returns:
        TrackedExtraction with poses populated.
    """
    extractor = PoseExtractor(model_path=model_path, output_format=output_format)
    return extractor.extract_video_tracked(video_path, person_click=person_click)
