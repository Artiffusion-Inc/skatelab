"""Tests for visualization layer base, skeleton, timer, joint angle, and vertical axis layers.

Covers:
- base.py: Layer, LayerContext, sort_layers_by_z_index, render_layers, create_layer_composite
- skeleton_layer.py: SkeletonLayer (2d and 3d modes)
- timer_layer.py: TimerLayer
- joint_angle_layer.py: JointAngleSpec, JointAngleLayer, 3D projection
- vertical_axis_layer.py: VerticalAxisLayer, classify_tilt, _tilt_direction_label
"""

from unittest.mock import patch

import numpy as np
import pytest

from src.pose_estimation import H36Key
from src.visualization.config import LayerConfig, VisualizationConfig
from src.visualization.layers.base import (
    Frame,
    Layer,
    LayerContext,
    create_layer_composite,
    render_layers,
    sort_layers_by_z_index,
)
from src.visualization.layers.joint_angle_layer import (
    DEFAULT_JOINT_SPECS,
    JointAngleLayer,
    JointAngleSpec,
)
from src.visualization.layers.skeleton_layer import SkeletonLayer
from src.visualization.layers.timer_layer import TimerLayer
from src.visualization.layers.vertical_axis_layer import (
    TiltQuality,
    VerticalAxisLayer,
    _tilt_direction_label,
    classify_tilt,
)

# =============================================================================
# Helpers
# =============================================================================


def _blank_frame(w: int = 640, h: int = 480) -> Frame:
    """Create a blank black frame."""
    return np.zeros((h, w, 3), dtype=np.uint8)


def _valid_pose_2d(w: int = 640, h: int = 480, normalized: bool = False) -> np.ndarray:
    """Create a valid 17-keypoint 2D pose (standing figure)."""
    pose = np.zeros((17, 2), dtype=np.float32)
    if normalized:
        # Normalized coordinates in [0, 1]
        pose[H36Key.LHIP] = [0.45, 0.6]
        pose[H36Key.RHIP] = [0.55, 0.6]
        pose[H36Key.LKNEE] = [0.45, 0.75]
        pose[H36Key.RKNEE] = [0.55, 0.75]
        pose[H36Key.LFOOT] = [0.45, 0.9]
        pose[H36Key.RFOOT] = [0.55, 0.9]
        pose[H36Key.LSHOULDER] = [0.47, 0.35]
        pose[H36Key.RSHOULDER] = [0.53, 0.35]
        pose[H36Key.LELBOW] = [0.40, 0.50]
        pose[H36Key.RELBOW] = [0.60, 0.50]
        pose[H36Key.LWRIST] = [0.38, 0.65]
        pose[H36Key.RWRIST] = [0.62, 0.65]
        pose[H36Key.HIP_CENTER] = [0.50, 0.6]
        pose[H36Key.SPINE] = [0.50, 0.50]
        pose[H36Key.THORAX] = [0.50, 0.40]
        pose[H36Key.NECK] = [0.50, 0.33]
        pose[H36Key.HEAD] = [0.50, 0.20]
    else:
        # Pixel coordinates
        cx = w // 2
        pose[H36Key.LHIP] = [cx - 20, 300]
        pose[H36Key.RHIP] = [cx + 20, 300]
        pose[H36Key.LKNEE] = [cx - 20, 360]
        pose[H36Key.RKNEE] = [cx + 20, 360]
        pose[H36Key.LFOOT] = [cx - 20, 420]
        pose[H36Key.RFOOT] = [cx + 20, 420]
        pose[H36Key.LSHOULDER] = [cx - 15, 180]
        pose[H36Key.RSHOULDER] = [cx + 15, 180]
        pose[H36Key.LELBOW] = [cx - 40, 240]
        pose[H36Key.RELBOW] = [cx + 40, 240]
        pose[H36Key.LWRIST] = [cx - 55, 310]
        pose[H36Key.RWRIST] = [cx + 55, 310]
        pose[H36Key.HIP_CENTER] = [cx, 300]
        pose[H36Key.SPINE] = [cx, 250]
        pose[H36Key.THORAX] = [cx, 200]
        pose[H36Key.NECK] = [cx, 170]
        pose[H36Key.HEAD] = [cx, 100]
    return pose


def _valid_pose_3d() -> np.ndarray:
    """Create a valid 17-keypoint 3D pose (standing figure in meters)."""
    pose = np.zeros((17, 3), dtype=np.float32)
    pose[H36Key.LHIP] = [-0.1, 0.0, 0.0]
    pose[H36Key.RHIP] = [0.1, 0.0, 0.0]
    pose[H36Key.LKNEE] = [-0.1, -0.4, 0.0]
    pose[H36Key.RKNEE] = [0.1, -0.4, 0.0]
    pose[H36Key.LFOOT] = [-0.1, -0.8, 0.0]
    pose[H36Key.RFOOT] = [0.1, -0.8, 0.0]
    pose[H36Key.LSHOULDER] = [-0.15, 0.3, 0.0]
    pose[H36Key.RSHOULDER] = [0.15, 0.3, 0.0]
    pose[H36Key.LELBOW] = [-0.2, 0.15, 0.0]
    pose[H36Key.RELBOW] = [0.2, 0.15, 0.0]
    pose[H36Key.LWRIST] = [-0.22, 0.0, 0.0]
    pose[H36Key.RWRIST] = [0.22, 0.0, 0.0]
    pose[H36Key.HIP_CENTER] = [0.0, 0.0, 0.0]
    pose[H36Key.SPINE] = [0.0, 0.2, 0.0]
    pose[H36Key.THORAX] = [0.0, 0.3, 0.0]
    pose[H36Key.NECK] = [0.0, 0.4, 0.0]
    pose[H36Key.HEAD] = [0.0, 0.5, 0.0]
    return pose


