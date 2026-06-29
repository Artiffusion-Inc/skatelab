"""Integration and unit tests for the full analysis pipeline.

H3.6M Architecture:
    Pipeline uses H3.6M 17-keypoint format as primary.
    2D: PoseExtractor (PersonDetector + MogaNetBatch)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.pipeline import AnalysisPipeline
from src.types import (
    AnalysisReport,
    ElementPhase,
    MetricResult,
    SegmentationResult,
    VideoMeta,
)


class TestAnalysisPipelineInit:
    """Unit tests for AnalysisPipeline initialization."""

    def test_init_defaults(self):
        """Should initialize with default values."""
        pipeline = AnalysisPipeline()

        assert pipeline._reference_store is None
        assert pipeline._enable_smoothing is True
        assert pipeline._person_click is None
        assert pipeline._reestimate_camera is False
        assert pipeline._profiler is not None

    def test_init_with_reference_store(self):
        """Should store reference_store when provided."""
        mock_store = MagicMock()
        pipeline = AnalysisPipeline(reference_store=mock_store)

        assert pipeline._reference_store is mock_store

    def test_init_with_device_str(self):
        """Should convert string device to DeviceConfig."""
        pipeline = AnalysisPipeline(device="cpu")

        assert pipeline._device_config.device == "cpu"

    def test_init_with_custom_options(self):
        """Should store all custom options."""
        mock_profiler = MagicMock()
        pipeline = AnalysisPipeline(
            enable_smoothing=False,
            reestimate_camera=True,
            profiler=mock_profiler,
        )

        assert pipeline._enable_smoothing is False
        assert pipeline._reestimate_camera is True
        assert pipeline._profiler is mock_profiler


class TestAnalysisPipelineAnalyze:
    """Unit tests for AnalysisPipeline.analyze with mocked dependencies."""

    @pytest.fixture
    def sample_3d_poses(self):
        """Create sample H3.6M 3D poses (10 frames, 17 joints, 3 coords)."""
        poses = np.ones((10, 17, 3), dtype=np.float32)
        for i in range(10):
            poses[i, :, 0] = 0.5 + i * 0.01
            poses[i, :, 1] = 0.5 + i * 0.01
            poses[i, :, 2] = 0.0
        return poses

    @pytest.fixture
    def sample_2d_poses(self):
        """Create sample H3.6M 2D normalized poses."""
        return np.ones((10, 17, 2), dtype=np.float32) * 0.5

    @pytest.fixture
    def sample_phases(self):
        """Create sample element phases."""
        return ElementPhase(
            name="waltz_jump",
            start=0,
            takeoff=3,
            peak=5,
            landing=7,
            end=9,
        )

    def _make_pipeline_with_mocks(
        self,
        sample_3d_poses,
        sample_2d_poses,
        sample_phases,
        reference_store=None,
    ):
        """Build pipeline with all heavy dependencies mocked."""
        pipeline = AnalysisPipeline(
            reference_store=reference_store,
        )

        # Mock _extract_and_track to avoid video I/O and ONNX
        pipeline._extract_and_track = MagicMock(return_value=(sample_3d_poses, 0))

        # Mock normalizer
        mock_normalizer = MagicMock()
        mock_normalizer.normalize = MagicMock(return_value=sample_2d_poses)
        pipeline._get_normalizer = MagicMock(return_value=mock_normalizer)

        # Mock smoother
        mock_smoother = MagicMock()
        mock_smoother.smooth = MagicMock(return_value=sample_2d_poses)
        mock_smoother.smooth_phase_aware = MagicMock(return_value=sample_2d_poses)
        pipeline._get_smoother = MagicMock(return_value=mock_smoother)

        # Mock phase detector
        mock_phase_result = MagicMock()
        mock_phase_result.phases = sample_phases
        mock_phase_detector = MagicMock()
        mock_phase_detector.detect_phases = MagicMock(return_value=mock_phase_result)
        pipeline._get_phase_detector = MagicMock(return_value=mock_phase_detector)

        # Mock analyzer factory
        mock_metric = MetricResult(
            name="airtime",
            value=0.5,
            unit="s",
            is_good=True,
            reference_range=(0.3, 0.7),
        )
        mock_analyzer = MagicMock()
        mock_analyzer.analyze = MagicMock(return_value=[mock_metric])
        pipeline._get_analyzer_factory = MagicMock(return_value=lambda element_def: mock_analyzer)

        # Mock recommender
        mock_recommender = MagicMock()
        mock_recommender.recommend_with_goe = MagicMock(return_value=["Test recommendation"])
        pipeline._get_recommender = MagicMock(return_value=mock_recommender)

        # Mock aligner
        mock_aligner = MagicMock()
        mock_aligner.compute_distance = MagicMock(return_value=0.25)
        pipeline._get_aligner = MagicMock(return_value=mock_aligner)

        return pipeline

    @patch("src.pipeline.get_video_meta")
    def test_analyze_full_pipeline(
        self, mock_get_meta, sample_3d_poses, sample_2d_poses, sample_phases
    ):
        """Should run full pipeline and return AnalysisReport."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        pipeline = self._make_pipeline_with_mocks(sample_3d_poses, sample_2d_poses, sample_phases)

        report = pipeline.analyze(Path("test.mp4"), element_type="waltz_jump")

        assert isinstance(report, AnalysisReport)
        assert report.element_type == "waltz_jump"
        assert report.phases == sample_phases
        assert len(report.metrics) == 1
        assert report.metrics[0].name == "airtime"
        assert report.recommendations == ["Test recommendation"]
        assert report.overall_score == 10.0

        pipeline._extract_and_track.assert_called_once()
        pipeline._get_normalizer().normalize.assert_called_once()
        pipeline._get_phase_detector().detect_phases.assert_called_once()
        pipeline._get_analyzer_factory()("dummy").analyze.assert_called_once()

    @patch("src.pipeline.get_video_meta")
    def test_analyze_without_element_type(self, mock_get_meta, sample_3d_poses, sample_2d_poses):
        """Should return basic report without metrics when element_type is None."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        pipeline = self._make_pipeline_with_mocks(
            sample_3d_poses, sample_2d_poses, ElementPhase("unknown", 0, 0, 0, 0, 0)
        )

        report = pipeline.analyze(Path("test.mp4"))

        assert isinstance(report, AnalysisReport)
        assert report.element_type == "unknown"
        assert report.metrics == []
        assert report.recommendations == []
        assert report.overall_score == 0.0
        assert report.dtw_distance == 0.0

        pipeline._get_phase_detector.assert_not_called()
        pipeline._get_analyzer_factory.assert_not_called()

    @patch("src.pipeline.get_video_meta")
    def test_analyze_unknown_element_type(self, mock_get_meta, sample_3d_poses, sample_2d_poses):
        """Should raise ValueError for unknown element type."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        pipeline = self._make_pipeline_with_mocks(
            sample_3d_poses, sample_2d_poses, ElementPhase("unknown", 0, 0, 0, 0, 0)
        )

        with pytest.raises(ValueError, match="Unknown element type"):
            pipeline.analyze(Path("test.mp4"), element_type="nonexistent_element")

    @patch("src.pipeline.get_video_meta")
    def test_analyze_with_manual_phases(
        self, mock_get_meta, sample_3d_poses, sample_2d_poses, sample_phases
    ):
        """Should use manual phases when provided."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        manual_phases = ElementPhase(
            name="waltz_jump",
            start=1,
            takeoff=2,
            peak=4,
            landing=6,
            end=8,
        )

        pipeline = self._make_pipeline_with_mocks(sample_3d_poses, sample_2d_poses, sample_phases)

        report = pipeline.analyze(
            Path("test.mp4"),
            element_type="waltz_jump",
            manual_phases=manual_phases,
        )

        assert report.phases == manual_phases
        pipeline._get_phase_detector().detect_phases.assert_not_called()

    @patch("src.pipeline.get_video_meta")
    def test_analyze_with_jump_and_phase_aware_smoothing(
        self, mock_get_meta, sample_3d_poses, sample_2d_poses, sample_phases
    ):
        """Should pre-detect phases for phase-aware smoothing on jumps."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        pipeline = self._make_pipeline_with_mocks(sample_3d_poses, sample_2d_poses, sample_phases)

        report = pipeline.analyze(Path("test.mp4"), element_type="waltz_jump")

        pipeline._get_smoother().smooth_phase_aware.assert_called_once()
        args = pipeline._get_smoother().smooth_phase_aware.call_args
        assert args[0][1] == [3, 5, 7]

    @patch("src.pipeline.get_video_meta")
    def test_analyze_non_jump_no_phase_aware_smoothing(
        self, mock_get_meta, sample_3d_poses, sample_2d_poses
    ):
        """Should use regular smoothing for non-jump elements."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        turn_phases = ElementPhase(
            name="three_turn",
            start=0,
            takeoff=0,
            peak=0,
            landing=0,
            end=9,
        )
        pipeline = self._make_pipeline_with_mocks(sample_3d_poses, sample_2d_poses, turn_phases)

        report = pipeline.analyze(Path("test.mp4"), element_type="three_turn")

        pipeline._get_smoother().smooth.assert_called_once()
        pipeline._get_smoother().smooth_phase_aware.assert_not_called()

    @patch("src.pipeline.get_video_meta")
    def test_analyze_with_reference_store(
        self, mock_get_meta, sample_3d_poses, sample_2d_poses, sample_phases
    ):
        """Should compute DTW distance when reference store is available."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        mock_ref = MagicMock()
        mock_ref.poses = sample_2d_poses
        mock_ref.phases = sample_phases
        mock_store = MagicMock()
        mock_store.get_best_match = MagicMock(return_value=mock_ref)

        pipeline = self._make_pipeline_with_mocks(
            sample_3d_poses,
            sample_2d_poses,
            sample_phases,
            reference_store=mock_store,
        )

        report = pipeline.analyze(Path("test.mp4"), element_type="waltz_jump")

        assert report.dtw_distance == 0.25
        mock_store.get_best_match.assert_called_once_with("waltz_jump")
        pipeline._get_aligner().compute_distance.assert_called_once()

    @patch("src.pipeline.get_video_meta")
    def test_analyze_with_reference_store_no_match(
        self, mock_get_meta, sample_3d_poses, sample_2d_poses, sample_phases
    ):
        """Should set dtw_distance to 0.0 when no reference match found."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        mock_store = MagicMock()
        mock_store.get_best_match = MagicMock(return_value=None)

        pipeline = self._make_pipeline_with_mocks(
            sample_3d_poses,
            sample_2d_poses,
            sample_phases,
            reference_store=mock_store,
        )

        report = pipeline.analyze(Path("test.mp4"), element_type="waltz_jump")

        assert report.dtw_distance == 0.0
        pipeline._get_aligner().compute_distance.assert_not_called()

    @patch("src.pipeline.get_video_meta")
    def test_analyze_profiling_recorded(
        self, mock_get_meta, sample_3d_poses, sample_2d_poses, sample_phases
    ):
        """Should record profiling data in the report."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        pipeline = self._make_pipeline_with_mocks(sample_3d_poses, sample_2d_poses, sample_phases)

        report = pipeline.analyze(Path("test.mp4"), element_type="waltz_jump")

        assert report.profiling is not None
        assert "extract_and_track" in {s["name"] for s in report.profiling["stages"]}
        assert "normalize" in {s["name"] for s in report.profiling["stages"]}

    @patch("src.pipeline.get_video_meta")
    def test_analyze_report_formatting(
        self, mock_get_meta, sample_3d_poses, sample_2d_poses, sample_phases
    ):
        """Should format report with Russian text."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        pipeline = self._make_pipeline_with_mocks(sample_3d_poses, sample_2d_poses, sample_phases)

        report = pipeline.analyze(Path("test.mp4"), element_type="waltz_jump")
        formatted = pipeline.format_report(report)

        assert "АНАЛИЗ" in formatted
        assert "WALTZ_JUMP" in formatted
        assert "РЕКОМЕНДАЦИИ" in formatted


class TestAnalysisPipelineExtractAndTrack:
    """Unit tests for AnalysisPipeline._extract_and_track."""

    def test_extract_and_track_extractor_none(self, tmp_path: Path):
        """Should raise RuntimeError when 2D extractor returns None."""
        pipeline = AnalysisPipeline()
        pipeline._get_pose_2d_extractor = MagicMock(return_value=None)

        meta = VideoMeta(path=tmp_path / "test.mp4", width=640, height=480, fps=30.0, num_frames=10)

        with pytest.raises(RuntimeError, match="2D pose extractor not initialized"):
            pipeline._extract_and_track(tmp_path / "test.mp4", meta)


class TestAnalysisPipelineSegment:
    """Unit tests for AnalysisPipeline.segment_video."""

    @patch("src.pipeline.get_video_meta")
    @patch("src.analysis.element_segmenter.ElementSegmenter")
    def test_segment_video(self, mock_segmenter_cls, mock_get_meta, tmp_path: Path):
        """Should segment video into elements."""
        mock_get_meta.return_value = VideoMeta(
            path=tmp_path / "test.mp4",
            width=640,
            height=480,
            fps=30.0,
            num_frames=30,
        )

        poses_3d = np.ones((30, 17, 3), dtype=np.float32)
        pipeline = AnalysisPipeline()
        pipeline._extract_and_track = MagicMock(return_value=(poses_3d, 0))

        mock_normalizer = MagicMock()
        mock_normalizer.normalize = MagicMock(return_value=np.ones((30, 17, 2), dtype=np.float32))
        pipeline._get_normalizer = MagicMock(return_value=mock_normalizer)

        mock_smoother = MagicMock()
        mock_smoother.smooth = MagicMock(return_value=np.ones((30, 17, 2), dtype=np.float32))
        pipeline._get_smoother = MagicMock(return_value=mock_smoother)

        mock_segmenter = MagicMock()
        expected_result = SegmentationResult(
            segments=[],
            video_path=tmp_path / "test.mp4",
            video_meta=mock_get_meta.return_value,
            method="mock",
            confidence=0.9,
        )
        mock_segmenter.segment = MagicMock(return_value=expected_result)
        mock_segmenter_cls.return_value = mock_segmenter

        result = pipeline.segment_video(tmp_path / "test.mp4")

        assert isinstance(result, SegmentationResult)
        assert result.method == "mock"
        pipeline._extract_and_track.assert_called_once()


class TestAnalysisPipelineAsync:
    """Unit tests for AnalysisPipeline.analyze_async."""

    @pytest.mark.asyncio
    @patch("src.pipeline.get_video_meta")
    async def test_analyze_async(self, mock_get_meta):
        """Should run async analyze and return AnalysisReport."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        sample_3d = np.ones((10, 17, 3), dtype=np.float32)
        sample_2d = np.ones((10, 17, 2), dtype=np.float32) * 0.5
        phases = ElementPhase(name="waltz_jump", start=0, takeoff=3, peak=5, landing=7, end=9)

        pipeline = AnalysisPipeline()
        pipeline._extract_and_track = MagicMock(return_value=(sample_3d, 0))

        mock_normalizer = MagicMock()
        mock_normalizer.normalize = MagicMock(return_value=sample_2d)
        pipeline._get_normalizer = MagicMock(return_value=mock_normalizer)

        mock_smoother = MagicMock()
        mock_smoother.smooth = MagicMock(return_value=sample_2d)
        mock_smoother.smooth_phase_aware = MagicMock(return_value=sample_2d)
        pipeline._get_smoother = MagicMock(return_value=mock_smoother)

        mock_phase_result = MagicMock()
        mock_phase_result.phases = phases
        mock_phase_detector = MagicMock()
        mock_phase_detector.detect_phases = MagicMock(return_value=mock_phase_result)
        pipeline._get_phase_detector = MagicMock(return_value=mock_phase_detector)

        mock_metric = MetricResult(
            name="airtime",
            value=0.5,
            unit="s",
            is_good=True,
            reference_range=(0.3, 0.7),
        )
        mock_analyzer = MagicMock()
        mock_analyzer.analyze = MagicMock(return_value=[mock_metric])
        pipeline._get_analyzer_factory = MagicMock(return_value=lambda element_def: mock_analyzer)

        mock_recommender = MagicMock()
        mock_recommender.recommend = MagicMock(return_value=["Async recommendation"])
        pipeline._get_recommender = MagicMock(return_value=mock_recommender)

        report = await pipeline.analyze_async(Path("test.mp4"), element_type="waltz_jump")

        assert isinstance(report, AnalysisReport)
        assert report.element_type == "waltz_jump"
        assert report.recommendations == ["Async recommendation"]
        assert report.overall_score == 10.0

    @pytest.mark.asyncio
    @patch("src.pipeline.get_video_meta")
    async def test_analyze_async_no_element(self, mock_get_meta):
        """Should return basic report when no element type in async mode."""
        mock_get_meta.return_value = VideoMeta(
            path=Path("test.mp4"),
            width=640,
            height=480,
            fps=30.0,
            num_frames=10,
        )

        sample_3d = np.ones((10, 17, 3), dtype=np.float32)
        sample_2d = np.ones((10, 17, 2), dtype=np.float32) * 0.5

        pipeline = AnalysisPipeline()
        pipeline._extract_and_track = MagicMock(return_value=(sample_3d, 0))

        mock_normalizer = MagicMock()
        mock_normalizer.normalize = MagicMock(return_value=sample_2d)
        pipeline._get_normalizer = MagicMock(return_value=mock_normalizer)

        mock_smoother = MagicMock()
        mock_smoother.smooth = MagicMock(return_value=sample_2d)
        pipeline._get_smoother = MagicMock(return_value=mock_smoother)

        report = await pipeline.analyze_async(Path("test.mp4"))

        assert report.element_type == "unknown"
        assert report.metrics == []
        assert report.recommendations == []


