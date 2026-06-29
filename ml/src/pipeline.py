"""Main analysis pipeline orchestrator.

H3.6M Architecture:
    This pipeline uses H3.6M 17-keypoint format as the primary format.
    2D extraction: PoseExtractor (PersonDetector + MogaNetBatch)

Pipeline stages:
    1. Extract & track: PoseExtractor.extract_video_tracked() + gap fill + spatial ref
    2. Normalization
    3. Temporal smoothing (One-Euro Filter)
    4. Phase detection
    5. Biomechanics metrics
    6. Reference comparison (DTW)
    7. Recommendations
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import numpy as np

from .device import DeviceConfig
from .types import AnalysisReport, ElementPhase, PersonClick, SegmentationResult
from .utils.geometry import calculate_com_trajectory
from .utils.profiling import PipelineProfiler
from .utils.video import VideoMeta, get_video_meta

if TYPE_CHECKING:
    from pathlib import Path

    from .alignment import MotionAligner, MotionDTWAligner
    from .analysis.element_defs import ElementDef
    from .analysis.phase_detector import PhaseDetector
    from .analysis.recommender import Recommender
    from .detection import PersonDetector
    from .pose_estimation.normalizer import PoseNormalizer
    from .pose_estimation.pose_extractor import PoseExtractor
    from .references import ReferenceStore
    from .utils.smoothing import OneEuroFilterConfig, PoseSmoother


class AnalysisPipeline:
    """Main pipeline for skating technique analysis.

    H3.6M Architecture:
        - 2D poses: PoseExtractor (17 keypoints, normalized [0,1], MogaNet-B backend)
    """

    def __init__(
        self,
        reference_store: ReferenceStore | None = None,  # type: ignore[valid-type]
        device: str | DeviceConfig = "auto",
        enable_smoothing: bool = True,
        smoothing_config: OneEuroFilterConfig | None = None,  # type: ignore[valid-type]
        person_click: PersonClick | None = None,
        reestimate_camera: bool = False,
        profiler: PipelineProfiler | None = None,
    ) -> None:
        """Initialize analysis pipeline.

        Args:
            reference_store: ReferenceStore for loading expert references.
            device: Device configuration — ``"auto"`` (default), ``"cuda"``, ``"cpu"``,
                or a DeviceConfig instance for custom behavior.
            enable_smoothing: Whether to apply One-Euro Filter temporal smoothing.
            smoothing_config: Optional custom smoothing configuration.
            person_click: Optional click point to select target person in multi-person videos.
            reestimate_camera: Enable per-frame camera re-estimation for moving cameras.
            profiler: Optional PipelineProfiler for recording stage timings.
        """
        self._reference_store = reference_store
        self._device_config = DeviceConfig(device) if isinstance(device, str) else device
        self._enable_smoothing = enable_smoothing
        self._smoothing_config = smoothing_config
        self._person_click = person_click
        self._reestimate_camera = reestimate_camera
        self._profiler = profiler or PipelineProfiler()

        # Components will be lazy-loaded
        self._detector: PersonDetector | None = None  # type: ignore[valid-type]
        self._pose_2d_extractor: PoseExtractor | None = None  # type: ignore[valid-type]
        self._normalizer: PoseNormalizer | None = None  # type: ignore[valid-type]
        self._smoother: PoseSmoother | None = None  # type: ignore[valid-type]
        self._phase_detector: PhaseDetector | None = None  # type: ignore[valid-type]
        self._analyzer_factory: type | None = None
        self._aligner: MotionAligner | MotionDTWAligner | None = None  # type: ignore[valid-type]
        self._recommender: Recommender | None = None  # type: ignore[valid-type]
        self._3d_lifter = None  # type: ignore[valid-type]

    def _extract_and_track(self, video_path: Path, meta: VideoMeta) -> tuple[np.ndarray, int]:
        """Extract poses with tracking, gap filling, and spatial compensation.

        Combines extraction, pre-roll trimming, gap filling, and camera
        compensation into a single method.

        Args:
            video_path: Path to video file.
            meta: Video metadata (width, height, fps, etc.).

        Returns:
            (compensated_h36m, frame_offset) — poses (N, 17, 3) normalized,
            frame_offset = first_detection_frame index.
        """
        # 1. Lazy-init extractor (model download + ONNX session)
        t0 = time.perf_counter()
        extractor = self._get_pose_2d_extractor()
        self._profiler.record("extractor_init", time.perf_counter() - t0)

        if extractor is None:
            msg = "2D pose extractor not initialized"
            raise RuntimeError(msg)

        # 2. Tracked extraction (per-frame RTMO inference + tracking)
        t0 = time.perf_counter()
        extraction = extractor.extract_video_tracked(video_path, person_click=self._person_click)
        self._profiler.record("pose_inference_loop", time.perf_counter() - t0)

        # 3. Skip pre-roll (trim leading NaN frames before first detection)
        frame_offset = extraction.first_detection_frame
        poses = extraction.poses[frame_offset:]
        valid = extraction.valid_mask()[frame_offset:]
        first_frame = extraction.first_frame

        # 4. Gap filling
        t0 = time.perf_counter()
        from .utils.gap_filling import GapFiller

        filler = GapFiller()
        filled, _report = filler.fill_gaps(poses, valid)

        # 4b. Interpolate low-confidence keypoints (feet often unreliable on ice)
        filled = GapFiller.interpolate_low_confidence(filled, threshold=0.3)

        self._profiler.record("gap_filling", time.perf_counter() - t0)

        # 5. Spatial reference / camera compensation
        t0 = time.perf_counter()
        if self._reestimate_camera:
            from .detection.spatial_reference import (
                compensate_poses_per_frame,
                estimate_pose_sequence,
            )

            camera_poses = estimate_pose_sequence(str(video_path), interval=30, fps=meta.fps)
            compensated = compensate_poses_per_frame(
                filled,
                camera_poses,
                video_width=meta.width,
                video_height=meta.height,
            )
        else:
            # Single-frame estimation (use cached first_frame from extraction)
            import cv2

            from .detection.spatial_reference import CameraPose, SpatialReferenceDetector

            spatial_detector = SpatialReferenceDetector()
            if first_frame is not None:
                camera_pose = spatial_detector.estimate_pose(first_frame)
            else:
                # Fallback: read first frame from video
                cap = cv2.VideoCapture(str(video_path))
                ret, first_frame_fallback = cap.read()
                if ret:
                    camera_pose = spatial_detector.estimate_pose(first_frame_fallback)
                else:
                    camera_pose = CameraPose()
                cap.release()

            if camera_pose.confidence > 0.1:
                from .detection.spatial_reference import compensate_poses_per_frame

                camera_poses = [(0, camera_pose)]
                compensated = compensate_poses_per_frame(filled, camera_poses)
            else:
                compensated = filled
        self._profiler.record("spatial_reference", time.perf_counter() - t0)

        return compensated, frame_offset

    def analyze(
        self,
        video_path: Path,
        element_type: str | None = None,
        manual_phases: ElementPhase | None = None,
        reference_path: Path | None = None,
        isu_code: str | None = None,
        lang: str = "ru",
        body_mass: float = 70.0,
    ) -> AnalysisReport:
        """Analyze a skating video.

        Args:
            video_path: Path to user's video file.
            element_type: Type of skating element (e.g., 'three_turn', 'waltz_jump').
                If None, only pose extraction + visualization is performed
                (no metrics, DTW, or recommendations).
            manual_phases: Optional manual phase boundaries (auto-detect if None).
            reference_path: Optional path to reference video (use store if None).
            isu_code: Optional ISU element code (e.g., '3T', '2A') for GOE grading.
            lang: Output language for the GOE summary — "ru" (default, backward
                compatible) or "en". Forwarded to ``recommend_with_goe``; the
                rule-based recommendations themselves stay Russian (rules/*.py
                templates are Russian-only — out of scope, #407 follow-up).
            body_mass: Athlete body mass in kg, threaded into PhysicsEngine so
                moment_of_inertia/angular_momentum are per-user. Default 70.0
                (backward compatible); callers pass the user's weight_kg. #429

        Returns:
            AnalysisReport with metrics, recommendations, and scores.

        Raises:
            ValueError: If video cannot be processed or element type not supported.
        """
        # Validate element type (only when specified)
        from .analysis import element_defs

        element_def = None
        if element_type is not None:
            element_def = element_defs.get_element_def(element_type)
            if element_def is None:
                raise ValueError(f"Unknown element type: {element_type}")

        t0 = time.perf_counter()
        meta = get_video_meta(video_path)
        self._profiler.record("video_meta", time.perf_counter() - t0)

        t0 = time.perf_counter()
        compensated_h36m, _frame_offset = self._extract_and_track(video_path, meta)
        self._profiler.record("extract_and_track", time.perf_counter() - t0)

        t0 = time.perf_counter()
        normalized = self._get_normalizer().normalize(compensated_h36m)
        self._profiler.record("normalize", time.perf_counter() - t0)

        # Stage 3.1: 3D lift (TCPFormer on normalized 2D)
        t0 = time.perf_counter()
        lifter = self._get_3d_lifter()
        if lifter is not None:
            poses_3d_raw = lifter.estimate_3d(normalized)
            from .pose_3d.normalizer_3d import Pose3DNormalizer

            poses_3d = Pose3DNormalizer().normalize(poses_3d_raw)
            # Release ONNX session to return VRAM to driver pool
            lifter.release()
            self._3d_lifter = None
        else:
            poses_3d = None
        self._profiler.record("3d_lift", time.perf_counter() - t0)

        # Stage 3.5: Smooth poses (temporal filtering)
        # Use 3D poses for smoothing if available, else 2D
        t0 = time.perf_counter()
        pre_phases: ElementPhase | None = None

        if self._enable_smoothing:
            if manual_phases is not None:
                boundaries = [manual_phases.takeoff, manual_phases.peak, manual_phases.landing]
                boundaries = [b for b in boundaries if b > 0]
                if poses_3d is not None:
                    smoothed = self._get_smoother(meta.fps).smooth_phase_aware_3d(
                        poses_3d, boundaries
                    )
                else:
                    smoothed = self._get_smoother(meta.fps).smooth_phase_aware(
                        normalized, boundaries
                    )
            # Pre-detect phases for phase-aware smoothing on jumps
            # (preserves snapshot angles by resetting filter at boundaries)
            elif element_type is not None and element_defs.is_jump(element_type):
                pre_result = self._get_phase_detector().detect_phases(
                    normalized, meta.fps, element_type, poses_3d=poses_3d
                )
                pre_phases = pre_result.phases
                boundaries = [pre_phases.takeoff, pre_phases.peak, pre_phases.landing]
                boundaries = [b for b in boundaries if b > 0]
                if poses_3d is not None:
                    smoothed = self._get_smoother(meta.fps).smooth_phase_aware_3d(
                        poses_3d, boundaries
                    )
                else:
                    smoothed = self._get_smoother(meta.fps).smooth_phase_aware(
                        normalized, boundaries
                    )
            elif poses_3d is not None:
                smoothed = self._get_smoother(meta.fps).smooth_3d(poses_3d)
            else:
                smoothed = self._get_smoother(meta.fps).smooth(normalized)
        else:
            smoothed = poses_3d if poses_3d is not None else normalized
        self._profiler.record("smooth", time.perf_counter() - t0)

        # Stage 4-7: Element-specific analysis (only when element_type provided)
        if element_type is not None and element_def is not None:
            # Stage 4: Detect phases (or use manual)
            t0 = time.perf_counter()
            if manual_phases is not None:
                phases = manual_phases
            elif pre_phases is not None:
                # Use pre-detected phases from normalized (smoothed can distort CoM)
                phases = pre_phases
            else:
                phase_result = self._get_phase_detector().detect_phases(
                    smoothed, meta.fps, element_type, poses_3d=poses_3d
                )
                phases = phase_result.phases
            self._profiler.record("phase_detection", time.perf_counter() - t0)

            # Stage 5: Compute biomechanics metrics
            t0 = time.perf_counter()
            analyzer = self._get_analyzer_factory()(element_def)
            metrics = analyzer.analyze(smoothed, phases, meta.fps)
            self._profiler.record("metrics", time.perf_counter() - t0)

            # Stage 6: Load reference and align (if available)
            t0 = time.perf_counter()
            dtw_distance: float | None = None
            if self._reference_store is not None:
                reference = self._reference_store.get_best_match(element_type)
                if reference is not None:
                    aligner = self._get_aligner()
                    # Prefer 3D DTW when both user and reference have 3D data
                    if (
                        poses_3d is not None
                        and hasattr(reference, "poses_3d")
                        and reference.poses_3d is not None
                    ):
                        dtw_distance = aligner.compute_distance_3d(
                            poses_3d[phases.start : phases.end],
                            reference.poses_3d[reference.phases.start : reference.phases.end],
                        )
                    else:
                        dtw_distance = aligner.compute_distance(
                            normalized[phases.start : phases.end],
                            reference.poses[reference.phases.start : reference.phases.end],
                        )
            self._profiler.record("dtw_alignment", time.perf_counter() - t0)

            # Stage 6.5: Physics calculations
            t0 = time.perf_counter()
            try:
                from .analysis.physics_engine import PhysicsEngine

                engine = PhysicsEngine(body_mass=body_mass)  # #429: was hardcoded 70.0
                # Use takeoff/landing only if they are non-zero (0 = unknown for steps/turns)
                _t_off = phases.takeoff if phases.takeoff > 0 else None
                _l_off = phases.landing if phases.landing > 0 else None

                if poses_3d is not None:
                    physics_result = engine.analyze(
                        smoothed,
                        takeoff_idx=_t_off,
                        landing_idx=_l_off,
                        fps=meta.fps,  # #423: was missing -> 3D path hardcoded 30 fps
                    )
                    physics_dict = {
                        "jump_height": physics_result.jump_height,
                        "flight_time": physics_result.flight_time,
                        "takeoff_velocity": None,
                        "fit_quality": None,
                        "avg_inertia": float(np.mean(physics_result.moment_of_inertia)),
                        "center_of_mass": physics_result.center_of_mass,
                        "moment_of_inertia": physics_result.moment_of_inertia,
                        "angular_momentum": physics_result.angular_momentum,
                    }
                else:
                    physics_dict = engine.analyze_2d(
                        smoothed,
                        takeoff_idx=_t_off,
                        landing_idx=_l_off,
                        fps=meta.fps,
                    )
            except Exception:
                physics_dict = {}
            self._profiler.record("physics", time.perf_counter() - t0)

            # Stage 6.5: ISU GOE grading (if isu_code available)
            t0 = time.perf_counter()
            goe_grade = None
            if isu_code:
                from .analysis.goe_grader import GOEGrader

                goe_grader = GOEGrader()
                sov_entry = self._get_sov_entry(isu_code)
                bv = sov_entry.base_value if sov_entry else 0.0
                expected_rot = sov_entry.rotations if sov_entry else element_def.rotations
                goe_grade = goe_grader.compute_goe_grade(
                    metrics, base_value=bv, expected_rotations=expected_rot
                )
            self._profiler.record("goe_grading", time.perf_counter() - t0)

            # Stage 7: Generate recommendations
            t0 = time.perf_counter()
            recommender = self._get_recommender()
            recommendations = recommender.recommend_with_goe(
                metrics, element_type, goe_grade, lang=lang
            )
            self._profiler.record("recommendations", time.perf_counter() - t0)

            # Stage 8: Compute overall score
            overall_score = self._compute_overall_score(metrics)
        else:
            # No element type specified — poses + visualization only
            phases = ElementPhase(name="unknown", start=0, takeoff=0, peak=0, landing=0, end=0)
            metrics = []
            recommendations = []
            overall_score = None
            dtw_distance = None
            physics_dict = {}
            goe_grade = None

        return AnalysisReport(
            element_type=element_type or "unknown",
            phases=phases,
            metrics=metrics,
            recommendations=recommendations,
            overall_score=overall_score if overall_score is not None else 0.0,
            goe_grade=goe_grade,
            dtw_distance=dtw_distance if dtw_distance is not None else 0.0,
            physics=physics_dict,
            profiling=self._profiler.to_dict(),
        )

    def segment_video(
        self,
        video_path: Path,
    ) -> SegmentationResult:
        """Segment video into individual skating elements.

        Args:
            video_path: Path to training video with multiple elements.

        Returns:
            SegmentationResult with detected elements.
        """
        from .analysis import element_segmenter

        ElementSegmenter = element_segmenter.ElementSegmenter

        # Get video metadata
        meta = get_video_meta(video_path)

        # Stage 1-2.6: Extract poses with tracking, gap filling, spatial compensation
        compensated_h36m, _frame_offset = self._extract_and_track(video_path, meta)

        # Stage 2: Normalize poses

        normalized = self._get_normalizer().normalize(compensated_h36m)

        # Stage 3: Smooth poses
        if self._enable_smoothing:
            smoothed = self._get_smoother(meta.fps).smooth(normalized)
        else:
            smoothed = normalized

        # Stage 4: Segment video into elements
        segmenter = ElementSegmenter()
        segmentation = segmenter.segment(smoothed, video_path, meta)

        return segmentation

    def _get_detector(self) -> PersonDetector:  # type: ignore[valid-type]
        """Lazy-load person detector."""
        if self._detector is None:
            from .detection import person_detector

            PersonDetector = person_detector.PersonDetector

            self._detector = PersonDetector(confidence=0.5)
        return self._detector

    def _get_pose_2d_extractor(self) -> PoseExtractor:  # type: ignore[valid-type]
        """Lazy-load PoseExtractor (sole 2D pose backend)."""
        if self._pose_2d_extractor is None:
            from .pose_estimation.pose_extractor import PoseExtractor

            self._pose_2d_extractor = PoseExtractor(
                output_format="normalized",
                device=self._device_config.device,
            )
        return self._pose_2d_extractor  # type: ignore[return-value]

    def _get_normalizer(self) -> PoseNormalizer:  # type: ignore[valid-type]
        """Lazy-load pose normalizer."""
        if self._normalizer is None:
            from .pose_estimation import normalizer

            PoseNormalizer = normalizer.PoseNormalizer

            self._normalizer = PoseNormalizer(target_spine_length=0.4)
        return self._normalizer

    def _get_smoother(self, fps: float = 30.0) -> PoseSmoother:  # type: ignore[valid-type]
        """Lazy-load pose smoother with One-Euro Filter."""
        if not self._enable_smoothing:
            from .utils.smoothing import OneEuroFilterConfig, PoseSmoother

            config = OneEuroFilterConfig(min_cutoff=100.0, beta=0.0, freq=fps)
            return PoseSmoother(config=config, freq=fps)

        if self._smoother is None:
            from .utils.smoothing import (
                PoseSmoother,
                get_skating_optimized_config,
            )

            config = self._smoothing_config or get_skating_optimized_config(fps)
            self._smoother = PoseSmoother(config=config, freq=fps)
        return self._smoother

    def _get_phase_detector(self) -> PhaseDetector:  # type: ignore[valid-type]
        """Lazy-load phase detector."""
        if self._phase_detector is None:
            from .analysis import phase_detector

            PhaseDetector = phase_detector.PhaseDetector

            self._phase_detector = PhaseDetector()
        return self._phase_detector

    def _get_analyzer_factory(self) -> type:
        """Get analyzer factory (returns BiomechanicsAnalyzer class)."""
        if self._analyzer_factory is None:
            from .analysis import metrics

            BiomechanicsAnalyzer = metrics.BiomechanicsAnalyzer

            self._analyzer_factory = BiomechanicsAnalyzer
        return self._analyzer_factory

    def _get_aligner(self) -> MotionAligner | MotionDTWAligner:  # type: ignore[valid-type]
        """Lazy-load motion aligner (using phase-aware MotionDTW)."""
        if self._aligner is None:
            from .alignment import motion_dtw

            MotionDTWAligner = motion_dtw.MotionDTWAligner

            self._aligner = MotionDTWAligner(window_type="sakoechiba", window_size=0.2)
        return self._aligner

    def _get_recommender(self) -> Recommender:  # type: ignore[valid-type]
        """Lazy-load recommender."""
        if self._recommender is None:
            from .analysis import recommender

            Recommender = recommender.Recommender

            self._recommender = Recommender()
        return self._recommender

    def _get_sov_entry(self, isu_code: str):
        """Load SOV entry for ISU code from data/isu JSON."""
        import json
        from pathlib import Path

        sov_path = Path(__file__).parent.parent.parent / "data" / "isu" / "sov_2025_26.json"
        if not sov_path.exists():
            return None
        try:
            with sov_path.open() as f:
                sov = json.load(f)
            for section in ("jumps", "spins", "step_sequences", "choreo_sequences"):
                entry = sov.get(section, {}).get(isu_code)
                if entry:
                    return type(
                        "SOVEntry",
                        (),
                        {
                            "base_value": entry["base_value"],
                            "rotations": entry.get("rotations", 0.0),
                        },
                    )()
        except (json.JSONDecodeError, KeyError):
            return None
        return None

    def _get_3d_lifter(self):
        """Lazy-load TCPFormer 3D lifter (ONNX).

        Uses model_downloader to resolve model path (local search → S3 download).
        Returns None if model unavailable (graceful degradation).
        After release(), calling again re-creates the ONNX session.
        """
        if getattr(self, "_3d_lifter_unavailable", False):
            return None

        if self._3d_lifter is None:
            from .pose_3d.model_downloader import resolve_model

            model_path = resolve_model("tcpformer", device=self._device_config.device)

            if model_path is not None:
                from .pose_3d.onnx_extractor import ONNXPoseExtractor

                self._3d_lifter = ONNXPoseExtractor(
                    model_path=model_path,
                    device=self._device_config.device,
                    temporal_window=81,
                )
            else:
                self._3d_lifter_unavailable = True

        return self._3d_lifter

    def _compute_overall_score(self, metrics: list) -> float:  # type: ignore[valid-type]
        """Compute overall quality score 0-10 from metrics.

        Args:
            metrics: List of MetricResult.

        Returns:
            Overall score 0-10.
        """
        if not metrics:
            return 5.0

        good_count = sum(1 for m in metrics if m.is_good)
        total_count = len(metrics)

        if total_count == 0:
            return 5.0

        ratio = good_count / total_count
        score = ratio * 10

        return float(round(score, 1))

    def format_report(self, report: AnalysisReport) -> str:
        """Format analysis report as human-readable text.

        Args:
            report: AnalysisReport to format.

        Returns:
            Formatted text report in Russian.
        """
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append(f"АНАЛИЗ: {report.element_type.upper()}")
        lines.append("=" * 60)

        # Phases
        lines.append("\n--- Фазы элемента ---")
        phase = report.phases
        if phase and (phase.takeoff > 0 or phase.start > 0):  # Only show if valid
            lines.append(f"  Начало:     {phase.start}")
            lines.append(f"  Отрыв:      {phase.takeoff}")
            lines.append(f"  Пик:        {phase.peak}")
            lines.append(f"  Приземление: {phase.landing}")
            lines.append(f"  Конец:       {phase.end}")

        # Metrics
        lines.append("\n--- Биомеханические метрики ---")
        for metric in report.metrics:
            status = "✓ ОК" if metric.is_good else "✗ ПЛОХО"
            ref_min, ref_max = metric.reference_range
            lines.append(
                f"  {metric.name}: {metric.value:.2f} {metric.unit} [{status}] "
                f"(референс: {ref_min:.2f}-{ref_max:.2f})"
            )

        # DTW distance
        lines.append("\n--- Сходство с референсом ---")
        lines.append(f"  DTW-расстояние: {report.dtw_distance:.3f} (0 = идеально)")

        # Recommendations
        if report.recommendations:
            lines.append("\n--- РЕКОМЕНДАЦИИ ---")
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"  {i}. {rec}")
        else:
            lines.append("\n--- РЕКОМЕНДАЦИИ ---")
            lines.append("  Отличное выполнение! Продолжай в том же духе.")

        # Overall score
        lines.append(f"\nОбщий балл: {report.overall_score:.1f} / 10")

        lines.append("=" * 60)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Async pipeline with parallel stage execution
    # ------------------------------------------------------------------

    async def analyze_async(
        self,
        video_path: Path,
        element_type: str | None = None,
        manual_phases: ElementPhase | None = None,
        reference_path: Path | None = None,
        lang: str = "ru",
        body_mass: float = 70.0,
    ) -> AnalysisReport:
        """Async version of analyze with parallel stage execution.

        Parallelizes independent operations:
        - Wave 0: 3D lift + reference loading (parallel)
        - Wave 1: Phase detection (if not pre-detected for smoothing)
        - Wave 2: Metrics + DTW alignment + physics (3D if available) (parallel)
        NumPy/Numba release GIL so ThreadPoolExecutor achieves real parallelism.

        Args:
            video_path: Path to user's video file.
            element_type: Type of skating element (e.g., 'three_turn', 'waltz_jump').
            manual_phases: Optional manual phase boundaries (auto-detect if None).
            reference_path: Optional path to reference video (use store if None).

        Returns:
            AnalysisReport with metrics, recommendations, and scores.
        """
        # Validate element type
        from .analysis import element_defs

        element_def = None
        if element_type is not None:
            element_def = element_defs.get_element_def(element_type)
            if element_def is None:
                raise ValueError(f"Unknown element type: {element_type}")

        # Get video metadata
        meta = get_video_meta(video_path)

        # Stage 1-2.6: Extract poses with tracking (must be sequential)
        compensated_h36m, _frame_offset = self._extract_and_track(video_path, meta)

        # Stage 3: Normalize poses (fast, run in main)
        normalized = self._get_normalizer().normalize(compensated_h36m)

        # === Wave 0: 3D Lift || Ref Load ===
        wave0_tasks: list[asyncio.Task] = []

        lifter = self._get_3d_lifter()
        if lifter is not None:
            wave0_tasks.append(asyncio.create_task(self._lift_3d_async(normalized)))

        if self._reference_store is not None and element_type is not None:
            wave0_tasks.append(asyncio.create_task(self._load_reference_async(element_type)))

        wave0_results = await asyncio.gather(*wave0_tasks) if wave0_tasks else []

        poses_3d = None
        reference: np.ndarray | None = None
        result_idx = 0
        if lifter is not None and len(wave0_results) > result_idx:
            poses_3d = wave0_results[result_idx]
            result_idx += 1
        if (
            self._reference_store is not None
            and element_type is not None
            and len(wave0_results) > result_idx
        ):
            reference = wave0_results[result_idx]
            result_idx += 1

        # Stage 3.5: Smooth poses (uses 3D if available)
        pre_phases_async: ElementPhase | None = None
        if self._enable_smoothing:
            if manual_phases is not None:
                boundaries = [manual_phases.takeoff, manual_phases.peak, manual_phases.landing]
                boundaries = [b for b in boundaries if b > 0]
                if poses_3d is not None:
                    smoothed = self._get_smoother(meta.fps).smooth_phase_aware_3d(
                        poses_3d, boundaries
                    )
                else:
                    smoothed = self._get_smoother(meta.fps).smooth_phase_aware(
                        normalized, boundaries
                    )
            # Pre-detect phases for phase-aware smoothing on jumps
            # (preserves snapshot angles by resetting filter at boundaries)
            elif element_type is not None and element_defs.is_jump(element_type):
                pre_result = self._get_phase_detector().detect_phases(
                    normalized, meta.fps, element_type, poses_3d=poses_3d
                )
                pre_phases_async = pre_result.phases
                boundaries = [
                    pre_phases_async.takeoff,
                    pre_phases_async.peak,
                    pre_phases_async.landing,
                ]
                boundaries = [b for b in boundaries if b > 0]
                if poses_3d is not None:
                    smoothed = self._get_smoother(meta.fps).smooth_phase_aware_3d(
                        poses_3d, boundaries
                    )
                else:
                    smoothed = self._get_smoother(meta.fps).smooth_phase_aware(
                        normalized, boundaries
                    )
            elif poses_3d is not None:
                smoothed = self._get_smoother(meta.fps).smooth_3d(poses_3d)
            else:
                smoothed = self._get_smoother(meta.fps).smooth(normalized)
        else:
            smoothed = poses_3d if poses_3d is not None else normalized

        # Default phases for non-element analysis
        phases = ElementPhase(name="unknown", start=0, takeoff=0, peak=0, landing=0, end=0)

        # Element-specific analysis with wave-based parallelism
        physics_dict: dict = {}

        if element_type is not None and element_def is not None:
            # Pre-compute CoM once (shared by metrics)
            com_trajectory = calculate_com_trajectory(smoothed)

            # === Wave 1: phase detection ===
            # Reference already loaded in Wave 0
            if manual_phases is not None:
                phases = manual_phases
            elif pre_phases_async is not None:
                # Use pre-detected phases from normalized (smoothed can distort CoM)
                phases = pre_phases_async
            else:
                phases = await self._detect_phases_async(
                    smoothed, meta.fps, element_type, None, poses_3d=poses_3d
                )

            # === Wave 2: metrics + DTW + physics in parallel ===
            # All three depend only on Wave 1 outputs (phases, reference, smoothed/normalized).
            # None depends on another's result, so they can run concurrently.
            wave2_tasks: list[asyncio.Task] = []

            # Task 2a: Biomechanics metrics
            wave2_tasks.append(
                asyncio.create_task(
                    self._compute_metrics_async(
                        smoothed,
                        phases,
                        meta.fps,
                        element_def,
                        com_trajectory=com_trajectory,
                    )
                )
            )

            # Task 2b: DTW alignment (needs normalized poses + phases + reference)
            if reference is not None:
                wave2_tasks.append(
                    asyncio.create_task(
                        self._compute_dtw_async(normalized, phases, reference, poses_3d)
                    )
                )

            # Task 2c: Physics (3D if available, else 2D)
            wave2_tasks.append(
                asyncio.create_task(
                    self._compute_physics_async(
                        smoothed, phases, meta.fps, poses_3d=poses_3d, body_mass=body_mass
                    )
                )
            )

            wave2_results = await asyncio.gather(*wave2_tasks)

            # Unpack wave 2 results — order matches append order above
            metrics = wave2_results[0]
            dtw_distance = wave2_results[1] if reference is not None else None
            physics_dict = wave2_results[2] if reference is not None else wave2_results[1]

            recommender = self._get_recommender()
            # recommend() rule templates are Russian-only (rules/*.py); lang
            # plumbing is for the GOE summary + training_plan only (#417).
            recommendations = recommender.recommend(metrics, element_type)
            overall_score = self._compute_overall_score(metrics)
        else:
            # No element type specified
            metrics = []
            recommendations = []
            overall_score = None
            dtw_distance = None
            physics_dict = {}

        return AnalysisReport(
            element_type=element_type or "unknown",
            phases=phases,
            metrics=metrics,
            recommendations=recommendations,
            overall_score=overall_score if overall_score is not None else 0.0,
            dtw_distance=dtw_distance if dtw_distance is not None else 0.0,
            physics=physics_dict,
        )

    async def _detect_phases_async(
        self,
        poses: np.ndarray,
        fps: float,
        element_type: str,
        manual_phases: ElementPhase | None,
        poses_3d: np.ndarray | None = None,
    ) -> ElementPhase:
        """Async phase detection.

        Args:
            poses: (N, 17, 2) normalized poses.
            fps: Video frame rate.
            element_type: Element type for detection.
            manual_phases: Manual phases if provided.
            poses_3d: Optional 3D poses for Z-axis detection.

        Returns:
            ElementPhase with detected boundaries.
        """
        if manual_phases is not None:
            return manual_phases

        # Run in thread pool
        loop = asyncio.get_event_loop()
        detector = self._get_phase_detector()
        result = await loop.run_in_executor(
            None, lambda: detector.detect_phases(poses, fps, element_type, poses_3d=poses_3d)
        )
        return result.phases

    async def _compute_metrics_async(
        self,
        poses: np.ndarray,
        phases: ElementPhase,
        fps: float,
        element_def: ElementDef,
        com_trajectory: np.ndarray | None = None,
    ) -> list:
        """Async biomechanics metrics computation.

        Args:
            poses: (N, 17, 2) normalized poses.
            phases: Element phases.
            fps: Video frame rate.
            element_def: Element definition.
            com_trajectory: Pre-computed CoM trajectory (optional, for caching).

        Returns:
            List of MetricResult.
        """
        # Run in thread pool
        loop = asyncio.get_event_loop()
        analyzer = self._get_analyzer_factory()(element_def)
        metrics = await loop.run_in_executor(
            None, analyzer.analyze, poses, phases, fps, com_trajectory
        )
        return metrics

    async def _load_reference_async(self, element_type: str):
        """Async reference loading from store.

        Args:
            element_type: Element type to load reference for.

        Returns:
            ReferenceData or None.
        """
        if self._reference_store is None:
            return None

        # Run in thread pool
        loop = asyncio.get_event_loop()
        reference = await loop.run_in_executor(
            None, self._reference_store.get_best_match, element_type
        )
        return reference

    async def _compute_dtw_async(
        self,
        normalized: np.ndarray,
        phases: ElementPhase,
        reference,
        poses_3d: np.ndarray | None = None,
    ) -> float:
        """Async DTW alignment against reference.

        Uses 3D DTW when both user and reference have 3D data,
        otherwise falls back to 2D.

        Args:
            normalized: (N, 17, 2) normalized poses.
            phases: Element phases for slicing.
            reference: ReferenceData with .poses and .phases.
            poses_3d: Optional (N, 17, 3) 3D poses.

        Returns:
            DTW distance (float).
        """
        loop = asyncio.get_event_loop()
        aligner = self._get_aligner()

        use_3d = (
            poses_3d is not None
            and hasattr(reference, "poses_3d")
            and reference.poses_3d is not None
        )

        if use_3d:
            return await loop.run_in_executor(
                None,
                aligner.compute_distance_3d,
                poses_3d[phases.start : phases.end],
                reference.poses_3d[reference.phases.start : reference.phases.end],
            )
        else:
            return await loop.run_in_executor(
                None,
                aligner.compute_distance,
                normalized[phases.start : phases.end],
                reference.poses[reference.phases.start : reference.phases.end],
            )

    async def _compute_physics_async(
        self,
        smoothed: np.ndarray,
        phases: ElementPhase,
        fps: float,
        poses_3d: np.ndarray | None = None,
        body_mass: float = 70.0,
    ) -> dict:
        """Compute physics in thread pool (3D if available, else 2D).

        Args:
            smoothed: Smoothed poses (N, 17, 2) or (N, 17, 3).
            phases: Element phases.
            fps: Video frame rate.
            poses_3d: 3D poses if available.
            body_mass: Athlete body mass in kg for per-user inertia (#429).

        Returns:
            Physics result dict.
        """
        loop = asyncio.get_event_loop()
        from .analysis.physics_engine import PhysicsEngine

        engine = PhysicsEngine(body_mass=body_mass)  # #429: was hardcoded 70.0
        _t_off = phases.takeoff if phases.takeoff > 0 else None
        _l_off = phases.landing if phases.landing > 0 else None

        try:
            if poses_3d is not None:
                result = await loop.run_in_executor(
                    None,
                    lambda: engine.analyze(
                        smoothed, takeoff_idx=_t_off, landing_idx=_l_off, fps=fps
                    ),  # #423: was missing -> 3D path hardcoded 30 fps
                )
                return {
                    "jump_height": result.jump_height,
                    "flight_time": result.flight_time,
                    "takeoff_velocity": None,
                    "fit_quality": None,
                    "avg_inertia": float(np.mean(result.moment_of_inertia)),
                    "center_of_mass": result.center_of_mass,
                    "moment_of_inertia": result.moment_of_inertia,
                    "angular_momentum": result.angular_momentum,
                }
            else:
                return await loop.run_in_executor(
                    None,
                    lambda: engine.analyze_2d(
                        smoothed, takeoff_idx=_t_off, landing_idx=_l_off, fps=fps
                    ),
                )
        except Exception:
            return {}

    async def _lift_3d_async(self, normalized: np.ndarray) -> np.ndarray:
        """Async 3D lift — runs TCPFormer in thread pool (GIL released by ORT CUDA).

        Releases ONNX session after inference to return VRAM to driver pool.

        Args:
            normalized: (N, 17, 2) normalized 2D poses.

        Returns:
            (N, 17, 3) 3D normalized poses.
        """
        loop = asyncio.get_event_loop()
        lifter = self._get_3d_lifter()
        if lifter is None:
            raise RuntimeError("3D lifter not available")

        poses_3d_raw = await loop.run_in_executor(None, lifter.estimate_3d, normalized)
        normalizer = self._get_normalizer()
        poses_3d = await loop.run_in_executor(None, normalizer.normalize_3d, poses_3d_raw)
        # Release ONNX session to return VRAM to driver pool
        lifter.release()
        self._3d_lifter = None
        return poses_3d