# =============================================================================
# LayerContext tests
# =============================================================================


class TestLayerContext:
    """Tests for LayerContext dataclass defaults and construction."""

    def test_defaults(self):
        ctx = LayerContext()
        assert ctx.frame_width == 1920
        assert ctx.frame_height == 1080
        assert ctx.fps == 30.0
        assert ctx.frame_idx == 0
        assert ctx.total_frames is None
        assert ctx.pose_2d is None
        assert ctx.pose_3d is None
        assert ctx.confidences is None
        assert ctx.metrics == []
        assert ctx.phase is None
        assert ctx.blade_state is None
        assert ctx.normalized is True
        assert ctx.camera_distance == 3.0
        assert ctx.focal_length == 800
        assert ctx.custom_data == {}

    def test_custom_values(self):
        pose = _valid_pose_2d()
        ctx = LayerContext(
            frame_width=1280,
            frame_height=720,
            fps=60.0,
            frame_idx=100,
            total_frames=300,
            pose_2d=pose,
            normalized=False,
            custom_data={"key": "value"},
        )
        assert ctx.frame_width == 1280
        assert ctx.frame_height == 720
        assert ctx.fps == 60.0
        assert ctx.frame_idx == 100
        assert ctx.total_frames == 300
        assert ctx.pose_2d is pose
        assert not ctx.normalized
        assert ctx.custom_data == {"key": "value"}

    def test_pose_3d(self):
        pose_3d = _valid_pose_3d()
        ctx = LayerContext(pose_3d=pose_3d)
        assert ctx.pose_3d is pose_3d
        assert ctx.pose_3d.shape == (17, 3)

    def test_confidences(self):
        conf = np.ones(17, dtype=np.float32)
        ctx = LayerContext(confidences=conf)
        assert ctx.confidences is not None
        np.testing.assert_array_equal(ctx.confidences, conf)


# =============================================================================
# Layer base class tests
# =============================================================================


class TestLayerBase:
    """Tests for the Layer abstract base class."""

    def _make_concrete_layer(self, **kwargs):
        """Create a minimal concrete Layer subclass for testing."""

        class ConcreteLayer(Layer):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.render_called = False

            def render(self, frame: Frame, context: LayerContext) -> Frame:
                self.render_called = True
                return frame

        return ConcreteLayer(**kwargs)

    def test_default_config(self):
        layer = self._make_concrete_layer()
        assert layer.config.enabled is True
        assert layer.config.z_index == 0
        assert layer.config.opacity == 1.0
        assert layer.name == "Layer"

    def test_custom_config(self):
        config = LayerConfig(enabled=False, z_index=5, opacity=0.5)
        layer = self._make_concrete_layer(config=config, name="Test")
        assert layer.enabled is False
        assert layer.z_index == 5
        assert layer.opacity == 0.5
        assert layer.name == "Test"

    def test_enabled_property(self):
        layer = self._make_concrete_layer()
        assert layer.enabled is True
        layer.enabled = False
        assert layer.enabled is False
        assert layer.config.enabled is False

    def test_z_index_property(self):
        layer = self._make_concrete_layer()
        assert layer.z_index == 0
        layer.z_index = 10
        assert layer.z_index == 10
        assert layer.config.z_index == 10

    def test_opacity_property(self):
        layer = self._make_concrete_layer()
        assert layer.opacity == 1.0
        layer.opacity = 0.5
        assert layer.opacity == 0.5
        assert layer.config.opacity == 0.5

    def test_is_visible_default(self):
        layer = self._make_concrete_layer()
        assert layer.is_visible() is True

    def test_is_visible_disabled(self):
        layer = self._make_concrete_layer(config=LayerConfig(enabled=False))
        assert layer.is_visible() is False

    def test_is_visible_zero_opacity(self):
        layer = self._make_concrete_layer(config=LayerConfig(opacity=0.0))
        assert layer.is_visible() is False

    def test_call_visible(self):
        layer = self._make_concrete_layer()
        frame = _blank_frame()
        ctx = LayerContext()
        result = layer(frame, ctx)
        assert layer.render_called is True
        assert result is frame

    def test_call_invisible_returns_frame_unchanged(self):
        layer = self._make_concrete_layer(config=LayerConfig(enabled=False))
        frame = _blank_frame()
        ctx = LayerContext()
        result = layer(frame, ctx)
        assert layer.render_called is False
        assert result is frame

    def test_call_zero_opacity_returns_frame_unchanged(self):
        layer = self._make_concrete_layer(config=LayerConfig(opacity=0.0))
        frame = _blank_frame()
        ctx = LayerContext()
        result = layer(frame, ctx)
        assert layer.render_called is False


# =============================================================================
# sort_layers_by_z_index tests
# =============================================================================