@pytest.mark.integration
class TestAnalysisPipeline:
    """Integration tests for the full pipeline."""

    def test_pipeline_initialization(self):
        """Should initialize without errors."""
        pipeline = AnalysisPipeline()

        assert pipeline is not None

    def test_pipeline_without_reference(self):
        """Should work without reference store."""
        pipeline = AnalysisPipeline(reference_store=None)

        assert pipeline._reference_store is None

    def test_analyze_with_mock_data(self, sample_normalized_poses):
        """Should analyze mock pose data."""
        pipeline = AnalysisPipeline(reference_store=None)

        ElementPhase(
            name="three_turn",
            start=0,
            takeoff=0,
            peak=1,
            landing=0,
            end=2,
        )

        assert pipeline is not None

    def test_format_report(self):
        """Should format report correctly."""
        pipeline = AnalysisPipeline()

        from src.types import AnalysisReport, MetricResult

        phases = ElementPhase(
            name="test",
            start=0,
            takeoff=10,
            peak=20,
            landing=30,
            end=40,
        )

        metrics = [
            MetricResult(
                name="test_metric",
                value=0.5,
                unit="s",
                is_good=True,
                reference_range=(0.3, 0.7),
            )
        ]

        report = AnalysisReport(
            element_type="test_element",
            phases=phases,
            metrics=metrics,
            recommendations=["Test recommendation"],
            overall_score=7.5,
            dtw_distance=0.15,
        )

        formatted = pipeline.format_report(report)

        assert "АНАЛИЗ" in formatted
        assert "TEST_ELEMENT" in formatted
        assert "7.5" in formatted
        assert "Test recommendation" in formatted

    def test_compute_overall_score(self):
        """Should compute overall score correctly."""
        pipeline = AnalysisPipeline()

        from src.types import MetricResult

        metrics_good = [
            MetricResult(
                name="metric1",
                value=0.5,
                unit="s",
                is_good=True,
                reference_range=(0.3, 0.7),
            ),
            MetricResult(
                name="metric2",
                value=100,
                unit="deg",
                is_good=True,
                reference_range=(90, 110),
            ),
        ]

        score = pipeline._compute_overall_score(metrics_good)
        assert score == 10.0

        metrics_mixed = [
            MetricResult(
                name="metric1",
                value=0.5,
                unit="s",
                is_good=True,
                reference_range=(0.3, 0.7),
            ),
            MetricResult(
                name="metric2",
                value=50,
                unit="deg",
                is_good=False,
                reference_range=(90, 110),
            ),
        ]

        score = pipeline._compute_overall_score(metrics_mixed)
        assert score == 5.0

        metrics_bad = [
            MetricResult(
                name="metric1",
                value=0.1,
                unit="s",
                is_good=False,
                reference_range=(0.3, 0.7),
            ),
            MetricResult(
                name="metric2",
                value=50,
                unit="deg",
                is_good=False,
                reference_range=(90, 110),
            ),
        ]

        score = pipeline._compute_overall_score(metrics_bad)
        assert score == 0.0

    def test_compute_overall_score_empty_metrics(self):
        """Should return neutral score for empty metrics."""
        pipeline = AnalysisPipeline()

        score = pipeline._compute_overall_score([])
        assert score == 5.0


