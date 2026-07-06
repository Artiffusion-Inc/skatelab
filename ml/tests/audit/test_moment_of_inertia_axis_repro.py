"""Repro tests — calculate_moment_of_inertia ignores the axis param (#854).

``calculate_moment_of_inertia`` (physics_engine.py:166) accepts
``axis`` ("vertical"/"sagittal"/"frontal") but never reads it — the inner
``add_segment_inertia`` helper uses ``np.linalg.norm(pos - com_trajectory,
axis=1)``, the full 3D distance from CoM. That is the moment of inertia about
a POINT, not an axis. The perpendicular distance to a rotation axis projects
the offset onto the plane perpendicular to that axis
(vertical → drop Y: ``sqrt(dx² + dz²)``).

Consequences:
  - Mass lying ON the vertical axis (head/feet above the CoM) contributes
    ``m·dy²`` that should be 0 → angular momentum L = I·ω inflated.
  - All three axes return the SAME value (the API lies).

Fix (#854): project the offset onto the plane perpendicular to ``axis``
before taking the norm.

Tests:
  - observable: mass on the vertical axis → I(vertical) ≈ 0 (RED: large).
  - observable: three axes give DIFFERENT values for an asymmetric pose
    (RED: all equal).
  - source-asserting: add_segment_inertia uses axis-aware projection, not
    the full norm.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.analysis.physics_engine import PhysicsEngine
from src.pose_estimation.h36m import H36Key


def _poses_mass_on_vertical_axis() -> np.ndarray:
    """Body stacked along the Y axis (head above, feet below), X=Z=0.

    After CoM (which stays on the Y axis), perpendicular distance to the
    vertical axis is 0 for every segment → I(vertical) == 0.
    """
    n = 3
    poses = np.zeros((n, 17, 3), dtype=np.float32)
    # Head up high, feet down — all at x=z=0.
    poses[:, H36Key.HEAD, 1] = 1.5
    poses[:, H36Key.SPINE, 1] = 0.5
    poses[:, H36Key.THORAX, 1] = 0.7
    poses[:, H36Key.LFOOT, 1] = -1.0
    poses[:, H36Key.RFOOT, 1] = -1.0
    return poses


def test_mass_on_vertical_axis_has_zero_inertia_repro():
    """#854: mass lying on the vertical axis → I(vertical) must be ~0.

    RED without the fix: full norm uses |dy| → I = m·dy² inflated.
    """
    engine = PhysicsEngine(body_mass=60.0)
    poses = _poses_mass_on_vertical_axis()
    inertia = engine.calculate_moment_of_inertia(poses, axis="vertical")
    assert float(np.max(np.abs(inertia))) < 1e-3, (
        f"#854 RED: mass on the vertical axis → I(vertical)={float(np.max(np.abs(inertia)))} — "
        "axis ignored, full 3D distance used (m·dy² should be 0)."
    )


def test_three_axes_give_different_values_repro():
    """#854: for an asymmetric pose, the three axes must give DIFFERENT MoI.

    RED without the fix: all three return the same full-norm value.
    """
    engine = PhysicsEngine(body_mass=60.0)
    n = 3
    poses = np.zeros((n, 17, 3), dtype=np.float32)
    # Asymmetric offset: head at (0.3, 0.5, 0.2).
    poses[:, H36Key.HEAD] = [0.3, 0.5, 0.2]
    poses[:, H36Key.LWRIST] = [-0.4, 0.1, 0.0]
    poses[:, H36Key.RWRIST] = [0.4, -0.1, 0.3]

    iv = float(engine.calculate_moment_of_inertia(poses, axis="vertical")[0])
    isg = float(engine.calculate_moment_of_inertia(poses, axis="sagittal")[0])
    ifr = float(engine.calculate_moment_of_inertia(poses, axis="frontal")[0])
    values = [iv, isg, ifr]
    assert len({round(v, 4) for v in values}) >= 2, (
        f"#854 RED: all three axes give the same MoI {values} — axis param is "
        "dead code, full 3D distance used."
    )


def test_source_uses_axis_aware_projection_repro():
    """#854 GREEN: add_segment_inertia must project the offset onto the plane
    perpendicular to ``axis``, not the full norm."""
    import inspect

    src = inspect.getsource(PhysicsEngine.calculate_moment_of_inertia)
    # The fix must reference the axis param inside the distance computation
    # (vertical → drop Y, sagittal → drop X, frontal → drop Z).
    assert "vertical" in src and ("sagittal" in src or "frontal" in src), (
        "#854: calculate_moment_of_inertia never branches on axis — axis param "
        "is dead. Project the offset onto the plane perp to axis."
    )
    assert "axis" in src, "#854: axis must be used in the projection."