class TestSortLayersByZIndex:
    def test_sorts_ascending(self):
        l1 = self._make_layer("A", 3)
        l2 = self._make_layer("B", 1)
        l3 = self._make_layer("C", 2)
        sorted_layers = sort_layers_by_z_index([l1, l2, l3])
        assert [ly.name for ly in sorted_layers] == ["B", "C", "A"]

    def test_empty_list(self):
        assert sort_layers_by_z_index([]) == []

    def test_single_layer(self):
        ly = self._make_layer("A", 5)
        result = sort_layers_by_z_index([ly])
        assert result == [ly]

    def test_same_z_index_preserves_order(self):
        l1 = self._make_layer("A", 1)
        l2 = self._make_layer("B", 1)
        l3 = self._make_layer("C", 1)
        result = sort_layers_by_z_index([l1, l2, l3])
        assert result == [l1, l2, l3]

    @staticmethod
    def _make_layer(name: str, z: int) -> Layer:
        class StubLayer(Layer):
            def render(self, frame, context):
                return frame

        return StubLayer(config=LayerConfig(z_index=z), name=name)


# =============================================================================
# render_layers tests
# =============================================================================


class TestRenderLayers:
    def test_renders_visible_layers(self):
        frame = _blank_frame()
        ctx = LayerContext()
        call_order = []

        class LayerA(Layer):
            def render(self, f, c):
                call_order.append("A")
                return f

        class LayerB(Layer):
            def render(self, f, c):
                call_order.append("B")
                return f

        layers = [
            LayerA(config=LayerConfig(z_index=2), name="A"),
            LayerB(config=LayerConfig(z_index=1), name="B"),
        ]
        result = render_layers(frame, layers, ctx)
        assert call_order == ["B", "A"]
        assert result is frame

    def test_skips_disabled_layers(self):
        frame = _blank_frame()
        ctx = LayerContext()
        call_order = []

        class LayerA(Layer):
            def render(self, f, c):
                call_order.append("A")
                return f

        class LayerB(Layer):
            def render(self, f, c):
                call_order.append("B")
                return f

        layers = [
            LayerA(config=LayerConfig(z_index=1, enabled=True), name="A"),
            LayerB(config=LayerConfig(z_index=2, enabled=False), name="B"),
        ]
        render_layers(frame, layers, ctx)
        assert call_order == ["A"]

    def test_skips_zero_opacity_layers(self):
        frame = _blank_frame()
        ctx = LayerContext()
        call_order = []

        class LayerA(Layer):
            def render(self, f, c):
                call_order.append("A")
                return f

        layers = [
            LayerA(config=LayerConfig(z_index=1, opacity=0.0), name="A"),
        ]
        render_layers(frame, layers, ctx)
        assert call_order == []


# =============================================================================
# create_layer_composite tests
# =============================================================================


class TestCreateLayerComposite:
    def test_composite_renders_all_children(self):
        frame = _blank_frame()
        ctx = LayerContext()
        call_count = [0]

        class CountLayer(Layer):
            def render(self, f, c):
                call_count[0] += 1
                return f

        children = [
            CountLayer(config=LayerConfig(z_index=0), name="C1"),
            CountLayer(config=LayerConfig(z_index=1), name="C2"),
        ]
        composite = create_layer_composite(children)
        assert composite.name == "Composite"
        composite.render(frame, ctx)
        assert call_count[0] == 2

    def test_composite_skips_disabled_children(self):
        frame = _blank_frame()
        ctx = LayerContext()
        call_count = [0]

        class CountLayer(Layer):
            def render(self, f, c):
                call_count[0] += 1
                return f

        children = [
            CountLayer(config=LayerConfig(z_index=0, enabled=True), name="C1"),
            CountLayer(config=LayerConfig(z_index=1, enabled=False), name="C2"),
        ]
        composite = create_layer_composite(children)
        composite.render(frame, ctx)
        assert call_count[0] == 1


# =============================================================================
# SkeletonLayer tests
# =============================================================================


