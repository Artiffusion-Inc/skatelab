"""Tests for unified visualization pipeline (VizPipeline + prepare_poses)."""

import csv
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

from src.visualization.pipeline import PreparedPoses, VizPipeline, _resolve_model_3d, prepare_poses

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_meta(w: int = 640, h: int = 480, fps: float = 30.0, num_frames: int = 10):
    """Create a VideoMeta-like object for testing."""
    return SimpleNamespace(width=w, height=h, fps=fps, num_frames=num_frames)


@pytest.fixture
def meta():
    return _make_meta()


@pytest.fixture
def poses_norm():
    """5 frames of normalized [0,1] poses (N, 17, 2)."""
    return np.random.rand(5, 17, 2).astype(np.float32)


@pytest.fixture
def poses_px():
    """5 frames of pixel-coordinate poses (N, 17, 3)."""
    return np.random.rand(5, 17, 3).astype(np.float32) * np.array([640, 480, 1])


@pytest.fixture
def poses_3d():
    """5 frames of 3D poses (N, 17, 3)."""
    return np.random.rand(5, 17, 3).astype(np.float32)


@pytest.fixture
def blank_frame():
    """A blank BGR frame (480, 640, 3)."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


def _fake_extraction(n: int = 10):
    """Create a fake TrackedExtraction result."""
    extraction = mock.MagicMock()
    extraction.poses = np.random.rand(n, 17, 3).astype(np.float32)
    extraction.frame_indices = np.arange(n)
    extraction.valid_mask.return_value = np.ones(n, dtype=bool)
    return extraction


# ===========================================================================
# VizPipeline.__init__ and __post_init__
# ===========================================================================


class TestVizPipelineInit:
    def test_minimal_init_auto_poses_px(self, meta, poses_norm):
        """When poses_px is None, it is computed from poses_norm and meta dims."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        assert pipe.poses_px is not None
        assert pipe.poses_px.shape == (5, 17, 2)
        np.testing.assert_allclose(pipe.poses_px[:, :, 0], poses_norm[:, :, 0] * 640)
        np.testing.assert_allclose(pipe.poses_px[:, :, 1], poses_norm[:, :, 1] * 480)

    def test_minimal_init_auto_frame_indices(self, meta, poses_norm):
        """When frame_indices is None, it defaults to np.arange(N)."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        assert pipe.frame_indices is not None
        np.testing.assert_array_equal(pipe.frame_indices, np.arange(5))

    def test_explicit_poses_px_preserved(self, meta, poses_norm, poses_px):
        """Explicit poses_px is not overwritten."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px)
        # Should keep the 3-column shape from the fixture
        assert pipe.poses_px is not None
        assert pipe.poses_px.shape[2] == 3

    def test_explicit_frame_indices(self, meta, poses_norm):
        """Explicit frame_indices is preserved."""
        fi = np.array([0, 2, 4, 6, 8], dtype=np.intp)
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, frame_indices=fi)
        np.testing.assert_array_equal(pipe.frame_indices, fi)

    def test_layer_default_is_zero(self, meta, poses_norm):
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        assert pipe.layer == 0

    def test_poses_3d_stored(self, meta, poses_norm, poses_3d):
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_3d=poses_3d)
        assert pipe.poses_3d is poses_3d

    def test_confs_stored(self, meta, poses_norm):
        confs = np.random.rand(5, 17).astype(np.float32)
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, confs=confs)
        np.testing.assert_array_equal(pipe.confs, confs)

    def test_internal_state_empty_on_init(self, meta, poses_norm):
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        assert pipe.export_frames == []
        assert pipe.export_timestamps == []
        assert pipe.export_floor_angles == []
        assert pipe.export_joint_angles == []
        assert pipe.export_poses == []


# ===========================================================================
# VizPipeline.build_layers
# ===========================================================================


class TestVizPipelineBuildLayers:
    def test_layer_0_no_layers(self, meta, poses_norm):
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, layer=0)
        assert len(pipe.layers) == 0

    def test_layer_1_no_layers(self, meta, poses_norm):
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, layer=1)
        assert len(pipe.layers) == 0

    def test_layer_2_adds_vertical_axis(self, meta, poses_norm):
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, layer=2)
        assert len(pipe.layers) == 1

    def test_layer_3_adds_vertical_axis(self, meta, poses_norm):
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, layer=3)
        assert len(pipe.layers) == 1

    def test_rebuild_resets_layers(self, meta, poses_norm):
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, layer=2)
        assert len(pipe.layers) == 1
        pipe.layer = 0
        pipe.build_layers()
        assert len(pipe.layers) == 0

    def test_rebuild_promotes_layers(self, meta, poses_norm):
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, layer=0)
        assert len(pipe.layers) == 0
        pipe.layer = 2
        pipe.build_layers()
        assert len(pipe.layers) == 1


