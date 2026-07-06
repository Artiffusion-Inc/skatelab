"""Tests for reference_builder module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.references.reference_builder import ReferenceBuilder
from src.types import ElementPhase, ReferenceData, TrackedExtraction, VideoMeta


@pytest.fixture
def sample_tracked_extraction():
    """Create a sample TrackedExtraction for testing."""
    poses = np.linspace(0, 1, 340).reshape(10, 17, 2).astype(np.float32)
    video_meta = VideoMeta(
        path=Path("test.mp4"),
        width=1920,
        height=1080,
        fps=30.0,
        num_frames=300,
    )
    return TrackedExtraction(
        poses=poses,
        frame_indices=np.arange(10),
        first_detection_frame=0,
        target_track_id=1,
        fps=30.0,
        video_meta=video_meta,
        first_frame=None,
    )


@pytest.fixture
def sample_element_phase():
    """Create a sample ElementPhase for testing."""
    return ElementPhase(
        name="waltz_jump",
        start=0,
        takeoff=3,
        peak=5,
        landing=7,
        end=9,
    )


@pytest.fixture
def mock_pose_extractor(sample_tracked_extraction):
    """Create a mock PoseExtractor."""
    extractor = MagicMock()
    extractor.extract_video_tracked.return_value = sample_tracked_extraction
    return extractor


@pytest.fixture
def mock_normalizer():
    """Create a mock PoseNormalizer."""
    normalizer = MagicMock()
    normalized = np.linspace(0.1, 0.9, 340).reshape(10, 17, 2).astype(np.float32)
    normalizer.normalize.return_value = normalized
    return normalizer


class TestReferenceBuilderBuildFromVideo:
    def test_build_from_video_returns_reference_data(
        self,
        tmp_path: Path,
        mock_pose_extractor,
        mock_normalizer,
        sample_element_phase,
    ):
        builder = ReferenceBuilder(mock_pose_extractor, mock_normalizer)
        video_path = tmp_path / "test_video.mp4"
        video_path.touch()

        mock_meta = VideoMeta(
            path=video_path,
            width=1920,
            height=1080,
            fps=30.0,
            num_frames=300,
        )

        with patch("src.references.reference_builder.get_video_meta", return_value=mock_meta):
            result = builder.build_from_video(
                video_path=video_path,
                element_type="waltz_jump",
                phases=sample_element_phase,
            )

        assert isinstance(result, ReferenceData)
        assert result.element_type == "waltz_jump"
        assert result.name == "test_video.mp4"
        assert result.fps == 30.0
        assert result.phases == sample_element_phase
        assert result.meta == mock_meta
        assert result.source == str(video_path)

        mock_pose_extractor.extract_video_tracked.assert_called_once_with(video_path)
        mock_normalizer.normalize.assert_called_once()

    def test_build_from_video_uses_normalized_poses(
        self,
        tmp_path: Path,
        mock_pose_extractor,
        mock_normalizer,
        sample_element_phase,
    ):
        builder = ReferenceBuilder(mock_pose_extractor, mock_normalizer)
        video_path = tmp_path / "test_video.mp4"
        video_path.touch()

        mock_meta = VideoMeta(
            path=video_path,
            width=1920,
            height=1080,
            fps=30.0,
            num_frames=300,
        )

        with patch("src.references.reference_builder.get_video_meta", return_value=mock_meta):
            result = builder.build_from_video(
                video_path=video_path,
                element_type="waltz_jump",
                phases=sample_element_phase,
            )

        np.testing.assert_array_almost_equal(result.poses, mock_normalizer.normalize.return_value)


class TestReferenceBuilderSaveReference:
    def test_save_reference_creates_npz(self, tmp_path: Path, mock_pose_extractor, mock_normalizer):
        builder = ReferenceBuilder(mock_pose_extractor, mock_normalizer)

        poses = np.linspace(0, 1, 170).reshape(5, 17, 2).astype(np.float32)
        phases = ElementPhase(
            name="waltz_jump",
            start=0,
            takeoff=2,
            peak=3,
            landing=4,
            end=5,
        )
        meta = VideoMeta(
            path=Path("test.mp4"),
            width=1920,
            height=1080,
            fps=30.0,
            num_frames=300,
        )
        ref = ReferenceData(
            element_type="waltz_jump",
            name="expert_waltz",
            poses=poses,
            phases=phases,
            fps=30.0,
            meta=meta,
            source="test.mp4",
        )

        output_dir = tmp_path / "refs"
        result = builder.save_reference(ref, output_dir)

        # #802: .stem strips the source extension — was .name → double ext
        # "waltz_jump_test.mp4.npz".
        assert result == output_dir / "waltz_jump_test.npz"
        assert result.exists()

        data = np.load(result)
        assert str(data["element_type"]) == "waltz_jump"
        assert str(data["source"]) == "test.mp4"
        np.testing.assert_array_almost_equal(data["poses"], poses)
        assert str(data["phases_name"]) == "waltz_jump"
        assert int(data["phases_start"]) == 0
        assert int(data["phases_takeoff"]) == 2
        assert int(data["phases_peak"]) == 3
        assert int(data["phases_landing"]) == 4
        assert int(data["phases_end"]) == 5
        assert float(data["meta_fps"]) == 30.0
        assert int(data["meta_width"]) == 1920
        assert int(data["meta_height"]) == 1080
        assert int(data["meta_num_frames"]) == 300
        assert str(data["meta_path"]) == "test.mp4"

    def test_save_reference_strips_source_extension_no_double_ext(
        self, tmp_path: Path, mock_pose_extractor, mock_normalizer
    ):
        """#802: source_path.name kept ".mp4" → "waltz_jump_expert.mp4.npz"
        (double extension). stem strips it. Also: refs differing only by
        source extension (expert.mp4 vs expert.mov) must map to one filename.
        """
        builder = ReferenceBuilder(mock_pose_extractor, mock_normalizer)
        poses = np.linspace(0, 1, 170).reshape(5, 17, 2).astype(np.float32)
        phases = ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=3, landing=4, end=5)
        meta = VideoMeta(path=Path("expert.mp4"), width=1920, height=1080, fps=30.0, num_frames=300)

        ref_mp4 = ReferenceData(
            element_type="waltz_jump",
            name="expert",
            poses=poses,
            phases=phases,
            fps=30.0,
            meta=meta,
            source="expert.mp4",
        )
        ref_mov = ReferenceData(
            element_type="waltz_jump",
            name="expert",
            poses=poses,
            phases=phases,
            fps=30.0,
            meta=meta,
            source="expert.mov",
        )

        out_mp4 = builder.save_reference(ref_mp4, tmp_path)
        out_mov = builder.save_reference(ref_mov, tmp_path / "mov")
        assert out_mp4.name == "waltz_jump_expert.npz", out_mp4.name
        assert out_mov.name == "waltz_jump_expert.npz", out_mov.name
        assert ".mp4" not in out_mp4.name and ".mov" not in out_mov.name

    def test_save_reference_without_meta(
        self, tmp_path: Path, mock_pose_extractor, mock_normalizer
    ):
        builder = ReferenceBuilder(mock_pose_extractor, mock_normalizer)

        poses = np.linspace(0, 1, 170).reshape(5, 17, 2).astype(np.float32)
        phases = ElementPhase(
            name="three_turn",
            start=0,
            takeoff=0,
            peak=2,
            landing=0,
            end=4,
        )
        ref = ReferenceData(
            element_type="three_turn",
            name="expert_three_turn",
            poses=poses,
            phases=phases,
            fps=30.0,
            meta=None,
            source="test.mp4",
        )

        output_dir = tmp_path / "refs"
        result = builder.save_reference(ref, output_dir)

        assert result.exists()
        data = np.load(result)
        assert float(data["meta_fps"]) == 30.0
        assert int(data["meta_width"]) == 1920
        assert int(data["meta_height"]) == 1080
        assert int(data["meta_num_frames"]) == len(poses)
        assert str(data["meta_path"]) == ""

    def test_save_reference_creates_output_dir(
        self, tmp_path: Path, mock_pose_extractor, mock_normalizer
    ):
        builder = ReferenceBuilder(mock_pose_extractor, mock_normalizer)

        poses = np.linspace(0, 1, 170).reshape(5, 17, 2).astype(np.float32)
        phases = ElementPhase(
            name="lutz",
            start=0,
            takeoff=2,
            peak=3,
            landing=4,
            end=5,
        )
        ref = ReferenceData(
            element_type="lutz",
            name="expert_lutz",
            poses=poses,
            phases=phases,
            fps=30.0,
            meta=None,
            source="test.mp4",
        )

        nested_dir = tmp_path / "nested" / "refs"
        result = builder.save_reference(ref, nested_dir)

        assert nested_dir.exists()
        assert result.exists()


class TestReferenceBuilderLoadReference:
    def test_load_reference(self, tmp_path: Path, mock_pose_extractor, mock_normalizer):
        builder = ReferenceBuilder(mock_pose_extractor, mock_normalizer)

        poses = np.linspace(0, 1, 170).reshape(5, 17, 2).astype(np.float32)

        npz_path = tmp_path / "ref.npz"
        np.savez_compressed(
            npz_path,
            element_type="waltz_jump",
            poses=poses,
            meta_fps=30.0,
            meta_width=1920,
            meta_height=1080,
            meta_num_frames=300,
            meta_path="",
            phases_name="waltz_jump",
            phases_start=0,
            phases_takeoff=2,
            phases_peak=3,
            phases_landing=4,
            phases_end=5,
            source="test.mp4",
        )

        result = builder.load_reference(npz_path)

        assert isinstance(result, ReferenceData)
        assert result.element_type == "waltz_jump"
        assert result.source == "test.mp4"
        np.testing.assert_array_almost_equal(result.poses, poses)
        assert result.phases.name == "waltz_jump"
        assert result.phases.start == 0
        assert result.phases.takeoff == 2
        assert result.phases.peak == 3
        assert result.phases.landing == 4
        assert result.phases.end == 5
        assert result.fps == 30.0
        assert result.meta is not None
        assert result.meta.fps == 30.0
        assert result.meta.width == 1920
        assert result.meta.height == 1080
        assert result.meta.num_frames == 300

    def test_load_reference_with_meta_path(
        self, tmp_path: Path, mock_pose_extractor, mock_normalizer
    ):
        builder = ReferenceBuilder(mock_pose_extractor, mock_normalizer)

        poses = np.linspace(0, 1, 170).reshape(5, 17, 2).astype(np.float32)

        npz_path = tmp_path / "ref.npz"
        np.savez_compressed(
            npz_path,
            element_type="three_turn",
            poses=poses,
            meta_fps=60.0,
            meta_width=1280,
            meta_height=720,
            meta_num_frames=120,
            meta_path="/videos/expert.mp4",
            phases_name="three_turn",
            phases_start=0,
            phases_takeoff=0,
            phases_peak=5,
            phases_landing=0,
            phases_end=10,
            source="expert.mp4",
        )

        result = builder.load_reference(npz_path)

        assert result.meta is not None
        assert result.meta.path == Path("/videos/expert.mp4")
        assert result.meta.fps == 60.0
        assert result.meta.width == 1280
        assert result.meta.height == 720
        assert result.meta.num_frames == 120
        assert result.name == "expert.mp4"

    def test_load_reference_fallback_fps(
        self, tmp_path: Path, mock_pose_extractor, mock_normalizer
    ):
        """Test that fps falls back to meta.fps when 'fps' key is missing in npz."""
        builder = ReferenceBuilder(mock_pose_extractor, mock_normalizer)

        poses = np.linspace(0, 1, 170).reshape(5, 17, 2).astype(np.float32)

        npz_path = tmp_path / "ref.npz"
        np.savez_compressed(
            npz_path,
            element_type="loop",
            poses=poses,
            meta_fps=25.0,
            meta_width=1920,
            meta_height=1080,
            meta_num_frames=250,
            meta_path="",
            phases_name="loop",
            phases_start=0,
            phases_takeoff=2,
            phases_peak=3,
            phases_landing=4,
            phases_end=5,
            source="test.mp4",
        )

        result = builder.load_reference(npz_path)
        # 'fps' key is not written by save_reference; falls back to meta.fps
        assert result.fps == 25.0