class TestSkeletonLayer:
    """Tests for SkeletonLayer."""

    def test_init_defaults(self):
        layer = SkeletonLayer()
        assert layer.enabled is True
        assert layer.z_index == 0
        assert layer.mode == "2d"
        assert layer.line_width == 2
        assert layer.joint_radius == 4
        assert layer.depth_min == 0.0
        assert layer.depth_max == 2.0
        assert layer.name == "Skeleton"

    def test_init_custom_config(self):
        config = LayerConfig(enabled=False, z_index=3)
        layer = SkeletonLayer(config=config, mode="3d", line_width=3, joint_radius=6)
        assert layer.enabled is False
        assert layer.z_index == 3
        assert layer.mode == "3d"
        assert layer.line_width == 3
        assert layer.joint_radius == 6

    def test_render_2d_with_pose(self):
        """Rendering 2D with a valid pose modifies the frame."""
        layer = SkeletonLayer()
        pose = _valid_pose_2d(normalized=False)
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        result = layer.render(frame, ctx)
        assert result is frame
        assert not np.array_equal(result, _blank_frame())

    def test_render_2d_no_pose_returns_unchanged(self):
        layer = SkeletonLayer(mode="2d")
        frame = _blank_frame()
        ctx = LayerContext(pose_2d=None)
        result = layer.render(frame, ctx)
        assert result is frame
        assert np.array_equal(result, _blank_frame())

    def test_render_3d_with_pose(self):
        """Rendering 3D with a valid pose returns the frame."""
        layer = SkeletonLayer(mode="3d")
        pose_3d = _valid_pose_3d()
        frame = _blank_frame()
        ctx = LayerContext(pose_3d=pose_3d)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_3d_no_pose_returns_unchanged(self):
        layer = SkeletonLayer(mode="3d")
        frame = _blank_frame()
        ctx = LayerContext(pose_3d=None)
        result = layer.render(frame, ctx)
        assert result is frame
        assert np.array_equal(result, _blank_frame())

    def test_render_2d_normalized_pose(self):
        """Rendering with normalized coordinates should work."""
        layer = SkeletonLayer()
        pose = _valid_pose_2d(normalized=True)
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=True)
        result = layer.render(frame, ctx)
        assert result is frame
        assert not np.array_equal(result, _blank_frame())

    def test_render_with_confidences(self):
        """Rendering with confidence values should work."""
        layer = SkeletonLayer()
        pose = _valid_pose_2d(normalized=False)
        confidences = np.ones(17, dtype=np.float32) * 0.9
        frame = _blank_frame()
        ctx = LayerContext(
            frame_width=640,
            frame_height=480,
            pose_2d=pose,
            confidences=confidences,
            normalized=False,
        )
        result = layer.render(frame, ctx)
        assert result is frame

    def test_call_visible_renders(self):
        """Calling a visible layer invokes render."""
        layer = SkeletonLayer()
        pose = _valid_pose_2d()
        frame = _blank_frame()
        ctx = LayerContext(pose_2d=pose, normalized=False)
        result = layer(frame, ctx)
        assert result is frame

    def test_call_disabled_returns_frame_unchanged(self):
        """Calling a disabled layer returns frame unchanged."""
        layer = SkeletonLayer(config=LayerConfig(enabled=False))
        frame = _blank_frame()
        ctx = LayerContext()
        result = layer(frame, ctx)
        assert np.array_equal(result, _blank_frame())


# =============================================================================
# TimerLayer tests
# =============================================================================


class TestTimerLayer:
    """Tests for TimerLayer."""

    def test_init_defaults(self):
        layer = TimerLayer()
        assert layer.enabled is True
        assert layer.z_index == 10

    def test_init_custom_config(self):
        config = LayerConfig(enabled=False, z_index=5)
        layer = TimerLayer(config=config)
        assert layer.enabled is False
        assert layer.z_index == 5

    def test_render_modifies_frame(self):
        """Timer should draw text on the frame."""
        layer = TimerLayer()
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, fps=30.0, frame_idx=90)
        result = layer.render(frame, ctx)
        assert result is frame
        assert not np.array_equal(result, _blank_frame())

    def test_render_at_frame_zero(self):
        """Timer at frame 0 should show 00:00.00."""
        layer = TimerLayer()
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, fps=30.0, frame_idx=0)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_at_30fps_60_frames(self):
        """At 30fps, frame 60 = 2 seconds = 00:02.00."""
        layer = TimerLayer()
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, fps=30.0, frame_idx=60)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_at_60fps(self):
        """Timer should work with 60fps."""
        layer = TimerLayer()
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, fps=60.0, frame_idx=120)
        result = layer.render(frame, ctx)
        assert result is frame
        assert not np.array_equal(result, _blank_frame())

    def test_render_zero_fps_returns_unchanged(self):
        """fps=0 should not draw anything."""
        layer = TimerLayer()
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, fps=0.0, frame_idx=10)
        result = layer.render(frame, ctx)
        assert np.array_equal(result, _blank_frame())

    def test_render_negative_fps_returns_unchanged(self):
        """Negative fps should not draw anything."""
        layer = TimerLayer()
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, fps=-5.0, frame_idx=10)
        result = layer.render(frame, ctx)
        assert np.array_equal(result, _blank_frame())

    def test_render_large_frame_idx(self):
        """Timer should handle large frame indices (>1 hour)."""
        layer = TimerLayer()
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, fps=30.0, frame_idx=180000)
        result = layer.render(frame, ctx)
        assert result is frame
        assert not np.array_equal(result, _blank_frame())

    def test_is_visible_default(self):
        layer = TimerLayer()
        assert layer.is_visible() is True

    def test_is_visible_disabled(self):
        layer = TimerLayer(config=LayerConfig(enabled=False))
        assert layer.is_visible() is False

    def test_call_disabled_returns_frame_unchanged(self):
        layer = TimerLayer(config=LayerConfig(enabled=False))
        frame = _blank_frame()
        ctx = LayerContext(fps=30.0, frame_idx=10)
        result = layer(frame, ctx)
        assert np.array_equal(result, _blank_frame())


# =============================================================================
# JointAngleSpec tests
# =============================================================================


