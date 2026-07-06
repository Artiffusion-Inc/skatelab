"""#797 repro: velocity_layer pose_2d=None frame leaves stale _prev_pose_3d."""

import inspect

import numpy as np

from src.visualization.layers.base import LayerContext
from src.visualization.layers.velocity_layer import VelocityLayer


def _make_layer() -> VelocityLayer:
    layer = VelocityLayer()
    # Seed a prior 3D pose so the reset is observable (None → not-None).
    layer._prev_pose_3d = np.ones((17, 3), dtype=np.float32) * 0.5
    layer._prev_pose_2d = np.ones((17, 2), dtype=np.float32) * 0.5
    return layer


def test_velocity_prev_pose_3d_cleared_when_pose_2d_none():
    """#797: pose_2d=None branch must reset BOTH _prev_pose_2d and
    _prev_pose_3d. The unconditional line 123 overwrote the 3D reset when
    pose_3d was set (3D lift succeeded, 2D detection failed), so a stale 3D
    pose survived the occlusion frame → spurious velocity arrow next frame.
    """
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    layer = _make_layer()

    ctx = LayerContext(
        frame_width=640,
        frame_height=480,
        fps=25.0,
        pose_2d=None,
        pose_3d=np.ones((17, 3), dtype=np.float32) * 0.5,
        normalized=True,
    )
    layer.render(frame, ctx)

    assert layer._prev_pose_2d is None, "pose_2d=None reset _prev_pose_2d"
    assert layer._prev_pose_3d is None, (
        "#797: pose_2d=None must reset _prev_pose_3d too — line 123 overwrote it"
    )


def test_velocity_prev_pose_2d_cleared_when_pose_2d_none():
    """Contrast: 2D reset works (elif line 121). 3D must match (asymmetry was the bug)."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    layer = _make_layer()

    ctx = LayerContext(
        frame_width=640,
        frame_height=480,
        fps=25.0,
        pose_2d=None,
        pose_3d=None,
        normalized=True,
    )
    layer.render(frame, ctx)

    assert layer._prev_pose_2d is None
    assert layer._prev_pose_3d is None


def test_velocity_no_unconditional_prev_pose_3d_overwrite():
    """Source contract: the unconditional `self._prev_pose_3d = ...` line
    (the pasted-twice bug) must be gone — render sets _prev_pose_3d only
    inside the if/elif branches, never unconditionally after.
    """
    src = inspect.getsource(VelocityLayer.render)
    # Count only real assignments (not comment lines mentioning the symbol).
    assigns = [
        ln.strip()
        for ln in src.splitlines()
        if "self._prev_pose_3d =" in ln and not ln.strip().startswith("#")
    ]
    assert len(assigns) == 2, (
        f"expected 2 _prev_pose_3d assignments in render (if + elif), got {len(assigns)}: {assigns}"
    )
    # The two must be inside branches (indented under if/elif), not a bare line.
    for a in assigns:
        assert a.startswith("self._prev_pose_3d ="), a