# ===========================================================================
# VizPipeline.add_ml_layers
# ===========================================================================


class TestVizPipelineAddMlLayers:
    def test_add_ml_layers_extends(self, meta, poses_norm):
        """add_ml_layers appends to existing layers list."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, layer=0)
        assert len(pipe.layers) == 0
        fake_layer = SimpleNamespace(name="ml_test")
        pipe.add_ml_layers([fake_layer])
        assert len(pipe.layers) == 1
        assert pipe.layers[0] is fake_layer

    def test_add_ml_layers_appends_not_replaces(self, meta, poses_norm):
        """add_ml_layers appends, not replaces, existing layers."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, layer=2)
        assert len(pipe.layers) == 1  # VerticalAxisLayer
        fake_layer = SimpleNamespace(name="ml_test")
        pipe.add_ml_layers([fake_layer])
        assert len(pipe.layers) == 2


# ===========================================================================
# VizPipeline.render_frame
# ===========================================================================


class TestVizPipelineRenderFrame:
    def test_no_pose_returns_context(self, meta, poses_norm, blank_frame):
        """render_frame with pose_idx=None returns unmodified context."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, layer=0)
        _frame_out, ctx = pipe.render_frame(blank_frame, frame_idx=0, pose_idx=None)
        assert ctx.pose_2d is None
        assert ctx.pose_3d is None

    def test_pose_idx_draws_skeleton(self, meta, poses_norm, poses_px, blank_frame):
        """render_frame with valid pose_idx calls draw_skeleton."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px, layer=0)
        with mock.patch(
            "src.visualization.pipeline.draw_skeleton", return_value=blank_frame
        ) as mock_draw:
            _frame_out, ctx = pipe.render_frame(blank_frame, frame_idx=0, pose_idx=0)
            mock_draw.assert_called_once()
        assert ctx.pose_2d is not None

    def test_pose_idx_out_of_range_no_skeleton(self, meta, poses_norm, poses_px, blank_frame):
        """render_frame with pose_idx >= len(poses_norm) does not draw skeleton."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px, layer=0)
        with mock.patch(
            "src.visualization.pipeline.draw_skeleton", return_value=blank_frame
        ) as mock_draw:
            _frame_out, ctx = pipe.render_frame(blank_frame, frame_idx=0, pose_idx=99)
            mock_draw.assert_not_called()
        assert ctx.pose_2d is None

    def test_poses_px_none_raises_value_error(self, meta, poses_norm, blank_frame):
        """render_frame raises ValueError if poses_px is None but pose_idx is valid.

        This is a defensive check: __post_init__ always sets poses_px, but
        if someone manually sets it to None, we catch it.
        """
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, layer=0)
        pipe.poses_px = None  # force the invalid state
        with pytest.raises(ValueError, match="poses_px is None"):
            pipe.render_frame(blank_frame, frame_idx=0, pose_idx=0)

    def test_pose_3d_set_in_context(self, meta, poses_norm, poses_px, poses_3d, blank_frame):
        """When poses_3d is provided and pose_idx valid, context.pose_3d is set."""
        pipe = VizPipeline(
            meta=meta,
            poses_norm=poses_norm,
            poses_px=poses_px,
            poses_3d=poses_3d,
            layer=0,
        )
        with mock.patch("src.visualization.pipeline.draw_skeleton", return_value=blank_frame):
            _, ctx = pipe.render_frame(blank_frame, frame_idx=0, pose_idx=0)
        assert ctx.pose_3d is not None
        np.testing.assert_array_equal(ctx.pose_3d, poses_3d[0])

    def test_pose_3d_out_of_range_not_set(self, meta, poses_norm, poses_px, blank_frame):
        """When poses_3d is shorter than pose_idx, context.pose_3d is not set."""
        short_3d = np.random.rand(1, 17, 3).astype(np.float32)
        pipe = VizPipeline(
            meta=meta,
            poses_norm=poses_norm,
            poses_px=poses_px,
            poses_3d=short_3d,
            layer=0,
        )
        with mock.patch("src.visualization.pipeline.draw_skeleton", return_value=blank_frame):
            _, ctx = pipe.render_frame(blank_frame, frame_idx=0, pose_idx=2)
        assert ctx.pose_3d is None

    def test_layer_1_calls_render_layers(self, meta, poses_norm, poses_px, blank_frame):
        """Layer >= 1 with valid pose_idx calls render_layers."""
        pipe = VizPipeline(
            meta=meta,
            poses_norm=poses_norm,
            poses_px=poses_px,
            layer=1,
        )
        with (
            mock.patch("src.visualization.pipeline.draw_skeleton", return_value=blank_frame),
            mock.patch(
                "src.visualization.pipeline.render_layers", return_value=blank_frame
            ) as mock_render,
        ):
            pipe.render_frame(blank_frame, frame_idx=0, pose_idx=0)
            mock_render.assert_called_once()

    def test_layer_0_no_render_layers(self, meta, poses_norm, poses_px, blank_frame):
        """Layer 0 does not call render_layers."""
        pipe = VizPipeline(
            meta=meta,
            poses_norm=poses_norm,
            poses_px=poses_px,
            layer=0,
        )
        with (
            mock.patch("src.visualization.pipeline.draw_skeleton", return_value=blank_frame),
            mock.patch(
                "src.visualization.pipeline.render_layers", return_value=blank_frame
            ) as mock_render,
        ):
            pipe.render_frame(blank_frame, frame_idx=0, pose_idx=0)
            mock_render.assert_not_called()

    def test_layer_1_no_pose_no_render_layers(self, meta, poses_norm, poses_px, blank_frame):
        """Layer >= 1 with pose_idx=None does not call render_layers."""
        pipe = VizPipeline(
            meta=meta,
            poses_norm=poses_norm,
            poses_px=poses_px,
            layer=1,
        )
        with mock.patch(
            "src.visualization.pipeline.render_layers", return_value=blank_frame
        ) as mock_render:
            pipe.render_frame(blank_frame, frame_idx=0, pose_idx=None)
            mock_render.assert_not_called()

    def test_context_metadata(self, meta, poses_norm, poses_px, blank_frame):
        """LayerContext is populated with correct video metadata."""
        pipe = VizPipeline(
            meta=meta,
            poses_norm=poses_norm,
            poses_px=poses_px,
            layer=0,
        )
        with mock.patch("src.visualization.pipeline.draw_skeleton", return_value=blank_frame):
            _, ctx = pipe.render_frame(blank_frame, frame_idx=3, pose_idx=0)
        assert ctx.frame_width == 640
        assert ctx.frame_height == 480
        assert ctx.fps == 30.0
        assert ctx.frame_idx == 3
        assert ctx.total_frames == 10
        assert ctx.normalized is True


# ===========================================================================
# VizPipeline.draw_frame_counter
# ===========================================================================


class TestVizPipelineDrawFrameCounter:
    def test_returns_frame(self, meta, poses_norm, blank_frame):
        """draw_frame_counter returns a frame array."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        result = pipe.draw_frame_counter(blank_frame, frame_idx=0)
        assert result is not None
        assert result.shape == blank_frame.shape

    def test_calls_draw_text_outlined(self, meta, poses_norm, blank_frame):
        """draw_frame_counter calls draw_text_outlined with correct position."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        with mock.patch("src.visualization.core.text.draw_text_outlined") as mock_text:
            pipe.draw_frame_counter(blank_frame, frame_idx=0)
            mock_text.assert_called_once()
            # Verify the y-position calculation: h - 40 - 25 = 480 - 65 = 415
            call_args = mock_text.call_args
            assert call_args[0][2] == (10, 415)

    def test_timestamp_calculation(self, meta, poses_norm, blank_frame):
        """Frame counter displays correct timestamp for known fps."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        # frame_idx=60, fps=30 → 2.0 seconds → 00:02.00
        with mock.patch("src.visualization.core.text.draw_text_outlined") as mock_text:
            pipe.draw_frame_counter(blank_frame, frame_idx=60)
            call_args = mock_text.call_args
            text = call_args[0][1]
            assert "60/10" in text  # frame 60 of 10 (odd but correct per meta)
            assert "00:02" in text

    def test_zero_frame_idx(self, meta, poses_norm, blank_frame):
        """Frame counter handles frame_idx=0 gracefully."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        with mock.patch("src.visualization.core.text.draw_text_outlined") as mock_text:
            pipe.draw_frame_counter(blank_frame, frame_idx=0)
            call_args = mock_text.call_args
            text = call_args[0][1]
            assert "0/10" in text
            assert "00:00" in text


# ===========================================================================
# VizPipeline.collect_export_data
# ===========================================================================


class TestVizPipelineCollectExportData:
    def test_pose_idx_none_early_return(self, meta, poses_norm):
        """collect_export_data with pose_idx=None does nothing."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        pipe.collect_export_data(frame_idx=0, pose_idx=None)
        assert pipe.export_frames == []
        assert pipe.export_timestamps == []
        assert pipe.export_floor_angles == []
        assert pipe.export_joint_angles == []
        assert pipe.export_poses == []

    def test_collects_frame_data(self, meta, poses_norm, poses_px):
        """collect_export_data appends frame index and timestamp."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px)
        with mock.patch("src.analysis.angles.compute_joint_angles", return_value={"R Knee": 90.0}):
            pipe.collect_export_data(frame_idx=30, pose_idx=0, floor_angle=15.5)
        assert pipe.export_frames == [30]
        assert pipe.export_timestamps == [1.0]  # 30 / 30.0 fps
        assert pipe.export_floor_angles == [15.5]

    def test_collects_joint_angles(self, meta, poses_norm, poses_px):
        """collect_export_data calls compute_joint_angles with correct pose."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px)
        fake_angles = {"R Knee": 90.0, "L Knee": 85.0}
        with mock.patch(
            "src.analysis.angles.compute_joint_angles", return_value=fake_angles
        ) as mock_ja:
            pipe.collect_export_data(frame_idx=0, pose_idx=2)
            mock_ja.assert_called_once()
            np.testing.assert_array_equal(mock_ja.call_args[0][0], poses_norm[2])
        assert pipe.export_joint_angles == [fake_angles]

    def test_collects_poses_px(self, meta, poses_norm, poses_px):
        """collect_export_data appends a copy of poses_px[pose_idx]."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px)
        with mock.patch("src.analysis.angles.compute_joint_angles", return_value={}):
            pipe.collect_export_data(frame_idx=0, pose_idx=1)
        assert len(pipe.export_poses) == 1
        np.testing.assert_array_equal(pipe.export_poses[0], poses_px[1])
        # Verify it's a copy, not a reference (poses_px[1] is (17, 3))
        pipe.export_poses[0][0, 0] = -999.0
        assert poses_px[1, 0, 0] != -999.0

    def test_default_floor_angle_is_zero(self, meta, poses_norm, poses_px):
        """collect_export_data defaults floor_angle to 0.0."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px)
        with mock.patch("src.analysis.angles.compute_joint_angles", return_value={}):
            pipe.collect_export_data(frame_idx=0, pose_idx=0)
        assert pipe.export_floor_angles == [0.0]

    def test_multiple_calls_accumulate(self, meta, poses_norm, poses_px):
        """Multiple collect_export_data calls accumulate data."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px)
        with mock.patch("src.analysis.angles.compute_joint_angles", return_value={}):
            for i in range(3):
                pipe.collect_export_data(frame_idx=i * 10, pose_idx=i)
        assert len(pipe.export_frames) == 3
        assert pipe.export_frames == [0, 10, 20]

    def test_no_poses_px_no_export_poses(self, meta, poses_norm):
        """When poses_px is None (unlikely after init), export_poses stays empty.

        After __post_init__, poses_px is never None. But for robustness,
        if someone forces it, we should not crash.
        """
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        pipe.poses_px = None  # force after init
        with mock.patch("src.analysis.angles.compute_joint_angles", return_value={}):
            pipe.collect_export_data(frame_idx=0, pose_idx=0)
        # poses_px is None, so no poses appended (but other data is)
        assert pipe.export_poses == []
        assert pipe.export_frames == [0]


# ===========================================================================
# VizPipeline.save_exports
# ===========================================================================


class TestVizPipelineSaveExports:
    def test_no_export_data_returns_none(self, meta, poses_norm):
        """save_exports with no collected data returns None paths."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        result = pipe.save_exports(Path("/tmp/test.mp4"))
        assert result["poses_path"] is None
        assert result["csv_path"] is None

    def test_saves_npy_file(self, meta, poses_norm, poses_px, tmp_path):
        """save_exports creates a .npy file with correct shape."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px)
        with mock.patch("src.analysis.angles.compute_joint_angles", return_value={}):
            pipe.collect_export_data(frame_idx=0, pose_idx=0)
            pipe.collect_export_data(frame_idx=1, pose_idx=1)

        out = tmp_path / "output.mp4"
        result = pipe.save_exports(out)

        assert result["poses_path"] is not None
        poses_path = Path(result["poses_path"])
        assert poses_path.exists()
        loaded = np.load(str(poses_path))
        assert loaded.shape[0] == 2

    def test_saves_csv_file(self, meta, poses_norm, poses_px, tmp_path):
        """save_exports creates a CSV with correct header and rows."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px)
        fake_angles = {"R Knee": 90.0, "L Knee": 85.0}
        with mock.patch("src.analysis.angles.compute_joint_angles", return_value=fake_angles):
            pipe.collect_export_data(frame_idx=0, pose_idx=0)
            pipe.collect_export_data(frame_idx=1, pose_idx=1)

        out = tmp_path / "output.mp4"
        result = pipe.save_exports(out)

        assert result["csv_path"] is not None
        csv_path = Path(result["csv_path"])
        assert csv_path.exists()

        with csv_path.open() as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header[0] == "frame"
            assert header[1] == "timestamp_s"
            assert header[2] == "floor_angle_deg"
            # Should have 12 angle keys after first 3 columns
            assert len(header) == 15

            rows = list(reader)
            assert len(rows) == 2
            assert rows[0][0] == "0"
            assert rows[1][0] == "1"

    def test_output_path_uses_parent_and_stem(self, meta, poses_norm, poses_px, tmp_path):
        """save_exports saves files alongside output_path using stem naming."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px)
        with mock.patch("src.analysis.angles.compute_joint_angles", return_value={}):
            pipe.collect_export_data(frame_idx=0, pose_idx=0)

        out = tmp_path / "my_video.mp4"
        result = pipe.save_exports(out)

        assert result["poses_path"] == str(tmp_path / "my_video_poses.npy")
        assert result["csv_path"] == str(tmp_path / "my_video_biomechanics.csv")

    def test_csv_missing_angle_keys_get_nan(self, meta, poses_norm, poses_px, tmp_path):
        """CSV rows fill NaN for angle keys not in compute_joint_angles output."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, poses_px=poses_px)
        partial_angles = {"R Knee": 90.0}  # only one key
        with mock.patch("src.analysis.angles.compute_joint_angles", return_value=partial_angles):
            pipe.collect_export_data(frame_idx=0, pose_idx=0)

        out = tmp_path / "test.mp4"
        result = pipe.save_exports(out)
        csv_path = Path(result["csv_path"])

        with csv_path.open() as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            row = next(reader)
            # "R Ankle" is the first angle key, should be nan since not in partial_angles
            assert row[3] == "nan"