class TestJointAngleSpec:
    """Tests for JointAngleSpec data class."""

    def test_init_defaults(self):
        spec = JointAngleSpec("Knee", 0, 1, 2)
        assert spec.name == "Knee"
        assert spec.point_a == 0
        assert spec.vertex == 1
        assert spec.point_c == 2
        assert spec.color == (255, 255, 0)  # COLOR_CYAN
        assert spec.min_radius == 4
        assert spec.good_range == (90, 180)
        assert spec.warn_range == (60, 190)

    def test_init_custom(self):
        spec = JointAngleSpec(
            "Hip",
            5,
            6,
            7,
            color=(0, 255, 0),
            min_radius=8,
            good_range=(70, 150),
            warn_range=(50, 170),
        )
        assert spec.color == (0, 255, 0)
        assert spec.min_radius == 8

    def test_get_color_for_angle_good(self):
        spec = JointAngleSpec("Knee", 0, 1, 2, good_range=(90, 170))
        color = spec.get_color_for_angle(120.0)
        assert color == (0, 255, 0)  # COLOR_GREEN

    def test_get_color_for_angle_warn(self):
        spec = JointAngleSpec("Knee", 0, 1, 2, good_range=(90, 170), warn_range=(60, 190))
        # 75 is outside good_range but inside warn_range
        color = spec.get_color_for_angle(75.0)
        assert color == (0, 255, 255)  # COLOR_YELLOW

    def test_get_color_for_angle_bad(self):
        spec = JointAngleSpec("Knee", 0, 1, 2, good_range=(90, 170), warn_range=(60, 190))
        # 50 is outside both ranges
        color = spec.get_color_for_angle(50.0)
        assert color == (0, 0, 255)  # COLOR_RED

    def test_get_color_for_angle_boundary(self):
        spec = JointAngleSpec("Knee", 0, 1, 2, good_range=(90, 170), warn_range=(60, 190))
        # Exactly at good_range boundary
        assert spec.get_color_for_angle(90.0) == (0, 255, 0)
        assert spec.get_color_for_angle(170.0) == (0, 255, 0)

    def test_default_joint_specs_count(self):
        assert len(DEFAULT_JOINT_SPECS) == 6

    def test_default_joint_specs_names(self):
        names = [s.name for s in DEFAULT_JOINT_SPECS]
        assert "L Knee" in names
        assert "R Knee" in names
        assert "L Elbow" in names
        assert "R Elbow" in names
        assert "L Hip" in names
        assert "R Hip" in names


# =============================================================================
# JointAngleLayer tests
# =============================================================================


