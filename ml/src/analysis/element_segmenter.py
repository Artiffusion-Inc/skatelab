"""Automatic element segmentation for skating videos.

Detects element boundaries using motion energy analysis and classifies
each segment using rule-based heuristics.

ML backend: set `tas_model_path` to use BiGRU+RF instead of rules.
Method "tas_ml_v2" uses BiGRUTASRefiner + Skeleton1DCNN v2 pipeline.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import binary_opening

from ..types import (
    ElementPhase,
    ElementSegment,
    NormalizedPose,
    SegmentationResult,
)
from ..utils.geometry import get_mid_hip, smooth_signal

if TYPE_CHECKING:
    from ..utils.video import VideoMeta


class ElementSegmenter:
    """Automatic segmentation of skating video into elements.

    Uses motion energy analysis to detect stillness periods between elements,
    then classifies each segment using rule-based heuristics.

    ML backends:
        - set `tas_model_path` to use BiGRU+RF (tas_ml) or v2 pipeline (tas_ml_v2).
        - "tas_ml_v2" is preferred when model path is set.
    """

    def __init__(
        self,
        stillness_threshold: float | None = None,
        min_still_duration: float = 0.5,
        min_segment_duration: float = 0.5,
        boundary_window: int = 10,
        tas_model_path: Path | str | None = None,
        tas_classifier_path: Path | str | None = None,
    ) -> None:
        """Initialize element segmenter.

        Args:
            stillness_threshold: Motion energy threshold for stillness (auto if None).
            min_still_duration: Minimum seconds for stillness period (default 0.5s).
            min_segment_duration: Minimum seconds for valid segment (default 0.5s).
            boundary_window: Frames to search for boundary refinement (default 10).
            tas_model_path: Path to BiGRU checkpoint for ML-based segmentation.
            tas_classifier_path: Path to RF classifier for fine element types.
        """
        self._stillness_threshold = stillness_threshold
        self._min_still_duration = min_still_duration
        self._min_segment_duration = min_segment_duration
        self._boundary_window = boundary_window
        self._tas_model_path = Path(tas_model_path) if tas_model_path else None
        self._tas_classifier_path = Path(tas_classifier_path) if tas_classifier_path else None
        self._tas_segmenter: object | None = None

    def _get_tas_segmenter(self) -> object | None:
        """Lazy init TAS segmenter."""
        if self._tas_segmenter is not None:
            return self._tas_segmenter
        if self._tas_model_path is None or not self._tas_model_path.exists():
            return None
        from ..tas.inference import TASElementSegmenter

        self._tas_segmenter = TASElementSegmenter(
            model_path=self._tas_model_path,
            classifier_path=self._tas_classifier_path,
            min_segment_duration=self._min_segment_duration,
        )
        return self._tas_segmenter

    def segment(
        self,
        poses: NormalizedPose,
        video_path: Path,
        video_meta: "VideoMeta",
        method: str = "adaptive",
    ) -> SegmentationResult:
        """Detect element boundaries in video.

        Args:
            poses: NormalizedPose sequence (num_frames, num_joints, 2).
            video_path: Path to original video file.
            video_meta: Video metadata.
            method: Segmentation strategy. One of:
                "adaptive" — try tas_ml_v2, then rule-based (default).
                "motion_energy" — rule-based only.
                "tas_ml" — v1 ML backend (BiGRU+RF).
                "tas_ml_v2" — v2 ML backend (BiGRUTASRefiner + Skeleton1DCNN).

        Returns:
            SegmentationResult with detected segments.
        """
        # Degenerate input (<2 frames) — np.diff / np.pad(mode="edge") in
        # _compute_motion_energy crash on an empty axis (no edge value to
        # replicate). Degrade gracefully to an empty result instead of
        # crashing the process_video_task worker job (#476).
        if len(poses) < 2:
            return SegmentationResult(
                segments=[],
                video_path=video_path,
                video_meta=video_meta,
                method=method,
                confidence=0.0,
            )
        # ML v2 backend (preferred when model path is set)
        if method in ("adaptive", "tas_ml_v2") and self._tas_model_path is not None:
            result = self._segment_with_tas_v2(poses, video_meta.fps, video_meta)
            if result is not None:
                return result
            # Fallback if v2 fails

        # ML v1 backend
        if method == "tas_ml":
            tas = self._get_tas_segmenter()
            if tas is not None:
                return self._segment_with_tas(tas, poses, video_path, video_meta)

        # Stage 1: Compute motion energy signal
        motion_energy = self._compute_motion_energy(poses)

        # Stage 2: Detect stillness periods (element separators)
        stillness_mask = self._detect_stillness(motion_energy, video_meta.fps)

        # Stage 3: Extract active segments
        active_segments = self._extract_active_segments(stillness_mask)

        # Stage 4: Filter short segments
        min_frames = int(self._min_segment_duration * video_meta.fps)
        filtered_segments = [(s, e) for s, e in active_segments if e - s >= min_frames]

        # Stage 5: Refine boundaries using velocity/pose changes
        refined_segments = self._refine_boundaries(poses, filtered_segments)

        # Stage 6: Classify each segment
        classified_segments = self._classify_segments(poses, refined_segments, video_meta.fps)

        # Stage 7: Compute overall confidence
        overall_confidence = self._compute_overall_confidence(classified_segments)

        return SegmentationResult(
            segments=classified_segments,
            video_path=video_path,
            video_meta=video_meta,
            method=method,
            confidence=overall_confidence,
        )

    def _segment_with_tas(
        self,
        tas_segmenter: Any,
        poses: NormalizedPose,
        video_path: Path,
        video_meta: "VideoMeta",
    ) -> SegmentationResult:
        """Run TAS ML segmentation and wrap result."""
        segs = tas_segmenter.segment(poses, fps=video_meta.fps)
        element_segs: list[ElementSegment] = []
        for seg in segs:
            element_segs.append(
                ElementSegment(
                    element_type=seg["element_type"],
                    start=seg["start"],
                    end=seg["end"],
                    confidence=seg["confidence"],
                )
            )
        return SegmentationResult(
            segments=element_segs,
            video_path=video_path,
            video_meta=video_meta,
            method="tas_ml",
            confidence=float(np.mean([s.confidence for s in element_segs]))
            if element_segs
            else 0.0,
        )

    def _segment_with_tas_v2(
        self,
        poses: NormalizedPose,
        fps: float,
        video_meta: "VideoMeta",
    ) -> SegmentationResult | None:
        """Segment using BiGRUTASRefiner + Skeleton1DCNN v2 pipeline."""

        segmenter = self._get_tas_segmenter()
        if segmenter is None:
            return None

        raw_segments = segmenter.segment(poses, fps=fps)
        if not raw_segments:
            return None

        segments: list[ElementSegment] = []
        for seg in raw_segments:
            phases = None
            seg_poses = poses[seg["start"] : seg["end"] + 1]
            # Try rule-based PhaseDetector for jump elements
            if seg["element_type"] == "Jump" and len(seg_poses) > 10:
                try:
                    from ..analysis.phase_detector import PhaseDetector

                    pd = PhaseDetector()
                    phase_result = pd.detect_phases(seg_poses, fps, seg["element_type"])
                    if phase_result and phase_result.phases:
                        phases = phase_result.phases
                except (ValueError, RuntimeError):
                    pass

            segments.append(
                ElementSegment(
                    element_type=seg["element_type"],
                    start=seg["start"],
                    end=seg["end"],
                    confidence=seg["confidence"],
                    phases=phases,
                    metadata={
                        "coarse_type": seg["element_type"],
                        # #813: fine label from optional RF classifier
                        # (None when no classifier loaded).
                        "fine_label": seg.get("fine_label"),
                    },
                )
            )

        return SegmentationResult(
            segments=segments,
            video_path=video_meta.path,
            video_meta=video_meta,
            method="tas_ml_v2",
            confidence=float(np.mean([s.confidence for s in segments])),
        )

    def _compute_motion_energy(self, poses: NormalizedPose) -> NDArray[np.float32]:
        """Compute per-frame motion energy from pose differences.

        Args:
            poses: NormalizedPose sequence (num_frames, num_joints, 2).

        Returns:
            Motion energy signal (num_frames,).
        """
        # Frame-to-frame difference
        diff = np.diff(poses, axis=0)  # (num_frames-1, num_joints, 2)

        # L2 norm per frame (sum of all joint movements)
        energy = np.linalg.norm(diff, axis=(1, 2))  # (num_frames-1,)

        # Pad to match original length
        energy = np.pad(energy, (1, 0), mode="edge")

        # Smooth with moving average to reduce noise
        energy = smooth_signal(energy, window=5)

        return energy.astype(np.float32)

    def _detect_stillness(
        self,
        motion_energy: NDArray[np.float32],
        fps: float,
    ) -> NDArray[np.bool_]:
        """Detect stillness periods (element separators).

        Args:
            motion_energy: Per-frame energy signal.
            fps: Frame rate.

        Returns:
            Boolean mask where True = stillness.
        """
        # Adaptive threshold if not provided
        adaptive = self._stillness_threshold is None
        if adaptive:
            # Use 25th percentile as threshold.
            # #985: np.nanpercentile (not np.percentile) — a NaN motion-energy
            # frame (occluded joint → NaN pose → NaN _compute_motion_energy)
            # propagates through np.percentile as NaN, collapsing `energy <
            # threshold` to all-False (NaN comparison always False) → no
            # element boundaries → whole video one segment. nanpercentile
            # ignores NaN, computing the threshold over finite frames so
            # low-energy finite frames still register as stillness.
            threshold = np.nanpercentile(motion_energy, 25)
        else:
            threshold = self._stillness_threshold

        # Binary mask: energy below threshold = stillness
        still = motion_energy < threshold

        # Degenerate adaptive case: when the signal is flat (e.g. all-zero
        # motion energy from a completely still video), the 25th percentile
        # equals the max, so `energy < threshold` marks NOTHING as still — the
        # whole video reads as "active". A flat low-energy signal means there
        # is no motion to segment, so classify every frame as still. (Explicit
        # thresholds already handle this: 0 < 0.1 is True for all-zero energy.)
        if adaptive and not still.any() and float(np.max(motion_energy)) <= float(threshold):
            still = np.ones_like(still)

        # Morphological opening to remove short noise bursts
        min_frames = int(self._min_still_duration * fps)
        if min_frames > 1:
            still = cast(
                "NDArray[np.bool_]",
                binary_opening(still, structure=np.ones(min_frames, dtype=bool)),
            )

        return still

    def _extract_active_segments(self, stillness_mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
        """Extract active segments from stillness mask.

        Args:
            stillness_mask: Boolean mask where True = stillness.

        Returns:
            List of (start_frame, end_frame) half-open tuples [start, end).
            Active segments are maximal runs of False (active) in the mask.
        """
        segments: list[tuple[int, int]] = []
        n = len(stillness_mask)
        i = 0
        while i < n:
            if not stillness_mask[i]:  # active
                start = i
                while i < n and not stillness_mask[i]:
                    i += 1
                segments.append((int(start), int(i)))  # half-open [start, end)
            else:
                i += 1
        return segments

    def _refine_boundaries(
        self,
        poses: NormalizedPose,
        segments: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        """Refine segment boundaries using velocity minima.

        Args:
            poses: NormalizedPose sequence.
            segments: List of (start, end) tuples.

        Returns:
            Refined list of (start, end) tuples.
        """
        if not segments:
            return segments

        refined = []

        # Compute hip velocity for boundary refinement
        hip_y = get_mid_hip(poses)[:, 1]
        velocity = np.gradient(hip_y)
        velocity_mag = np.abs(velocity)

        for start, end in segments:
            # Refine start boundary
            if start > self._boundary_window:
                search_start = start - self._boundary_window
                search_end = start + self._boundary_window
            else:
                search_start = 0
                search_end = min(start + self._boundary_window, len(poses))

            # Find velocity minimum in search window.
            # #972: np.argmin on a NaN-bearing window treats NaN as smallest
            # and snaps the boundary to the NaN frame (occluded hip). Use
            # nanargmin over finite frames; fall back to 0 when all-NaN
            # (sentinel, no crash — boundary left at search_start).
            window_vel = velocity_mag[search_start:search_end]
            if len(window_vel) > 0 and np.isfinite(window_vel).any():
                min_idx = int(np.nanargmin(window_vel))
                new_start = search_start + min_idx
            else:
                new_start = start

            # Refine end boundary
            if end + self._boundary_window < len(poses):
                search_start = max(0, end - self._boundary_window)
                search_end = end + self._boundary_window
            else:
                search_start = max(0, end - self._boundary_window)
                search_end = len(poses)

            window_vel = velocity_mag[search_start:search_end]
            if len(window_vel) > 0 and np.isfinite(window_vel).any():
                min_idx = int(np.nanargmin(window_vel))
                new_end = search_start + min_idx
            else:
                new_end = end

            # Ensure segment is valid
            if new_start < new_end:
                refined.append((int(new_start), int(new_end)))

        return refined

    def _classify_segments(
        self,
        poses: NormalizedPose,
        segments: list[tuple[int, int]],
        fps: float,
    ) -> list[ElementSegment]:
        """Classify each segment as an element type.

        Args:
            poses: Full video poses.
            segments: List of (start, end) tuples.
            fps: Frame rate.

        Returns:
            List of ElementSegment objects.
        """
        classified = []

        for start, end in segments:
            segment_poses = poses[start:end]

            # Extract features
            features = self._extract_segment_features(segment_poses, fps)

            # Classify by rules
            element_type, confidence = self._classify_by_rules(features)

            # Detect phases for this segment
            phases = self._detect_segment_phases(segment_poses, fps, element_type, start)

            # Create segment
            segment = ElementSegment(
                element_type=element_type,
                start=start,
                end=end,
                confidence=confidence,
                phases=phases,
                metadata=features,
            )

            classified.append(segment)

        return classified

    def _extract_segment_features(
        self,
        poses: NormalizedPose,
        fps: float,
    ) -> dict[str, float | int | bool]:
        """Extract features for classification.

        Args:
            poses: Segment poses.
            fps: Frame rate.

        Returns:
            Dictionary of features.
        """
        features: dict[str, float | int | bool] = {}

        # #922: occluded joint → NaN keypoint propagates through np.linalg.norm
        # (motion energy), np.arctan2 (shoulder rotation), np.gradient, and the
        # non-NaN-aware reductions (np.max/np.mean/np.std) into the metadata
        # feature dict → NaN features persisted in segment.metadata AND
        # _classify_by_rules reads rotation_speed_max as `NaN > 200` = False →
        # jump branch silently skipped → element misclassified as "unknown".
        # Guard at the feature-math trust boundary: replace NaN/inf keypoints
        # with 0.0 before any feature computation. No-op on all-finite input
        # (byte-identical features). Mirrors #979 extract_segment_features.
        poses = np.nan_to_num(poses, nan=0.0, posinf=0.0, neginf=0.0)

        # Duration
        num_frames = len(poses)
        # #505: fps=0.0 (cv2 returns 0.0 for broken-header/remuxed videos) makes
        # pure-int / 0.0 raise ZeroDivisionError, killing the worker job. Fall
        # back to 0.0 duration for a degenerate fps; the frame count is still
        # recorded. (types.py fps=0 is guarded by #499/#501; these analysis
        # siblings were missed.)
        features["duration_sec"] = round(num_frames / fps, 3) if fps > 0 else 0.0
        features["duration_frames"] = num_frames

        # Motion energy
        motion_energy = self._compute_motion_energy(poses)
        features["motion_energy_mean"] = float(np.mean(motion_energy))
        features["motion_energy_std"] = float(np.std(motion_energy))
        features["motion_energy_max"] = float(np.max(motion_energy))

        # Hip Y trajectory (for jumps)
        hip_y = get_mid_hip(poses)[:, 1]
        features["hip_y_range"] = float(np.max(hip_y) - np.min(hip_y))
        # #989: np.argmin on NaN-bearing hip_y treats NaN as smallest → returns
        # the NaN-frame index (occluded hip) instead of the real CoM peak. Use
        # nanargmin over finite frames; fall back to 0 when all-NaN (sentinel,
        # no crash). hip_y_range still leaks NaN separately (covered elsewhere).
        features["hip_y_min_idx"] = int(np.nanargmin(hip_y)) if np.isfinite(hip_y).any() else 0

        # Detect jump-like pattern
        hip_y_derivative = np.gradient(hip_y)
        has_takeoff = np.any(hip_y_derivative < -0.02)  # Rapid rise (negative Y is up)
        has_landing = np.any(hip_y_derivative > 0.02)  # Rapid descent
        features["has_jump_pattern"] = bool(has_takeoff and has_landing)

        # Edge indicator (for steps/turns)
        edge_ind = self._compute_edge_indicator(poses)
        features["edge_change_count"] = int(np.sum(np.abs(np.diff(edge_ind)) > 0.3))
        features["edge_indicator_mean"] = float(np.mean(np.abs(edge_ind)))

        # Rotation speed (shoulder axis).
        # #860: _compute_shoulder_rotation returns unwrapped radians, so
        # gradient is rad/s; convert to deg/s (×180/π) to match the deg/s-shaped
        # thresholds in _classify_by_rules (200/350/500). Without this a real
        # 1080 deg/s jump reads as 18.85 rad/s — below every threshold.
        shoulder_angles = self._compute_shoulder_rotation(poses)
        if len(shoulder_angles) > 0:
            rot_velocity = np.abs(np.gradient(shoulder_angles)) * fps * (180.0 / np.pi)
            features["rotation_speed_max"] = float(np.max(rot_velocity))
            features["rotation_speed_mean"] = float(np.mean(rot_velocity))
        else:
            features["rotation_speed_max"] = 0.0
            features["rotation_speed_mean"] = 0.0

        # Knee angle range
        knee_angles = self._compute_knee_angle_series(poses, side="left")
        if len(knee_angles) > 0:
            features["knee_angle_min"] = float(np.min(knee_angles))
            features["knee_angle_max"] = float(np.max(knee_angles))
            features["knee_angle_range"] = features["knee_angle_max"] - features["knee_angle_min"]
        else:
            features["knee_angle_min"] = 0.0
            features["knee_angle_max"] = 0.0
            features["knee_angle_range"] = 0.0

        return features

    def _classify_by_rules(self, features: dict[str, float | int | bool]) -> tuple[str, float]:
        """Rule-based element classification.

        Args:
            features: Extracted segment features.

        Returns:
            (element_type, confidence) tuple.
        """
        # Decision tree based on features

        # Check for jump (hip Y pattern + rotation)
        if features.get("has_jump_pattern", False):
            rotation_max = features.get("rotation_speed_max", 0)
            if not isinstance(rotation_max, bool) and rotation_max > 200:
                # Classify jump type by rotation speed
                if rotation_max > 500:
                    return "flip", 0.7
                elif rotation_max > 350:
                    return "toe_loop", 0.7
                else:
                    return "waltz_jump", 0.65
            elif not isinstance(rotation_max, bool) and rotation_max > 100:
                return "waltz_jump", 0.6

        # Check for turn/step (edge changes)
        edge_changes = features.get("edge_change_count", 0)
        if not isinstance(edge_changes, bool) and edge_changes > 0:
            return "three_turn", 0.7

        return "unknown", 0.3

    def _detect_segment_phases(
        self,
        poses: NormalizedPose,
        fps: float,
        element_type: str,
        global_start: int,
    ) -> ElementPhase | None:
        """Detect phases for a segment.

        Args:
            poses: Segment poses.
            fps: Frame rate.
            element_type: Element type.
            global_start: Global start frame offset.

        Returns:
            ElementPhase with adjusted frame indices, or None.
        """
        try:
            from . import phase_detector

            PhaseDetector = phase_detector.PhaseDetector

            detector = PhaseDetector()
            result = detector.detect_phases(poses, fps, element_type)

            # Adjust frame indices to global coordinates
            phases = result.phases
            return ElementPhase(
                name=element_type,
                start=phases.start + global_start,
                takeoff=phases.takeoff + global_start if phases.takeoff > 0 else 0,
                peak=phases.peak + global_start if phases.peak > 0 else 0,
                landing=phases.landing + global_start if phases.landing > 0 else 0,
                end=phases.end + global_start,
            )
        except Exception:
            # If phase detection fails, return None
            return None

    def _compute_overall_confidence(self, segments: list[ElementSegment]) -> float:
        """Compute overall segmentation confidence.

        Args:
            segments: List of classified segments.

        Returns:
            Overall confidence score [0, 1].
        """
        if not segments:
            return 0.0

        # Average of segment confidences
        return float(np.mean([s.confidence for s in segments]))

    def _compute_edge_indicator(self, poses: NormalizedPose) -> NDArray[np.float32]:
        """Compute edge indicator for step/turn detection.

        Uses foot velocity direction to estimate edge (inside/outside/flat).

        Args:
            poses: NormalizedPose sequence (H3.6M 17kp format).

        Returns:
            Edge indicator signal (+1=inside, -1=outside, 0=flat).
        """
        # Simplified: use foot velocity direction as edge indicator
        # For H3.6M format, use LFOOT and RFOOT keypoints
        from ..types import H36Key

        left_foot = poses[:, H36Key.LFOOT, :]
        right_foot = poses[:, H36Key.RFOOT, :]

        # Compute foot velocity (difference between consecutive frames)
        left_vel = np.diff(left_foot, axis=0, prepend=left_foot[:1])
        right_vel = np.diff(right_foot, axis=0, prepend=right_foot[:1])

        # Use x-component of velocity as edge indicator
        # (positive = outside edge, negative = inside edge)
        edge_left = np.sign(left_vel[:, 0])
        edge_right = np.sign(right_vel[:, 0])

        # Average both feet
        edge = (edge_left + edge_right) / 2

        return edge.astype(np.float32)

    def _compute_shoulder_rotation(self, poses: NormalizedPose) -> NDArray[np.float32]:
        """Compute shoulder rotation angle over time.

        Args:
            poses: NormalizedPose sequence (H3.6M 17kp format).

        Returns:
            Shoulder rotation angles in radians.
        """
        from ..types import H36Key

        left_shoulder = poses[:, H36Key.LSHOULDER, :]
        right_shoulder = poses[:, H36Key.RSHOULDER, :]

        # Compute shoulder axis vector
        shoulder_vector = right_shoulder - left_shoulder

        # Compute angle relative to horizontal.
        # #860: np.unwrap before gradient — arctan2 wraps to (-π, π], so a
        # shoulder rotation past ±π produces a 2π-per-frame gradient spike
        # (physically impossible) that becomes rotation_speed_max. Unwrap makes
        # the angle monotonic across the wrap boundary so gradient reflects the
        # real spin rate.
        angles = np.unwrap(np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0]))

        return angles.astype(np.float32)

    def _compute_knee_angle_series(
        self,
        poses: NormalizedPose,
        side: str = "left",
    ) -> NDArray[np.float32]:
        """Compute knee angle series.

        Args:
            poses: NormalizedPose sequence (H3.6M 17kp format).
            side: "left" or "right".

        Returns:
            Knee angles in degrees.
        """
        from ..types import H36Key
        from ..utils.geometry import angle_3pt

        if side == "left":
            hip_idx = H36Key.LHIP
            knee_idx = H36Key.LKNEE
            ankle_idx = H36Key.LFOOT
        else:
            hip_idx = H36Key.RHIP
            knee_idx = H36Key.RKNEE
            ankle_idx = H36Key.RFOOT

        angles = []
        for i in range(len(poses)):
            hip = poses[i, hip_idx]
            knee = poses[i, knee_idx]
            ankle = poses[i, ankle_idx]

            # Skip if any point is at origin (missing data)
            if np.allclose(hip, 0) or np.allclose(knee, 0) or np.allclose(ankle, 0):
                angles.append(0.0)
            else:
                angle = angle_3pt(hip, knee, ankle)
                angles.append(angle)

        return np.array(angles, dtype=np.float32)