# ===========================================================================
# VizPipeline.find_pose_idx
# ===========================================================================


class TestVizPipelineFindPoseIdx:
    def test_exact_match(self, meta, poses_norm):
        """find_pose_idx returns matching pose_idx when frame matches."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        current, next_idx = pipe.find_pose_idx(frame_idx=2, pose_idx=2)
        assert current == 2
        assert next_idx == 3

    def test_advance_pose_idx(self, meta, poses_norm):
        """find_pose_idx advances pose_idx past frames before target."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        current, next_idx = pipe.find_pose_idx(frame_idx=3, pose_idx=0)
        assert current == 3
        assert next_idx == 4

    def test_frame_ahead_returns_none(self, meta, poses_norm):
        """find_pose_idx returns (None, pose_idx) when target frame is ahead of all poses."""
        pipe = VizPipeline(
            meta=meta, poses_norm=poses_norm, frame_indices=np.array([0, 1, 2], dtype=np.intp)
        )
        current, next_idx = pipe.find_pose_idx(frame_idx=5, pose_idx=0)
        # pose_idx will advance to 3 (past all), then break since 5 > frame_indices[2]=2
        # Actually: 0<5 advance, 1<5 advance, 2<5 advance, pose_idx=3 >= len=3 → loop ends
        assert current is None
        assert next_idx == 3

    def test_no_match_returns_none(self, meta, poses_norm):
        """find_pose_idx returns (None, pose_idx) when frame_idx doesn't match any."""
        pipe = VizPipeline(
            meta=meta, poses_norm=poses_norm, frame_indices=np.array([0, 5, 10], dtype=np.intp)
        )
        current, next_idx = pipe.find_pose_idx(frame_idx=3, pose_idx=0)
        # 0 < 3 advance → pose_idx=1, 5 > 3 → break
        assert current is None
        assert next_idx == 1

    def test_frame_indices_none_raises(self, meta, poses_norm):
        """find_pose_idx raises ValueError if frame_indices is None."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        pipe.frame_indices = None
        with pytest.raises(ValueError, match="frame_indices is None"):
            pipe.find_pose_idx(frame_idx=0, pose_idx=0)

    def test_sparse_frame_indices(self, meta, poses_norm):
        """find_pose_idx works with sparse (non-contiguous) frame indices."""
        fi = np.array([0, 5, 10, 15, 20], dtype=np.intp)
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm, frame_indices=fi)
        current, next_idx = pipe.find_pose_idx(frame_idx=10, pose_idx=0)
        assert current == 2
        assert next_idx == 3

    def test_at_end_returns_none(self, meta, poses_norm):
        """find_pose_idx at end of frame_indices returns (None, N)."""
        pipe = VizPipeline(meta=meta, poses_norm=poses_norm)
        current, next_idx = pipe.find_pose_idx(frame_idx=100, pose_idx=0)
        assert current is None
        assert next_idx == 5  # len(poses_norm)


# ===========================================================================
# _resolve_model_3d
# ===========================================================================


class TestResolveModel3d:
    def test_explicit_path_existing(self, tmp_path):
        """Explicit path that exists is returned."""
        model = tmp_path / "model.onnx"
        model.touch()
        result = _resolve_model_3d(model)
        assert result == model

    def test_explicit_path_nonexistent(self, tmp_path):
        """Explicit path that doesn't exist returns None."""
        result = _resolve_model_3d(tmp_path / "nonexistent.onnx")
        assert result is None

    def test_none_returns_default_candidate_if_exists(self, tmp_path, monkeypatch):
        """When path=None, returns first existing default candidate."""
        from src.visualization import pipeline as pipe_mod

        fake_path = tmp_path / "motionagformer-s-ap3d.onnx"
        fake_path.touch()
        monkeypatch.setattr(pipe_mod, "_DEFAULT_MODEL_3D_CANDIDATES", [fake_path])
        result = _resolve_model_3d(None)
        assert result == fake_path

    def test_none_returns_none_when_no_candidates_exist(self, tmp_path, monkeypatch):
        """When path=None and no candidates exist, returns None."""
        from src.visualization import pipeline as pipe_mod

        monkeypatch.setattr(
            pipe_mod,
            "_DEFAULT_MODEL_3D_CANDIDATES",
            [tmp_path / "nope1.onnx", tmp_path / "nope2.onnx"],
        )
        result = _resolve_model_3d(None)
        assert result is None