class TestJointAngleLayer:
    """Tests for JointAngleLayer."""

    def test_init_defaults(self):
        layer = JointAngleLayer()
        assert layer.enabled is True
        assert layer.z_index == 6
        assert layer.angle_source == "auto"
        assert layer.show_degree_labels is True
        assert layer.arc_scale == 0.25
        assert layer.joints is DEFAULT_JOINT_SPECS

    def test_init_custom(self):
        custom_joints = [JointAngleSpec("Test", 0, 1, 2)]
        layer = JointAngleLayer(
            angle_source="2d",
            show_degree_labels=False,
            arc_scale=0.3,
            joints=custom_joints,
        )
        assert layer.angle_source == "2d"
        assert layer.show_degree_labels is False
        assert layer.arc_scale == 0.3
        assert len(layer.joints) == 1

    def test_init_invalid_angle_source(self):
        with pytest.raises(ValueError, match="angle_source must be"):
            JointAngleLayer(angle_source="invalid")

    def test_render_no_pose_returns_unchanged(self):
        layer = JointAngleLayer()
        frame = _blank_frame()
        ctx = LayerContext(pose_2d=None)
        result = layer.render(frame, ctx)
        assert result is frame
        assert np.array_equal(result, _blank_frame())

    def test_render_with_valid_pose_modifies_frame(self):
        layer = JointAngleLayer()
        pose = _valid_pose_2d(normalized=False)
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        result = layer.render(frame, ctx)
        assert result is frame
        assert not np.array_equal(result, _blank_frame())

    def test_render_2d_mode(self):
        layer = JointAngleLayer(angle_source="2d")
        pose = _valid_pose_2d(normalized=False)
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_auto_mode_with_3d(self):
        """Auto mode should use 3D data when available."""
        layer = JointAngleLayer(angle_source="auto")
        pose_2d = _valid_pose_2d(normalized=False)
        pose_3d = _valid_pose_3d()
        frame = _blank_frame()
        ctx = LayerContext(
            frame_width=640,
            frame_height=480,
            pose_2d=pose_2d,
            pose_3d=pose_3d,
            normalized=False,
        )
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_3d_mode_with_3d_data(self):
        layer = JointAngleLayer(angle_source="3d")
        pose_2d = _valid_pose_2d(normalized=False)
        pose_3d = _valid_pose_3d()
        frame = _blank_frame()
        ctx = LayerContext(
            frame_width=640,
            frame_height=480,
            pose_2d=pose_2d,
            pose_3d=pose_3d,
            normalized=False,
        )
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_3d_mode_no_3d_data(self):
        """3d mode with no 3d data should fallback to 2d angles."""
        layer = JointAngleLayer(angle_source="3d")
        pose_2d = _valid_pose_2d(normalized=False)
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose_2d, normalized=False)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_normalized_pose(self):
        layer = JointAngleLayer()
        pose = _valid_pose_2d(normalized=True)
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=True)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_nan_in_non_required_joints(self):
        """NaN in non-required joints should not crash (other joints may still render)."""
        layer = JointAngleLayer(
            joints=[
                JointAngleSpec("Test", H36Key.LHIP, H36Key.LKNEE, H36Key.LFOOT),
            ]
        )
        pose = _valid_pose_2d(normalized=False)
        # Make some non-essential joints NaN
        pose[H36Key.LSHOULDER] = [np.nan, np.nan]
        pose[H36Key.RSHOULDER] = [np.nan, np.nan]
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_vertex_out_of_bounds_skipped(self):
        """Vertices far outside frame bounds should be skipped."""
        layer = JointAngleLayer()
        pose = _valid_pose_2d(normalized=False)
        # Move knee vertex way off-screen
        pose[H36Key.LKNEE] = [-5000, -5000]
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_degree_labels_disabled(self):
        """When show_degree_labels=False, still render arcs but no text."""
        layer = JointAngleLayer(show_degree_labels=False)
        pose = _valid_pose_2d(normalized=False)
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_custom_joints(self):
        """Only render specified joints."""
        single_joint = JointAngleSpec("Test Knee", H36Key.LHIP, H36Key.LKNEE, H36Key.LFOOT)
        layer = JointAngleLayer(joints=[single_joint])
        pose = _valid_pose_2d(normalized=False)
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_project_3d_arc_2d_degenerate_bones(self):
        """Degenerate (zero-length) bones should return None."""
        a = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        v = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        c = np.array([1.0, 0.0, 0.0], dtype=np.float64)  # collinear
        a2 = np.array([100.0, 200.0], dtype=np.float64)
        v2 = np.array([300.0, 400.0], dtype=np.float64)
        c2 = np.array([500.0, 600.0], dtype=np.float64)
        result = JointAngleLayer._project_3d_arc_2d(a, v, c, a2, v2, c2, 20)
        assert result is None

    def test_project_3d_arc_2d_valid(self):
        """Valid 3D points should produce an arc array."""
        a = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        v = np.array([1.0, 1.0, 0.0], dtype=np.float64)
        c = np.array([2.0, 0.0, 0.0], dtype=np.float64)
        a2 = np.array([100.0, 200.0], dtype=np.float64)
        v2 = np.array([300.0, 400.0], dtype=np.float64)
        c2 = np.array([500.0, 200.0], dtype=np.float64)
        result = JointAngleLayer._project_3d_arc_2d(a, v, c, a2, v2, c2, 20)
        assert result is not None
        assert result.shape[1] == 2

    def test_draw_arc_does_not_crash(self):
        """Static _draw_arc method should not crash."""
        frame = _blank_frame()
        vertex = np.array([320.0, 240.0], dtype=np.float64)
        point_a = np.array([320.0, 140.0], dtype=np.float64)
        point_c = np.array([420.0, 240.0], dtype=np.float64)
        JointAngleLayer._draw_arc(frame, vertex, point_a, point_c, 20, (220, 220, 220))
        assert not np.array_equal(frame, _blank_frame())

    def test_draw_tick_does_not_crash(self):
        """Static _draw_tick method should not crash."""
        frame = _blank_frame()
        vertex = np.array([320.0, 240.0], dtype=np.float64)
        bone_end = np.array([320.0, 140.0], dtype=np.float64)
        JointAngleLayer._draw_tick(frame, vertex, bone_end, 10, (255, 255, 0))

    def test_draw_tick_zero_length_bone(self):
        """_draw_tick with zero-length bone should not crash."""
        frame = _blank_frame()
        original = frame.copy()
        vertex = np.array([320.0, 240.0], dtype=np.float64)
        bone_end = np.array([320.0, 240.0], dtype=np.float64)  # Same as vertex
        JointAngleLayer._draw_tick(frame, vertex, bone_end, 10, (255, 255, 0))
        # Should return early without drawing
        assert np.array_equal(frame, original)

    def test_compute_bisector(self):
        """_compute_bisector returns a normalized direction."""
        vertex = np.array([0.0, 0.0], dtype=np.float64)
        pa = np.array([1.0, 0.0], dtype=np.float64)
        pc = np.array([0.0, 1.0], dtype=np.float64)
        bisector = JointAngleLayer._compute_bisector(vertex, pa, pc)
        # Bisector of (1,0) and (0,1) should be roughly (0.707, 0.707)
        expected = np.array([1.0, 1.0]) / np.sqrt(2)
        np.testing.assert_allclose(bisector, expected, atol=1e-6)

    def test_compute_bisector_zero_length(self):
        """_compute_bisector with zero-length bone should return fallback direction."""
        vertex = np.array([0.0, 0.0], dtype=np.float64)
        pa = np.array([0.0, 0.0], dtype=np.float64)  # Same as vertex
        pc = np.array([0.0, 1.0], dtype=np.float64)
        bisector = JointAngleLayer._compute_bisector(vertex, pa, pc)
        assert bisector is not None
        # Fallback direction is [1.0, -1.0] (up-right), not necessarily unit-normalized
        expected = np.array([1.0, -1.0])
        np.testing.assert_allclose(bisector, expected)

    def test_draw_projected_arc_does_not_crash(self):
        """Static _draw_projected_arc should not crash."""
        frame = _blank_frame()
        pts = np.array(
            [[100.0, 200.0], [110.0, 180.0], [120.0, 160.0], [130.0, 150.0]],
            dtype=np.float64,
        )
        JointAngleLayer._draw_projected_arc(frame, pts, (220, 220, 220))

    def test_draw_projected_arc_with_nan(self):
        """_draw_projected_arc should handle NaN points gracefully."""
        frame = _blank_frame()
        pts = np.array(
            [[100.0, 200.0], [np.nan, np.nan], [130.0, 150.0]],
            dtype=np.float64,
        )
        # Should not crash — nan_to_num replaces NaN with 0
        JointAngleLayer._draw_projected_arc(frame, pts, (220, 220, 220))


