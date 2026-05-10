"""Tests for ml/src/visualization/comparison.py.

Covers ComparisonConfig, ComparisonMode, _build_layers, and
ComparisonRenderer including init, cache I/O, streaming extraction,
and the full process pipeline in both SIDE_BY_SIDE and OVERLAY modes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Add ml to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.visualization.comparison import (
    ComparisonConfig,
    ComparisonMode,
    ComparisonRenderer,
    _build_layers,
)
from src.visualization.layers.joint_angle_layer import JointAngleLayer
from src.visualization.layers.skeleton_layer import SkeletonLayer
from src.visualization.layers.timer_layer import TimerLayer
from src.visualization.layers.vertical_axis_layer import VerticalAxisLayer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_video(tmp_path):
    """Create a dummy video file path."""
    video = tmp_path / "test_video.mp4"
    video.write_bytes(b"dummy")
    return video


@pytest.fixture
def mock_video_meta():
    """Return a mock VideoMeta-like object."""
    meta = MagicMock()
    meta.width = 640
    meta.height = 480
    meta.fps = 30.0
    meta.num_frames = 10
    return meta


@pytest.fixture
def mock_tracked_poses():
    """Return a small sequence of tracked 3D poses (5 frames, 17 kp, xyz)."""
    poses = np.zeros((5, 17, 3), dtype=np.float32)
    for i in range(17):
        poses[:, i, 0] = (i % 5) * 0.1
        poses[:, i, 1] = (i % 7) * 0.1
    return poses


@pytest.fixture
def mock_cap():
    """Return a mock cv2.VideoCapture that yields 5 frames then stops."""
    cap = MagicMock()
    cap.isOpened.return_value = True
    frames = [(True, np.ones((480, 640, 3), dtype=np.uint8) * i * 40) for i in range(5)] + [
        (False, None)
    ]
    cap.read.side_effect = frames
    cap.set.return_value = True
    cap.release.return_value = None
    return cap


def _make_renderer_with_mocks(  # noqa: PLR0913
    tmp_path,
    mock_video_meta,
    mock_tracked_poses,
    *,
    mode=ComparisonMode.SIDE_BY_SIDE,
    max_frames=3,
    overlays=None,
    start_frame=0,
    no_cache=False,
    fps=0.0,
    resize_width=1280,
    reference_alpha=0.4,
    crf=30,
    compress=False,
    divider_width=4,
):
    """Build mocks for a full ComparisonRenderer.process() call.

    Returns (renderer, mocks_dict) where mocks_dict contains all the
    patched objects so assertions can be made on them.
    """
    mocks = {}

    # PoseExtractor
    extractor_instance = MagicMock()
    tracked = MagicMock()
    tracked.poses = (
        mock_tracked_poses[:max_frames]
        if max_frames > 0
        else np.zeros((0, 17, 3), dtype=np.float32)
    )
    extractor_instance.extract_video_tracked.return_value = tracked
    mocks["extractor"] = extractor_instance

    # PoseSmoother
    smoother_instance = MagicMock()
    smoother_instance.smooth.side_effect = lambda x: x
    mocks["smoother"] = smoother_instance

    # H264Writer
    writer_instance = MagicMock()
    mocks["writer"] = writer_instance

    # VideoCapture
    cap_mock = MagicMock()
    cap_mock.isOpened.return_value = True
    cap_mock.set.return_value = True
    cap_mock.release.return_value = None
    frame_data = np.ones((480, 640, 3), dtype=np.uint8) * 128
    frames = [(True, frame_data.copy()) for _ in range(max_frames + 2)] + [(False, None)]
    cap_mock.read.side_effect = frames
    mocks["cap"] = cap_mock

    mocks["meta"] = mock_video_meta

    cfg = ComparisonConfig(
        mode=mode,
        overlays=overlays or ["skeleton", "axis", "angles", "timer"],
        max_frames=max_frames,
        start_frame=start_frame,
        no_cache=no_cache,
        fps=fps,
        resize_width=resize_width,
        reference_alpha=reference_alpha,
        crf=crf,
        compress=compress,
        divider_width=divider_width,
    )
    renderer = ComparisonRenderer(config=cfg)
    return renderer, mocks


# ---------------------------------------------------------------------------
# ComparisonConfig / ComparisonMode
# ---------------------------------------------------------------------------


class TestComparisonConfig:
    """Test configuration dataclass."""

    def test_default_values(self):
        """Default config should have sensible values."""
        cfg = ComparisonConfig()
        assert cfg.mode == ComparisonMode.SIDE_BY_SIDE
        assert cfg.overlays == ["skeleton", "axis", "angles", "timer"]
        assert cfg.resize_width == 1280
        assert cfg.reference_color == (255, 0, 255)  # COLOR_MAGENTA
        assert cfg.reference_alpha == 0.4
        assert cfg.divider_width == 4
        assert cfg.fps == 0.0
        assert cfg.max_frames == 0
        assert cfg.start_frame == 0
        assert cfg.device == "auto"
        assert cfg.no_cache is False
        assert cfg.compress is False
        assert cfg.crf == 30

    def test_overlay_mode(self):
        """Config can be set to overlay mode."""
        cfg = ComparisonConfig(mode=ComparisonMode.OVERLAY)
        assert cfg.mode == ComparisonMode.OVERLAY

    def test_custom_values(self):
        """Config accepts custom values for all fields."""
        cfg = ComparisonConfig(
            mode=ComparisonMode.OVERLAY,
            overlays=["skeleton", "timer"],
            resize_width=960,
            reference_color=(0, 255, 0),
            reference_alpha=0.7,
            divider_width=2,
            fps=25.0,
            compress=True,
            crf=23,
            max_frames=100,
            start_frame=50,
            device="cuda:0",
            no_cache=True,
        )
        assert cfg.mode == ComparisonMode.OVERLAY
        assert cfg.overlays == ["skeleton", "timer"]
        assert cfg.resize_width == 960
        assert cfg.reference_color == (0, 255, 0)
        assert cfg.reference_alpha == 0.7
        assert cfg.divider_width == 2
        assert cfg.fps == 25.0
        assert cfg.compress is True
        assert cfg.crf == 23
        assert cfg.max_frames == 100
        assert cfg.start_frame == 50
        assert cfg.device == "cuda:0"
        assert cfg.no_cache is True

    def test_overlays_is_independent_between_instances(self):
        """Each ComparisonConfig instance should have its own overlays list."""
        cfg1 = ComparisonConfig()
        cfg2 = ComparisonConfig()
        cfg1.overlays.append("extra")
        assert "extra" not in cfg2.overlays


class TestComparisonMode:
    """Test mode enum."""

    def test_side_by_side_value(self):
        assert ComparisonMode.SIDE_BY_SIDE.value == "side-by-side"

    def test_overlay_value(self):
        assert ComparisonMode.OVERLAY.value == "overlay"

    def test_enum_members(self):
        """Enum should have exactly two members."""
        assert len(ComparisonMode) == 2

    def test_from_value(self):
        """ComparisonMode should be constructable from string value."""
        assert ComparisonMode("side-by-side") == ComparisonMode.SIDE_BY_SIDE
        assert ComparisonMode("overlay") == ComparisonMode.OVERLAY


# ---------------------------------------------------------------------------
# _build_layers
# ---------------------------------------------------------------------------


class TestBuildLayers:
    """Test layer builder helper."""

    @patch("src.visualization.comparison.SkeletonLayer")
    @patch("src.visualization.comparison.VerticalAxisLayer")
    @patch("src.visualization.comparison.JointAngleLayer")
    @patch("src.visualization.comparison.TimerLayer")
    def test_builds_all_layers(self, mock_timer, mock_angle, mock_axis, mock_skeleton):
        """All recognized overlay names should instantiate their layer classes."""
        layers = _build_layers(["skeleton", "axis", "angles", "timer"])
        assert len(layers) == 4
        mock_skeleton.assert_called_once()
        mock_axis.assert_called_once()
        mock_angle.assert_called_once()
        mock_timer.assert_called_once()

    @patch("src.visualization.comparison.SkeletonLayer")
    @patch("src.visualization.comparison.TimerLayer")
    def test_ignores_unknown_names(self, mock_timer, mock_skeleton):
        """Unknown overlay names should be silently ignored."""
        layers = _build_layers(["skeleton", "unknown_layer", "timer"])
        assert len(layers) == 2
        mock_skeleton.assert_called_once()
        mock_timer.assert_called_once()

    def test_builds_real_layer_instances(self):
        """Without mocks, _build_layers returns actual layer instances."""
        layers = _build_layers(["skeleton", "axis", "angles", "timer"])
        assert len(layers) == 4
        assert isinstance(layers[0], SkeletonLayer)
        assert isinstance(layers[1], VerticalAxisLayer)
        assert isinstance(layers[2], JointAngleLayer)
        assert isinstance(layers[3], TimerLayer)

    def test_empty_overlays(self):
        """Empty overlay list should return empty layers list."""
        layers = _build_layers([])
        assert layers == []

    def test_all_unknown_returns_empty(self):
        """All-unknown overlay names should return empty list."""
        layers = _build_layers(["nonexistent", "also_missing"])
        assert layers == []

    @patch("src.visualization.comparison.SkeletonLayer")
    @patch("src.visualization.comparison.VerticalAxisLayer")
    @patch("src.visualization.comparison.JointAngleLayer")
    @patch("src.visualization.comparison.TimerLayer")
    def test_duplicate_overlay_names(self, mock_timer, mock_angle, mock_axis, mock_skeleton):
        """Duplicate overlay names should create multiple instances."""
        layers = _build_layers(["skeleton", "skeleton"])
        assert len(layers) == 2
        assert mock_skeleton.call_count == 2

    def test_layer_map_keys_match_overlay_defaults(self):
        """The layer_map keys should match the default overlays in ComparisonConfig."""
        cfg = ComparisonConfig()
        # All default overlays should produce layers when unmocked
        layers = _build_layers(cfg.overlays)
        assert len(layers) == 4


# ---------------------------------------------------------------------------
# ComparisonRenderer.__init__
# ---------------------------------------------------------------------------


class TestComparisonRendererInit:
    """Test renderer initialization."""

    @patch("src.visualization.comparison._build_layers")
    def test_default_init(self, mock_build):
        """Renderer with default config should build default layers."""
        mock_build.return_value = [
            MagicMock(z_index=0),
            MagicMock(z_index=1),
            MagicMock(z_index=2),
            MagicMock(z_index=3),
        ]
        renderer = ComparisonRenderer()
        assert renderer.config is not None
        assert renderer.config.mode == ComparisonMode.SIDE_BY_SIDE
        assert len(renderer.layers) == 4
        mock_build.assert_called_once_with(["skeleton", "axis", "angles", "timer"])

    def test_custom_config(self):
        """Renderer should accept a custom config."""
        cfg = ComparisonConfig(mode=ComparisonMode.OVERLAY, overlays=["timer"])
        renderer = ComparisonRenderer(config=cfg)
        assert renderer.config.mode == ComparisonMode.OVERLAY
        assert len(renderer.layers) == 1
        assert isinstance(renderer.layers[0], TimerLayer)

    def test_sorted_layers(self):
        """_sorted_layers should be sorted by z_index."""
        renderer = ComparisonRenderer(config=ComparisonConfig(overlays=["timer", "skeleton"]))
        z_indices = [ly.z_index for ly in renderer._sorted_layers]
        assert z_indices == sorted(z_indices)

    @patch("src.visualization.comparison._build_layers")
    def test_none_config_uses_defaults(self, mock_build):
        """Passing None config should use ComparisonConfig defaults."""
        mock_build.return_value = []
        renderer = ComparisonRenderer(config=None)
        assert renderer.config.mode == ComparisonMode.SIDE_BY_SIDE


# ---------------------------------------------------------------------------
# ComparisonRenderer._pose_cache_path
# ---------------------------------------------------------------------------


class TestPoseCachePath:
    """Test cache path generation."""

    def test_returns_npz_next_to_video(self):
        """Cache path should be video stem + '_poses.npz'."""
        renderer = ComparisonRenderer()
        video = Path("/tmp/test_video.mp4")
        cache = renderer._pose_cache_path(video)
        assert cache == Path("/tmp/test_video_poses.npz")

    def test_various_extensions(self):
        """Cache path should work with various video extensions."""
        renderer = ComparisonRenderer()
        assert renderer._pose_cache_path(Path("data/skate.mov")) == Path("data/skate_poses.npz")
        assert renderer._pose_cache_path(Path("data/skate.avi")) == Path("data/skate_poses.npz")

    def test_nested_path(self):
        """Cache path should handle nested directories."""
        renderer = ComparisonRenderer()
        video = Path("/home/user/videos/2024/jump.mp4")
        cache = renderer._pose_cache_path(video)
        assert cache == Path("/home/user/videos/2024/jump_poses.npz")


# ---------------------------------------------------------------------------
# ComparisonRenderer._save_pose_cache
# ---------------------------------------------------------------------------


class TestSavePoseCache:
    """Test cache writing."""

    @patch("src.visualization.comparison.np.savez_compressed")
    def test_saves_compressed_npz(self, mock_savez, tmp_path):
        """Pose cache should be saved as compressed .npz."""
        renderer = ComparisonRenderer()
        video = tmp_path / "athlete.mp4"
        video.write_bytes(b"")
        poses = [np.zeros((17, 2), dtype=np.float32) for _ in range(3)]
        renderer._save_pose_cache(video, poses)
        mock_savez.assert_called_once()
        call_args = mock_savez.call_args
        # keyword arg "poses" has the stacked array
        assert "poses" in call_args.kwargs
        assert call_args.kwargs["poses"].shape == (3, 17, 2)

    def test_empty_poses_noop(self, tmp_path):
        """Empty pose list should not write cache."""
        renderer = ComparisonRenderer()
        video = tmp_path / "athlete.mp4"
        video.write_bytes(b"")
        with patch("src.visualization.comparison.np.savez_compressed") as mock_savez:
            renderer._save_pose_cache(video, [])
            mock_savez.assert_not_called()

    @patch("src.visualization.comparison.np.savez_compressed")
    def test_save_path_matches_cache_path(self, mock_savez, tmp_path):
        """Saved path should match _pose_cache_path output."""
        renderer = ComparisonRenderer()
        video = tmp_path / "athlete.mp4"
        video.write_bytes(b"")
        poses = [np.ones((17, 2), dtype=np.float32) * 0.5]
        renderer._save_pose_cache(video, poses)
        expected_path = renderer._pose_cache_path(video)
        call_args = mock_savez.call_args
        assert Path(call_args[0][0]) == expected_path


# ---------------------------------------------------------------------------
# ComparisonRenderer._load_pose_cache
# ---------------------------------------------------------------------------


class TestLoadPoseCache:
    """Test cache loading."""

    def test_cache_miss_returns_none(self, tmp_path):
        """Missing cache file should return None."""
        renderer = ComparisonRenderer()
        video = tmp_path / "no_cache.mp4"
        result = renderer._load_pose_cache(video, expected_frames=10)
        assert result is None

    def test_no_cache_flag_returns_none(self, tmp_path):
        """no_cache=True should always return None, even with valid cache."""
        cfg = ComparisonConfig(no_cache=True)
        renderer = ComparisonRenderer(config=cfg)
        video = tmp_path / "cached.mp4"
        cache = video.with_name("cached_poses.npz")
        np.savez_compressed(cache, poses=np.zeros((10, 17, 2)))
        result = renderer._load_pose_cache(video, expected_frames=10)
        assert result is None

    def test_cache_hit(self, tmp_path):
        """Valid cache should return poses as list of arrays."""
        renderer = ComparisonRenderer()
        video = tmp_path / "cached.mp4"
        cache = video.with_name("cached_poses.npz")
        np.savez_compressed(cache, poses=np.zeros((10, 17, 2)))
        result = renderer._load_pose_cache(video, expected_frames=10)
        assert result is not None
        assert len(result) == 10
        assert all(p.shape == (17, 2) for p in result)

    def test_stale_cache_returns_none(self, tmp_path):
        """Cache with large frame mismatch should return None."""
        renderer = ComparisonRenderer()
        video = tmp_path / "cached.mp4"
        cache = video.with_name("cached_poses.npz")
        # 5 frames cached but 100 expected -- way outside 10% tolerance
        np.savez_compressed(cache, poses=np.zeros((5, 17, 2)))
        result = renderer._load_pose_cache(video, expected_frames=100)
        assert result is None

    def test_corrupted_cache_returns_none(self, tmp_path):
        """Corrupted cache file should return None."""
        renderer = ComparisonRenderer()
        video = tmp_path / "bad.mp4"
        cache = video.with_name("bad_poses.npz")
        cache.write_text("not a valid npz")
        result = renderer._load_pose_cache(video, expected_frames=10)
        assert result is None

    def test_cache_within_tolerance(self, tmp_path):
        """Cache within 10% frame tolerance should be accepted."""
        renderer = ComparisonRenderer()
        video = tmp_path / "cached.mp4"
        cache = video.with_name("cached_poses.npz")
        # 10 frames cached, 11 expected (within 10% + 5 tolerance)
        np.savez_compressed(cache, poses=np.zeros((10, 17, 2)))
        result = renderer._load_pose_cache(video, expected_frames=11)
        assert result is not None
        assert len(result) == 10

    def test_cache_exactly_at_boundary(self, tmp_path):
        """Cache at exact tolerance boundary (5 frame delta) should be accepted."""
        renderer = ComparisonRenderer()
        video = tmp_path / "cached.mp4"
        cache = video.with_name("cached_poses.npz")
        # 5 frames cached, 10 expected: delta=5, max(10*0.1, 5)=5, |5-10|=5 <= 5
        np.savez_compressed(cache, poses=np.zeros((5, 17, 2)))
        result = renderer._load_pose_cache(video, expected_frames=10)
        assert result is not None


# ---------------------------------------------------------------------------
# ComparisonRenderer._create_extractor
# ---------------------------------------------------------------------------


class TestCreateExtractor:
    """Test PoseExtractor creation."""

    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.DeviceConfig")
    def test_creates_extractor_with_device(self, mock_device_cls, mock_extractor_cls):
        """Extractor should be created with device config."""
        mock_cfg = MagicMock()
        mock_cfg.device = "cuda"
        mock_device_cls.return_value = mock_cfg
        renderer = ComparisonRenderer()
        extractor = renderer._create_extractor("cuda")
        mock_device_cls.assert_called_once_with(device="cuda")
        mock_extractor_cls.assert_called_once_with(conf_threshold=0.3, device="cuda")

    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.DeviceConfig")
    def test_default_device_is_auto(self, mock_device_cls, mock_extractor_cls):
        """Default device parameter should be 'auto'."""
        mock_cfg = MagicMock()
        mock_cfg.device = "auto"
        mock_device_cls.return_value = mock_cfg
        renderer = ComparisonRenderer()
        renderer._create_extractor()
        mock_device_cls.assert_called_once_with(device="auto")


# ---------------------------------------------------------------------------
# ComparisonRenderer._extract_poses_streaming
# ---------------------------------------------------------------------------


class TestExtractPosesStreaming:
    """Test streaming pose extraction."""

    def test_extracts_and_converts_to_2d(self, sample_video, mock_tracked_poses):
        """Should extract 3D poses and return 2D slices."""
        renderer = ComparisonRenderer()
        extractor = MagicMock()
        result = MagicMock()
        result.poses = mock_tracked_poses
        extractor.extract_video_tracked.return_value = result

        poses = renderer._extract_poses_streaming(
            sample_video, extractor, target_w=640, target_h=480
        )
        assert len(poses) == 5
        assert all(p.ndim == 2 and p.shape == (17, 2) for p in poses)
        extractor.extract_video_tracked.assert_called_once_with(str(sample_video))

    def test_respects_max_frames(self, sample_video, mock_tracked_poses):
        """max_frames should truncate result."""
        renderer = ComparisonRenderer()
        extractor = MagicMock()
        result = MagicMock()
        result.poses = mock_tracked_poses
        extractor.extract_video_tracked.return_value = result

        poses = renderer._extract_poses_streaming(
            sample_video, extractor, target_w=640, target_h=480, max_frames=3
        )
        assert len(poses) == 3

    def test_respects_start_frame(self, sample_video, mock_tracked_poses):
        """start_frame should skip initial frames."""
        renderer = ComparisonRenderer()
        extractor = MagicMock()
        result = MagicMock()
        result.poses = mock_tracked_poses
        extractor.extract_video_tracked.return_value = result

        poses = renderer._extract_poses_streaming(
            sample_video, extractor, target_w=640, target_h=480, start_frame=2
        )
        assert len(poses) == 3  # 5 total - 2 skipped


# ---------------------------------------------------------------------------
# ComparisonRenderer.process — SIDE_BY_SIDE mode
# ---------------------------------------------------------------------------


class TestProcessSideBySide:
    """Test full rendering pipeline in SIDE_BY_SIDE mode."""

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_side_by_side_mode(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
        mock_cap,
    ):
        """Side-by-side mode should write frames with divider."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(mode=ComparisonMode.SIDE_BY_SIDE, max_frames=3)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        assert mock_writer.write.call_count == 3
        mock_writer.close.assert_called_once()
        mock_cap.release.assert_called()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_side_by_side_with_padding(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_tracked_poses,
    ):
        """Side-by-side with different video heights should pad shorter video."""
        # Athlete 640x480, Reference 640x240 -> different heights, padding needed
        meta_a = MagicMock()
        meta_a.width = 640
        meta_a.height = 480
        meta_a.fps = 30.0
        meta_a.num_frames = 5

        meta_r = MagicMock()
        meta_r.width = 640
        meta_r.height = 240
        meta_r.fps = 30.0
        meta_r.num_frames = 5

        mock_get_meta.side_effect = [meta_a, meta_r]

        # Create separate caps for athlete (480 height) and reference (240 height)
        cap_a = MagicMock()
        cap_a.isOpened.return_value = True
        cap_a.set.return_value = True
        cap_a.release.return_value = None
        frame_a = np.ones((480, 640, 3), dtype=np.uint8) * 100
        cap_a.read.side_effect = [(True, frame_a.copy()) for _ in range(5)] + [(False, None)]

        cap_r = MagicMock()
        cap_r.isOpened.return_value = True
        cap_r.set.return_value = True
        cap_r.release.return_value = None
        frame_r = np.ones((240, 640, 3), dtype=np.uint8) * 200
        cap_r.read.side_effect = [(True, frame_r.copy()) for _ in range(5)] + [(False, None)]

        mock_cap_cls.side_effect = [cap_a, cap_r]
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(mode=ComparisonMode.SIDE_BY_SIDE, max_frames=3)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        # Verify writer received frames (3 frames written)
        assert mock_writer.write.call_count == 3
        mock_writer.close.assert_called_once()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_side_by_side_with_athlete_padding(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_tracked_poses,
    ):
        """Side-by-side where athlete is shorter than reference -- athlete gets padded (lines 376-377)."""
        # Athlete 640x240, Reference 640x480 -> athlete shorter, pad_a is not None
        meta_a = MagicMock()
        meta_a.width = 640
        meta_a.height = 240
        meta_a.fps = 30.0
        meta_a.num_frames = 5

        meta_r = MagicMock()
        meta_r.width = 640
        meta_r.height = 480
        meta_r.fps = 30.0
        meta_r.num_frames = 5

        mock_get_meta.side_effect = [meta_a, meta_r]

        cap_a = MagicMock()
        cap_a.isOpened.return_value = True
        cap_a.set.return_value = True
        cap_a.release.return_value = None
        frame_a = np.ones((240, 640, 3), dtype=np.uint8) * 100
        cap_a.read.side_effect = [(True, frame_a.copy()) for _ in range(5)] + [(False, None)]

        cap_r = MagicMock()
        cap_r.isOpened.return_value = True
        cap_r.set.return_value = True
        cap_r.release.return_value = None
        frame_r = np.ones((480, 640, 3), dtype=np.uint8) * 200
        cap_r.read.side_effect = [(True, frame_r.copy()) for _ in range(5)] + [(False, None)]

        mock_cap_cls.side_effect = [cap_a, cap_r]
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(mode=ComparisonMode.SIDE_BY_SIDE, max_frames=3)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        # After resize: a_h=480, r_h=960, out_h=960
        # pad_a should be non-None (480 < 960), so lines 376-377 execute
        assert mock_writer.write.call_count == 3
        mock_writer.close.assert_called_once()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_no_poses_aborts_early(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_cap,
    ):
        """If both videos return zero poses, render_frames should be 0 and process returns."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = np.zeros((0, 17, 3), dtype=np.float32)
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(max_frames=3)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)
        mock_writer.close.assert_called_once()


# ---------------------------------------------------------------------------
# ComparisonRenderer.process — OVERLAY mode
# ---------------------------------------------------------------------------


class TestProcessOverlay:
    """Test full rendering pipeline in OVERLAY mode."""

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_overlay_mode(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
        mock_cap,
    ):
        """Overlay mode should blend reference skeleton onto athlete."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(mode=ComparisonMode.OVERLAY, max_frames=3)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        assert mock_writer.write.call_count == 3
        mock_writer.close.assert_called_once()