# ===========================================================================
# prepare_poses
# ===========================================================================


class TestPreparePoses:
    def _patch_deps(self):
        """Return a dict of standard mock patches for prepare_poses dependencies."""
        return {
            "get_video_meta": mock.patch(
                "src.visualization.pipeline.get_video_meta", return_value=_make_meta()
            ),
            "PoseExtractor": mock.patch("src.visualization.pipeline.PoseExtractor"),
            "ONNXPoseExtractor": mock.patch("src.visualization.pipeline.ONNXPoseExtractor"),
            "resolve_model_3d": mock.patch(
                "src.visualization.pipeline._resolve_model_3d",
                return_value=Path("model.onnx"),
            ),
            "DeviceConfig": mock.patch("src.device.DeviceConfig"),
        }

    def test_returns_prepared_poses(self):
        """prepare_poses returns PreparedPoses with correct shapes."""
        with (
            mock.patch("src.visualization.pipeline.get_video_meta", return_value=_make_meta()),
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline.ONNXPoseExtractor") as MockOnnx,
            mock.patch(
                "src.visualization.pipeline._resolve_model_3d", return_value=Path("model.onnx")
            ),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = _fake_extraction()
            MockOnnx.return_value.estimate_3d.return_value = np.random.rand(10, 17, 3).astype(
                np.float32
            )

            result = prepare_poses(Path("test.mp4"))

        assert isinstance(result, PreparedPoses)
        assert result.poses_norm.shape == (10, 17, 2)
        assert result.poses_px.shape == (10, 17, 3)
        assert result.poses_3d is not None
        assert result.poses_3d.shape == (10, 17, 3)
        assert result.n_valid == 10
        assert result.n_total == 10

    def test_no_3d_when_model_missing(self):
        """When 3D model not found, poses_3d is None."""
        with (
            mock.patch("src.visualization.pipeline.get_video_meta", return_value=_make_meta()),
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline._resolve_model_3d", return_value=None),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = _fake_extraction()

            result = prepare_poses(Path("test.mp4"))

        assert result.poses_3d is None
        assert result.poses_norm.shape == (10, 17, 2)

    def test_gap_filling_with_nan(self):
        """NaN frames from frame_skip are linearly interpolated."""
        extraction = _fake_extraction(20)
        raw = np.full((20, 17, 3), np.nan, dtype=np.float32)
        for i in [0, 4, 8, 12, 16]:
            raw[i] = np.random.rand(17, 3).astype(np.float32)
        extraction.poses = raw

        with (
            mock.patch(
                "src.visualization.pipeline.get_video_meta", return_value=_make_meta(num_frames=20)
            ),
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline.ONNXPoseExtractor") as MockOnnx,
            mock.patch(
                "src.visualization.pipeline._resolve_model_3d", return_value=Path("model.onnx")
            ),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = extraction
            MockOnnx.return_value.estimate_3d.return_value = np.random.rand(20, 17, 3).astype(
                np.float32
            )

            result = prepare_poses(Path("test.mp4"), frame_skip=4)

        assert not np.isnan(result.poses_norm).any()
        assert result.n_valid == 5

    def test_no_gap_filling_when_all_valid(self):
        """No interpolation needed when all frames are valid."""
        extraction = _fake_extraction(5)  # all valid

        with (
            mock.patch(
                "src.visualization.pipeline.get_video_meta", return_value=_make_meta(num_frames=5)
            ),
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline._resolve_model_3d", return_value=None),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = extraction

            result = prepare_poses(Path("test.mp4"))

        assert result.n_valid == 5

    def test_progress_cb_called(self):
        """prepare_poses calls progress_cb at expected stages."""
        extraction = _fake_extraction(5)
        progress_calls = []

        def cb(progress, msg):
            progress_calls.append((progress, msg))

        with (
            mock.patch("src.visualization.pipeline.get_video_meta", return_value=_make_meta()),
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline.ONNXPoseExtractor") as MockOnnx,
            mock.patch(
                "src.visualization.pipeline._resolve_model_3d", return_value=Path("model.onnx")
            ),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = extraction
            MockOnnx.return_value.estimate_3d.return_value = np.random.rand(5, 17, 3).astype(
                np.float32
            )

            result = prepare_poses(Path("test.mp4"), progress_cb=cb)

        # Check progress callbacks were made at expected stages
        messages = [msg for _, msg in progress_calls]
        assert "Extracting poses..." in messages
        assert "3D pose estimation..." in messages
        assert "Poses ready." in messages

    def test_progress_cb_without_3d(self):
        """prepare_poses calls progress_cb correctly when no 3D model."""
        extraction = _fake_extraction(5)
        progress_calls = []

        def cb(progress, msg):
            progress_calls.append((progress, msg))

        with (
            mock.patch("src.visualization.pipeline.get_video_meta", return_value=_make_meta()),
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline._resolve_model_3d", return_value=None),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = extraction

            result = prepare_poses(Path("test.mp4"), progress_cb=cb)

        messages = [msg for _, msg in progress_calls]
        assert "Extracting poses..." in messages
        assert "Poses ready." in messages

    def test_poses_px_built_from_final_poses_norm(self):
        """poses_px is built from final (possibly interpolated) poses_norm."""
        extraction = _fake_extraction(5)

        with (
            mock.patch("src.visualization.pipeline.get_video_meta", return_value=_make_meta()),
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline._resolve_model_3d", return_value=None),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = extraction

            result = prepare_poses(Path("test.mp4"))

        # poses_px x = poses_norm x * width, y = poses_norm y * height
        np.testing.assert_allclose(
            result.poses_px[:, :, 0],
            result.poses_norm[:, :, 0] * 640,
            rtol=1e-5,
        )
        np.testing.assert_allclose(
            result.poses_px[:, :, 1],
            result.poses_norm[:, :, 1] * 480,
            rtol=1e-5,
        )

    def test_person_click_forwarded(self):
        """person_click is forwarded to PoseExtractor.extract_video_tracked."""
        from src.types import PersonClick

        extraction = _fake_extraction(5)
        click = PersonClick(x=100, y=200)

        with (
            mock.patch("src.visualization.pipeline.get_video_meta", return_value=_make_meta()),
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline._resolve_model_3d", return_value=None),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = extraction

            prepare_poses(Path("test.mp4"), person_click=click)

        # Verify person_click was passed
        call_kwargs = MockExt.return_value.extract_video_tracked.call_args
        assert (
            call_kwargs.kwargs.get("person_click") is click
            or call_kwargs[1].get("person_click") is click
        )

    def test_video_path_converted_to_path(self):
        """String video_path is converted to Path."""
        extraction = _fake_extraction(5)

        with (
            mock.patch(
                "src.visualization.pipeline.get_video_meta", return_value=_make_meta()
            ) as mock_meta,
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline._resolve_model_3d", return_value=None),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = extraction

            prepare_poses("test.mp4")

        # get_video_meta should have been called with a Path
        called_arg = mock_meta.call_args[0][0]
        assert isinstance(called_arg, Path)

    def test_pose_extractor_params(self):
        """PoseExtractor is constructed with correct parameters."""
        extraction = _fake_extraction(5)

        with (
            mock.patch("src.visualization.pipeline.get_video_meta", return_value=_make_meta()),
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline._resolve_model_3d", return_value=None),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = extraction

            prepare_poses(Path("test.mp4"), frame_skip=2, tracking="deepsort")

        # Verify PoseExtractor was called with expected params
        call_kwargs = MockExt.call_args
        assert (
            call_kwargs.kwargs.get("output_format") == "normalized"
            or call_kwargs[1].get("output_format") == "normalized"
        )
        assert call_kwargs.kwargs.get("frame_skip") == 2 or call_kwargs[1].get("frame_skip") == 2
        assert (
            call_kwargs.kwargs.get("tracking_mode") == "deepsort"
            or call_kwargs[1].get("tracking_mode") == "deepsort"
        )

    def test_no_interpolation_with_single_valid_frame(self):
        """Gap filling skipped when only 1 valid frame (needs >= 2 for interp)."""
        extraction = _fake_extraction(5)
        raw = np.full((5, 17, 3), np.nan, dtype=np.float32)
        raw[2] = np.random.rand(17, 3).astype(np.float32)  # only 1 valid
        extraction.poses = raw

        with (
            mock.patch("src.visualization.pipeline.get_video_meta", return_value=_make_meta()),
            mock.patch("src.visualization.pipeline.PoseExtractor") as MockExt,
            mock.patch("src.visualization.pipeline._resolve_model_3d", return_value=None),
            mock.patch("src.device.DeviceConfig") as MockDevCfg,
        ):
            MockDevCfg.return_value.device = "cuda"
            MockExt.return_value.extract_video_tracked.return_value = extraction

            result = prepare_poses(Path("test.mp4"))

        # Only 1 valid frame → interpolation skipped → NaN stays
        assert result.n_valid == 1
        # Most poses_norm frames will still have NaN (only frame 2 valid)
        assert np.isnan(result.poses_norm).any()


# ===========================================================================
# Integration: full render + export cycle
# ===========================================================================


class TestVizPipelineIntegration:
    def test_render_all_frames(self):
        """Render 5 frames with poses, verify no crash and export data collected."""
        meta = _make_meta(num_frames=5)
        poses = np.random.rand(5, 17, 2).astype(np.float32)
        pipe = VizPipeline(meta=meta, poses_norm=poses, layer=0)

        pose_idx = 0
        for frame_idx in range(5):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            current, pose_idx = pipe.find_pose_idx(frame_idx, pose_idx)
            frame, _ = pipe.render_frame(frame, frame_idx, current)
            pipe.collect_export_data(frame_idx, current)

        assert len(pipe.export_frames) == 5

    def test_save_exports_after_full_cycle(self, tmp_path):
        """Full render + collect + save creates both output files."""
        meta = _make_meta(num_frames=3)
        poses = np.random.rand(3, 17, 2).astype(np.float32)
        pipe = VizPipeline(meta=meta, poses_norm=poses, layer=0)

        with mock.patch("src.analysis.angles.compute_joint_angles", return_value={"R Knee": 90.0}):
            for i in range(3):
                pipe.collect_export_data(i, i)

        out = tmp_path / "integration.mp4"
        result = pipe.save_exports(out)

        assert result["poses_path"] is not None
        assert result["csv_path"] is not None
        assert Path(result["poses_path"]).exists()
        assert Path(result["csv_path"]).exists()

    def test_mixed_valid_and_missing_poses(self):
        """Pipeline handles frames where some have poses and some don't."""
        meta = _make_meta(num_frames=10)
        poses = np.random.rand(3, 17, 2).astype(np.float32)
        pipe = VizPipeline(
            meta=meta,
            poses_norm=poses,
            layer=1,
            frame_indices=np.array([0, 4, 7], dtype=np.intp),
        )

        pose_idx = 0
        export_count = 0
        for frame_idx in range(10):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            current, pose_idx = pipe.find_pose_idx(frame_idx, pose_idx)
            frame, _ = pipe.render_frame(frame, frame_idx, current)
            if current is not None:
                export_count += 1

        assert export_count == 3