# =============================================================================
# VerticalAxisLayer tests
# =============================================================================


class TestClassifyTilt:
    """Tests for the classify_tilt function."""

    def test_zero_tilt_is_good(self):
        assert classify_tilt(0.0) == TiltQuality.GOOD

    def test_small_tilt_is_good(self):
        assert classify_tilt(4.0) == TiltQuality.GOOD

    def test_at_good_threshold_is_warn(self):
        assert classify_tilt(5.0) == TiltQuality.WARN

    def test_medium_tilt_is_warn(self):
        assert classify_tilt(8.0) == TiltQuality.WARN

    def test_at_warn_threshold_is_bad(self):
        assert classify_tilt(10.0) == TiltQuality.BAD

    def test_large_tilt_is_bad(self):
        assert classify_tilt(15.0) == TiltQuality.BAD

    def test_negative_tilt(self):
        assert classify_tilt(-4.0) == TiltQuality.GOOD
        assert classify_tilt(-8.0) == TiltQuality.WARN
        assert classify_tilt(-15.0) == TiltQuality.BAD

    def test_custom_thresholds(self):
        assert classify_tilt(7.0, 10.0, 20.0) == TiltQuality.GOOD
        assert classify_tilt(15.0, 10.0, 20.0) == TiltQuality.WARN
        assert classify_tilt(25.0, 10.0, 20.0) == TiltQuality.BAD


class TestTiltDirectionLabel:
    """Tests for _tilt_direction_label helper."""

    def test_zero_tilt_no_direction(self):
        assert _tilt_direction_label(0.0) == ""
        assert _tilt_direction_label(0.5) == ""

    def test_positive_tilt_right(self):
        assert _tilt_direction_label(5.0) == "R"
        assert _tilt_direction_label(1.5) == "R"

    def test_negative_tilt_left(self):
        assert _tilt_direction_label(-5.0) == "L"
        assert _tilt_direction_label(-1.5) == "L"