@pytest.mark.integration
class TestPipelineLazyLoading:
    """Test lazy loading of pipeline components.

    H3.6M Migration: Updated for new variable names.
    """

    def test_detector_lazy_load(self):
        """Should lazy-load person detector (requires onnxruntime-gpu)."""
        pytest.importorskip("onnxruntime")
        pipeline = AnalysisPipeline()

        assert pipeline._detector is None
        detector = pipeline._get_detector()
        assert detector is not None
        assert pipeline._detector is not None

    def test_pose_2d_extractor_lazy_load(self):
        """Should lazy-load PoseExtractor."""
        from pathlib import Path

        model_file = Path("data/models/moganet/moganet_b_ap2d_384x288.onnx")
        if not model_file.exists():
            pytest.skip("MogaNet-B model not available")

        pipeline = AnalysisPipeline()

        assert pipeline._pose_2d_extractor is None
        extractor = pipeline._get_pose_2d_extractor()
        assert extractor is not None
        assert pipeline._pose_2d_extractor is not None

    def test_normalizer_lazy_load(self):
        """Should lazy-load normalizer."""
        pipeline = AnalysisPipeline()

        assert pipeline._normalizer is None
        normalizer = pipeline._get_normalizer()
        assert normalizer is not None
        assert pipeline._normalizer is not None

    def test_phase_detector_lazy_load(self):
        """Should lazy-load phase detector."""
        pipeline = AnalysisPipeline()

        assert pipeline._phase_detector is None
        detector = pipeline._get_phase_detector()
        assert detector is not None
        assert pipeline._phase_detector is not None

    def test_aligner_lazy_load(self):
        """Should lazy-load aligner."""
        pipeline = AnalysisPipeline()

        assert pipeline._aligner is None
        aligner = pipeline._get_aligner()
        assert aligner is not None
        assert pipeline._aligner is not None

    def test_recommender_lazy_load(self):
        """Should lazy-load recommender."""
        pipeline = AnalysisPipeline()

        assert pipeline._recommender is None
        recommender = pipeline._get_recommender()
        assert recommender is not None
        assert pipeline._recommender is not None