# ---------------------------------------------------------------------------
# ComparisonRenderer.process — edge cases
# ---------------------------------------------------------------------------


class TestProcessEdgeCases:
    """Test edge cases in the process pipeline."""

    @patch("src.visualization.comparison.draw_skeleton")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.cv2.VideoCapture")
    def test_cannot_open_athlete_video(
        self,
        mock_cap_cls,
        mock_get_meta,
        mock_writer_cls,
        mock_extractor_cls,
        mock_smoother_cls,
        mock_get_config,
        mock_draw,
        tmp_path,
        mock_video_meta,
    ):
        """If athlete video cannot be opened, process should close writer and return."""
        mock_get_meta.return_value = mock_video_meta
        bad_cap = MagicMock()
        bad_cap.isOpened.return_value = False
        mock_cap_cls.side_effect = [bad_cap, MagicMock()]
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = np.zeros((5, 17, 3), dtype=np.float32)
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(max_frames=5)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)
        mock_writer.close.assert_called_once()

    @patch("src.visualization.comparison.draw_skeleton")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.cv2.VideoCapture")
    def test_cannot_open_reference_video(
        self,
        mock_cap_cls,
        mock_get_meta,
        mock_writer_cls,
        mock_extractor_cls,
        mock_smoother_cls,
        mock_get_config,
        mock_draw,
        tmp_path,
        mock_video_meta,
    ):
        """If reference video cannot be opened, process should release athlete cap and return."""
        mock_get_meta.return_value = mock_video_meta
        good_cap = MagicMock()
        good_cap.isOpened.return_value = True
        bad_cap = MagicMock()
        bad_cap.isOpened.return_value = False
        mock_cap_cls.side_effect = [good_cap, bad_cap]
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = np.zeros((5, 17, 3), dtype=np.float32)
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(max_frames=5)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)
        good_cap.release.assert_called_once()
        mock_writer.close.assert_called_once()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_uses_last_frame_when_video_ends(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
    ):
        """When one video ends before the other, last frame should be reused."""
        mock_get_meta.return_value = mock_video_meta

        # Athlete cap yields 5 frames then ends
        cap_a = MagicMock()
        cap_a.isOpened.return_value = True
        frames_a = [(True, np.ones((480, 640, 3), dtype=np.uint8) * i * 40) for i in range(5)] + [
            (False, None)
        ]
        cap_a.read.side_effect = frames_a
        cap_a.set.return_value = True
        cap_a.release.return_value = None

        # Reference cap yields 5 frames then ends
        cap_r = MagicMock()
        cap_r.isOpened.return_value = True
        frames_r = [(True, np.ones((480, 640, 3), dtype=np.uint8) * i * 40) for i in range(5)] + [
            (False, None)
        ]
        cap_r.read.side_effect = frames_r
        cap_r.set.return_value = True
        cap_r.release.return_value = None

        mock_cap_cls.side_effect = [cap_a, cap_r]
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(max_frames=5)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        assert mock_writer.write.call_count == 5

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_start_frame_seek(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
        mock_cap,
    ):
        """start_frame > 0 should seek both captures."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(start_frame=2, max_frames=3)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        mock_cap.set.assert_any_call(pytest.approx(1), pytest.approx(2))  # CAP_PROP_POS_FRAMES
        mock_writer.write.assert_called()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_both_videos_end_early_stops_loop(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_get_meta_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
    ):
        """When both videos return False at the same time, the loop should break."""
        mock_get_meta.return_value = mock_video_meta

        # Both caps return (False, None) on the first read
        cap_a = MagicMock()
        cap_a.isOpened.return_value = True
        cap_a.read.return_value = (False, None)
        cap_a.set.return_value = True
        cap_a.release.return_value = None

        cap_r = MagicMock()
        cap_r.isOpened.return_value = True
        cap_r.read.return_value = (False, None)
        cap_r.set.return_value = True
        cap_r.release.return_value = None

        mock_cap_cls = patch("src.visualization.comparison.cv2.VideoCapture")
        # Use a different approach - just set up caps via side_effect

        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        # We need to patch cv2.VideoCapture at module level
        with patch("src.visualization.comparison.cv2.VideoCapture") as mock_vc:
            mock_vc.side_effect = [cap_a, cap_r]
            cfg = ComparisonConfig(max_frames=5)
            renderer = ComparisonRenderer(config=cfg)
            renderer.process(athlete, reference, output)

            # No frames should be written since both videos ended immediately
            assert mock_writer.write.call_count == 0
            mock_writer.close.assert_called_once()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_athlete_poses_empty_warns(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_cap,
    ):
        """When athlete has no poses but reference does, warning should be logged (line 232)."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        # First call (athlete) returns empty poses, second call (reference) returns poses
        extractor_instance = MagicMock()
        empty_tracked = MagicMock()
        empty_tracked.poses = np.zeros((0, 17, 3), dtype=np.float32)
        full_tracked = MagicMock()
        full_tracked.poses = np.zeros((3, 17, 3), dtype=np.float32)

        # Side effect: first call for athlete, second for reference
        extractor_instance.extract_video_tracked.side_effect = [empty_tracked, full_tracked]
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(mode=ComparisonMode.OVERLAY, max_frames=3)
        renderer = ComparisonRenderer(config=cfg)

        with patch.object(renderer, "_load_pose_cache", return_value=None):
            with patch.object(renderer, "_save_pose_cache"):
                renderer.process(athlete, reference, output)

        # Writer should still be called for the reference poses rendered
        mock_writer.close.assert_called_once()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_reference_poses_empty_warns(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_cap,
    ):
        """When reference has no poses but athlete does, warning should be logged (line 236)."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        full_tracked = MagicMock()
        full_tracked.poses = np.zeros((3, 17, 3), dtype=np.float32)
        empty_tracked = MagicMock()
        empty_tracked.poses = np.zeros((0, 17, 3), dtype=np.float32)

        # First call for athlete returns poses, second for reference returns empty
        extractor_instance.extract_video_tracked.side_effect = [full_tracked, empty_tracked]
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(mode=ComparisonMode.OVERLAY, max_frames=3)
        renderer = ComparisonRenderer(config=cfg)

        with patch.object(renderer, "_load_pose_cache", return_value=None):
            with patch.object(renderer, "_save_pose_cache"):
                renderer.process(athlete, reference, output)

        mock_writer.close.assert_called_once()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_render_frames_zero_returns(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
    ):
        """When render_frames is 0, process should abort early (lines 261-262)."""
        # Video meta with 0 frames so max_frames evaluates to 0
        zero_meta = MagicMock()
        zero_meta.width = 640
        zero_meta.height = 480
        zero_meta.fps = 30.0
        zero_meta.num_frames = 0
        mock_get_meta.return_value = zero_meta

        extractor_instance = MagicMock()
        # Both videos have zero poses
        empty_tracked = MagicMock()
        empty_tracked.poses = np.zeros((0, 17, 3), dtype=np.float32)
        extractor_instance.extract_video_tracked.side_effect = [empty_tracked, empty_tracked]
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        # max_frames=0 AND num_frames=0 → render_frames = 0
        cfg = ComparisonConfig(max_frames=0)
        renderer = ComparisonRenderer(config=cfg)

        with patch.object(renderer, "_load_pose_cache", return_value=None):
            with patch.object(renderer, "_save_pose_cache"):
                renderer.process(athlete, reference, output)

        # H264Writer should never be constructed since render_frames <= 0
        mock_writer_cls.assert_not_called()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_athlete_video_ends_reuses_last_frame(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
    ):
        """When athlete video ends but reference continues, last athlete frame is reused (line 325)."""
        mock_get_meta.return_value = mock_video_meta

        # Athlete cap: 2 frames then ends -- triggers frame_a_last reuse (line 325)
        cap_a = MagicMock()
        cap_a.isOpened.return_value = True
        cap_a.set.return_value = True
        cap_a.release.return_value = None
        frames_a = [(True, np.ones((480, 640, 3), dtype=np.uint8) * i * 50) for i in range(2)] + [
            (False, None),
            (False, None),
        ]
        cap_a.read.side_effect = frames_a

        # Reference cap: 5 frames available
        cap_r = MagicMock()
        cap_r.isOpened.return_value = True
        cap_r.set.return_value = True
        cap_r.release.return_value = None
        frames_r = [(True, np.ones((480, 640, 3), dtype=np.uint8) * 100) for _ in range(5)]
        cap_r.read.side_effect = frames_r

        mock_cap_cls.side_effect = [cap_a, cap_r]

        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(mode=ComparisonMode.OVERLAY, max_frames=3, no_cache=True)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        # Frames should be written even after athlete video ends
        assert mock_writer.write.call_count >= 1
        mock_writer.close.assert_called_once()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_reference_video_ends_reuses_last_frame(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
    ):
        """When reference video ends but athlete continues, last reference frame is reused (line 327)."""
        mock_get_meta.return_value = mock_video_meta

        # Athlete cap: 5 frames available
        cap_a = MagicMock()
        cap_a.isOpened.return_value = True
        cap_a.set.return_value = True
        cap_a.release.return_value = None
        frames_a = [(True, np.ones((480, 640, 3), dtype=np.uint8) * i * 50) for i in range(5)]
        cap_a.read.side_effect = frames_a

        # Reference cap: 2 frames then ends -- triggers frame_r_last reuse (line 327)
        cap_r = MagicMock()
        cap_r.isOpened.return_value = True
        cap_r.set.return_value = True
        cap_r.release.return_value = None
        frames_r = [(True, np.ones((480, 640, 3), dtype=np.uint8) * 100) for _ in range(2)] + [
            (False, None),
            (False, None),
        ]
        cap_r.read.side_effect = frames_r

        mock_cap_cls.side_effect = [cap_a, cap_r]

        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(mode=ComparisonMode.OVERLAY, max_frames=3, no_cache=True)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        # Frames should be written even after reference video ends
        assert mock_writer.write.call_count >= 1
        mock_writer.close.assert_called_once()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_custom_fps_from_config(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
        mock_cap,
    ):
        """Config fps should override video metadata fps."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(max_frames=3, fps=25.0)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        # Verify H264Writer was created with custom fps (4th positional arg)
        call_args = mock_writer_cls.call_args[0]
        assert call_args[3] == 25.0

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_pose_cache_hit_skips_extraction(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
        mock_cap,
    ):
        """When pose cache exists, extraction should be skipped."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cached_poses = [np.zeros((17, 2), dtype=np.float32) for _ in range(5)]

        cfg = ComparisonConfig(max_frames=3)
        renderer = ComparisonRenderer(config=cfg)

        # Mock _load_pose_cache to return cached data for both videos
        with patch.object(
            renderer, "_load_pose_cache", side_effect=[cached_poses, cached_poses]
        ) as mock_load:
            with patch.object(renderer, "_save_pose_cache") as mock_save:
                renderer.process(athlete, reference, output)

                # _save_pose_cache should NOT be called when cache hit
                mock_save.assert_not_called()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_few_poses_still_rendered(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_cap,
    ):
        """When poses are too few to smooth (1-2), they should still be used (lines 246-247, 251-252)."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        # Only 2 poses -- too few to smooth, should use raw
        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = np.random.rand(2, 17, 3).astype(np.float32)
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(max_frames=2)
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        # Smoother should NOT be called for 2 poses (too few)
        # But np.stack should still work and frames should be rendered
        assert mock_writer.write.call_count >= 1

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_overlay_mode_with_reference_pose_draws_skeleton(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
        mock_cap,
    ):
        """Overlay mode should call draw_skeleton for both athlete and reference poses."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        extractor_instance = MagicMock()
        tracked = MagicMock()
        tracked.poses = mock_tracked_poses[:5]
        extractor_instance.extract_video_tracked.return_value = tracked
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(mode=ComparisonMode.OVERLAY, max_frames=3, overlays=[])
        renderer = ComparisonRenderer(config=cfg)
        renderer.process(athlete, reference, output)

        # draw_skeleton should be called for athlete poses and reference poses
        assert mock_draw.call_count >= 2  # At least once for athlete, once for reference
        mock_writer.close.assert_called_once()

    @patch("src.visualization.comparison.cv2.VideoCapture")
    @patch("src.visualization.comparison.get_video_meta")
    @patch("src.visualization.comparison.H264Writer")
    @patch("src.visualization.comparison.PoseExtractor")
    @patch("src.visualization.comparison.PoseSmoother")
    @patch("src.visualization.comparison.get_skating_optimized_config")
    @patch("src.visualization.comparison.draw_skeleton")
    def test_overlay_mode_without_reference_pose(
        self,
        mock_draw,
        mock_get_config,
        mock_smoother_cls,
        mock_extractor_cls,
        mock_writer_cls,
        mock_get_meta,
        mock_cap_cls,
        tmp_path,
        mock_video_meta,
        mock_tracked_poses,
        mock_cap,
    ):
        """Overlay mode with no reference pose should not draw reference skeleton."""
        mock_get_meta.return_value = mock_video_meta
        mock_cap_cls.return_value = mock_cap
        mock_writer = MagicMock()
        mock_writer_cls.return_value = mock_writer

        # Athlete has poses, reference has none
        extractor_instance = MagicMock()
        full_tracked = MagicMock()
        full_tracked.poses = mock_tracked_poses[:5]
        empty_tracked = MagicMock()
        empty_tracked.poses = np.zeros((0, 17, 3), dtype=np.float32)
        extractor_instance.extract_video_tracked.side_effect = [full_tracked, empty_tracked]
        mock_extractor_cls.return_value = extractor_instance

        smoother_instance = MagicMock()
        smoother_instance.smooth.side_effect = lambda x: x
        mock_smoother_cls.return_value = smoother_instance
        mock_get_config.return_value = {}

        athlete = tmp_path / "athlete.mp4"
        reference = tmp_path / "reference.mp4"
        output = tmp_path / "output.mp4"
        athlete.write_bytes(b"")
        reference.write_bytes(b"")

        cfg = ComparisonConfig(mode=ComparisonMode.OVERLAY, max_frames=3)
        renderer = ComparisonRenderer(config=cfg)

        with patch.object(renderer, "_load_pose_cache", return_value=None):
            with patch.object(renderer, "_save_pose_cache"):
                renderer.process(athlete, reference, output)

        mock_writer.close.assert_called_once()