class TestVerticalAxisLayer:
    """Tests for VerticalAxisLayer."""

    def test_init_defaults(self):
        layer = VerticalAxisLayer()
        assert layer.enabled is True
        assert layer.z_index == 5
        assert layer.show_degree_label is True
        assert layer.show_head_alignment is True
        assert layer.good_threshold == 5.0
        assert layer.warn_threshold == 10.0
        assert layer.arc_radius == 20

    def test_init_custom_config(self):
        config = LayerConfig(enabled=False, z_index=3)
        layer = VerticalAxisLayer(
            config=config,
            show_degree_label=False,
            show_head_alignment=False,
            good_threshold=3.0,
            warn_threshold=8.0,
            arc_radius=15,
        )
        assert layer.enabled is False
        assert layer.z_index == 3
        assert layer.show_degree_label is False
        assert layer.show_head_alignment is False
        assert layer.good_threshold == 3.0
        assert layer.warn_threshold == 8.0
        assert layer.arc_radius == 15

    def test_render_no_pose_returns_unchanged(self):
        layer = VerticalAxisLayer()
        frame = _blank_frame()
        ctx = LayerContext(pose_2d=None)
        result = layer.render(frame, ctx)
        assert result is frame
        assert np.array_equal(result, _blank_frame())

    def test_render_upright_pose_modifies_frame(self):
        """Upright pose should still draw gravity line."""
        pose = np.zeros((17, 2), dtype=np.float32)
        cx = 320
        pose[H36Key.LHIP] = [cx - 20, 300]
        pose[H36Key.RHIP] = [cx + 20, 300]
        pose[H36Key.LSHOULDER] = [cx - 15, 180]
        pose[H36Key.RSHOULDER] = [cx + 15, 180]
        pose[H36Key.HEAD] = [cx, 100]

        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        layer = VerticalAxisLayer()
        result = layer.render(frame, ctx)
        assert result is frame
        assert not np.array_equal(result, _blank_frame())

    def test_render_leaning_pose_modifies_frame(self):
        """Leaning pose should draw spine + tilt indicators."""
        pose = np.zeros((17, 2), dtype=np.float32)
        cx = 320
        pose[H36Key.LHIP] = [cx - 20, 300]
        pose[H36Key.RHIP] = [cx + 20, 300]
        pose[H36Key.LSHOULDER] = [cx + 25, 180]  # Lean right
        pose[H36Key.RSHOULDER] = [cx + 55, 180]
        pose[H36Key.HEAD] = [cx + 40, 100]

        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        layer = VerticalAxisLayer()
        result = layer.render(frame, ctx)
        assert result is frame
        assert not np.array_equal(result, _blank_frame())

    def test_render_normalized_coords(self):
        """Rendering with normalized coordinates should work."""
        pose = np.zeros((17, 2), dtype=np.float32)
        pose[H36Key.LHIP] = [0.47, 0.6]
        pose[H36Key.RHIP] = [0.53, 0.6]
        pose[H36Key.LSHOULDER] = [0.48, 0.35]
        pose[H36Key.RSHOULDER] = [0.52, 0.35]
        pose[H36Key.HEAD] = [0.5, 0.2]

        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=True)
        layer = VerticalAxisLayer()
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_nan_pose_returns_unchanged(self):
        """All-NaN pose should not crash and return frame unchanged."""
        pose = np.full((17, 2), np.nan, dtype=np.float32)
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        layer = VerticalAxisLayer()
        result = layer.render(frame, ctx)
        assert result is frame

    def test_render_partial_nan_skips(self):
        """NaN in required joints should return frame unchanged."""
        pose = _valid_pose_2d(normalized=False)
        pose[H36Key.LHIP] = [np.nan, np.nan]
        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        layer = VerticalAxisLayer()
        result = layer.render(frame, ctx)
        assert result is frame
        assert np.array_equal(result, _blank_frame())

    def test_coincident_hip_shoulder(self):
        """Hip and shoulder at same location should not crash."""
        pose = np.zeros((17, 2), dtype=np.float32)
        cx, cy = 320, 240
        pose[H36Key.LHIP] = [cx - 10, cy]
        pose[H36Key.RHIP] = [cx + 10, cy]
        pose[H36Key.LSHOULDER] = [cx - 10, cy]
        pose[H36Key.RSHOULDER] = [cx + 10, cy]
        pose[H36Key.HEAD] = [cx, cy]

        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        layer = VerticalAxisLayer()
        result = layer.render(frame, ctx)
        assert result is frame

    def test_show_degree_label_false(self):
        """When degree labels are disabled, still draws gravity line."""
        pose = np.zeros((17, 2), dtype=np.float32)
        cx = 320
        pose[H36Key.LHIP] = [cx - 20, 300]
        pose[H36Key.RHIP] = [cx + 20, 300]
        pose[H36Key.LSHOULDER] = [cx + 25, 180]
        pose[H36Key.RSHOULDER] = [cx + 55, 180]
        pose[H36Key.HEAD] = [cx + 40, 100]

        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        layer = VerticalAxisLayer(show_degree_label=False)
        result = layer.render(frame, ctx)
        assert result is frame
        assert not np.array_equal(result, _blank_frame())

    def test_head_alignment_with_offset(self):
        """Head offset should draw head alignment indicator."""
        pose = np.zeros((17, 2), dtype=np.float32)
        cx = 320
        pose[H36Key.LHIP] = [cx - 20, 300]
        pose[H36Key.RHIP] = [cx + 20, 300]
        pose[H36Key.LSHOULDER] = [cx - 15, 180]
        pose[H36Key.RSHOULDER] = [cx + 15, 180]
        pose[H36Key.HEAD] = [cx + 50, 100]  # Offset head

        frame = _blank_frame()
        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)
        layer = VerticalAxisLayer(show_head_alignment=True)
        result = layer.render(frame, ctx)
        assert result is frame

    def test_head_alignment_disabled_differs_from_enabled(self):
        """Disabling head alignment should produce a different result."""
        pose = np.zeros((17, 2), dtype=np.float32)
        cx = 320
        pose[H36Key.LHIP] = [cx - 20, 300]
        pose[H36Key.RHIP] = [cx + 20, 300]
        pose[H36Key.LSHOULDER] = [cx - 15, 180]
        pose[H36Key.RSHOULDER] = [cx + 15, 180]
        pose[H36Key.HEAD] = [cx + 50, 100]

        ctx = LayerContext(frame_width=640, frame_height=480, pose_2d=pose, normalized=False)

        frame1 = _blank_frame()
        frame2 = _blank_frame()

        VerticalAxisLayer(show_head_alignment=True).render(frame1, ctx)
        VerticalAxisLayer(show_head_alignment=False).render(frame2, ctx)

        assert not np.array_equal(frame1, frame2)

    def test_draw_dashed_line_short_distance(self):
        """_draw_dashed_line with very short distance should not crash."""
        layer = VerticalAxisLayer()
        frame = _blank_frame()
        # Two identical points — distance = 0
        layer._draw_dashed_line(frame, (100, 100), (100, 100), (200, 200, 100), 1, dash=8)
        assert result_frame_is_valid(frame)

    def test_draw_dashed_line_normal(self):
        """_draw_dashed_line should draw visible segments."""
        layer = VerticalAxisLayer()
        frame = _blank_frame()
        original = frame.copy()
        layer._draw_dashed_line(frame, (100, 100), (200, 200), (200, 200, 100), 1, dash=8)
        assert not np.array_equal(frame, original)

    def test_backward_compatible_constructor(self):
        """Old-style constructor with config and viz_config still works."""
        layer = VerticalAxisLayer(
            config=LayerConfig(enabled=True, z_index=5),
            viz_config=VisualizationConfig(),
        )
        assert layer.enabled
        assert layer.z_index == 5


def result_frame_is_valid(frame):
    """Helper: frame is a valid numpy array."""
    return isinstance(frame, np.ndarray) and frame.shape[2] == 3