# --------------------------------------------------------------------------- #
# #429 — pipeline must not hardcode PhysicsEngine body_mass; thread user weight
# --------------------------------------------------------------------------- #
class TestPipelineBodyMassPlumbing:
    def test_pipeline_does_not_hardcode_body_mass_70(self):
        """pipeline.py must thread the user's body mass into PhysicsEngine, not
        hardcode 70.0 kg, so moment_of_inertia/angular_momentum are per-user.
        The User model stores weight_kg (models/user.py:29). #429
        """
        import re

        pipeline_src = Path(__file__).resolve().parents[1] / "src" / "pipeline.py"
        text = pipeline_src.read_text(encoding="utf-8")
        hardcoded = re.findall(r"PhysicsEngine\(body_mass=70\.0\)", text)
        assert not hardcoded, (
            f"pipeline.py hardcodes PhysicsEngine(body_mass=70.0) "
            f"({len(hardcoded)} site(s)); user weight_kg from profile is ignored. "
            "Thread the user's weight_kg into the engine so "
            "moment_of_inertia/angular_momentum are per-user."
        )

    def test_analyze_accepts_body_mass_param(self):
        """analyze and analyze_async must expose a body_mass param so callers
        can pass the user's weight_kg (#429)."""
        import inspect

        from src.pipeline import AnalysisPipeline

        analyze_sig = inspect.signature(AnalysisPipeline.analyze)
        analyze_async_sig = inspect.signature(AnalysisPipeline.analyze_async)
        assert "body_mass" in analyze_sig.parameters, "analyze must accept body_mass"
        assert "body_mass" in analyze_async_sig.parameters, "analyze_async must accept body_mass"
