"""NaN joint guard for `JointAngleLayer.render` (#1091, tranche GY).

Regression test: a NaN joint point (vertex / point_a / point_c) on the 2D
path must NOT crash `render` (pixel coords) and must NOT draw a garbage arc
(normalized coords). The guard lives on the RAW pose, before
`normalized_to_pixel` masks NaN to (0,0).

Original issue body referenced line numbers from pre-#894 code; the
correctness contract is the same. The fix (#894) lives in
`JointAngleLayer.render` lines 216-221. This file pins the contract.
"""

import inspect

import numpy as np

from src.types import H36Key
from src.visualization.layers.base import LayerContext
from src.visualization.layers.joint_angle_layer import JointAngleLayer, JointAngleSpec


def _spec() -> JointAngleSpec:
    """R-knee angle spec: vertex=RKNEE, point_a=RHIP, point_c=RFOOT."""
    return JointAngleSpec(
        name="rknee",
        point_a=H36Key.RHIP,
        vertex=H36Key.RKNEE,
        point_c=H36Key.RFOOT,
    )


def _valid_pose() -> np.ndarray:
    pose = np.zeros((17, 2), dtype=np.float32)
    pose[H36Key.RHIP] = [250.0, 300.0]
    pose[H36Key.RKNEE] = [260.0, 360.0]
    pose[H36Key.RFOOT] = [270.0, 420.0]
    return pose


def _nan_point_pose(point: int) -> np.ndarray:
    """Pose with ONLY `point` NaN (rest valid) — partial occlusion."""
    pose = _valid_pose()
    pose[point] = [np.nan, np.nan]
    return pose


def test_nan_vertex_pixel_render_does_not_crash():
    """NaN vertex (RKNEE) on the 2D path (pixel) must not raise."""
    w, h = 640, 480
    layer = JointAngleLayer(joints=[_spec()])
    ctx = LayerContext(
        frame_width=w,
        frame_height=h,
        normalized=False,
        pose_2d=_nan_point_pose(H36Key.RKNEE),
    )
    out = layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx)
    assert out is not None
    assert out.shape == (h, w, 3)


def test_nan_point_a_pixel_render_does_not_crash():
    """NaN point_a (RHIP) on the 2D path (pixel) must not raise."""
    w, h = 640, 480
    layer = JointAngleLayer(joints=[_spec()])
    ctx = LayerContext(
        frame_width=w,
        frame_height=h,
        normalized=False,
        pose_2d=_nan_point_pose(H36Key.RHIP),
    )
    out = layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx)
    assert out is not None
    assert out.shape == (h, w, 3)


def test_nan_point_c_pixel_render_does_not_crash():
    """NaN point_c (RFOOT) on the 2D path (pixel) must not raise."""
    w, h = 640, 480
    layer = JointAngleLayer(joints=[_spec()])
    ctx = LayerContext(
        frame_width=w,
        frame_height=h,
        normalized=False,
        pose_2d=_nan_point_pose(H36Key.RFOOT),
    )
    out = layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx)
    assert out is not None
    assert out.shape == (h, w, 3)


def test_all_valid_pose_still_renders():
    """Regression: an all-valid pose must still render an angle arc (no over-skip)."""
    w, h = 640, 480
    layer = JointAngleLayer(joints=[_spec()])
    ctx = LayerContext(
        frame_width=w,
        frame_height=h,
        normalized=False,
        pose_2d=_valid_pose(),
    )
    out = layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx)
    assert out is not None
    # Frame should not be entirely black (something was drawn).
    assert out.sum() > 0


def test_nan_guard_uses_isfinite_check_on_raw_pose():
    """Source check: the 2D-path guard is `np.isfinite` on the RAW pose
    (pre-`normalized_to_pixel`). Mirrors the 3D path guard. Locks the fix
    so a future refactor cannot regress by guarding post-conversion
    (where `normalized_to_pixel` masks NaN -> (0,0))."""
    src = inspect.getsource(JointAngleLayer.render)
    # The 2D-path raw-pose NaN guard must be present.
    assert (
        "np.isnan(pose[spec.point_a]).any()" in src
        and "np.isnan(pose[spec.vertex]).any()" in src
        and "np.isnan(pose[spec.point_c]).any()" in src
    ), (
        "JointAngleLayer.render must guard the 2D path on the RAW pose "
        "(np.isnan(pose[spec.point_a]).any() or ...). The post-conversion "
        "guard is dead for the normalized path (normalized_to_pixel masks "
        "NaN -> (0,0))."
    )
    # The NaN-angle secondary guard is still present (defence-in-depth for
    # the pixel path where angle_3pt's #863 wrapper returns NaN).
    assert "if np.isnan(angle) or angle < 0 or angle > 360:" in src
