"""Repro tests — analyze_2d jump_height uses full CoM Y range, not takeoff→peak (#855).

``analyze_2d`` (physics_engine.py:539) computes jump height as the full CoM Y
excursion over the flight window:

``jump_height = np.max(flight_com_y) - np.min(flight_com_y)``

"Jump height" is how high the CoM rises ABOVE takeoff (``takeoff_y − peak_y``
in Y-down image coords), not the peak-to-trough range. When the landing drops
the CoM BELOW takeoff (knee bend on impact — the normal, praised landing
posture), ``max`` lands on the landing frame, not takeoff:

    buggy = landing_y − peak_y = landing_drop + real_height > real_height

A deeper knee-bend landing reports a TALLER jump than the same physical jump
landed stiff.

Fix (#855): ``jump_height = com[takeoff_idx, 1] - np.min(flight_com_y)`` — peak
elevation relative to takeoff. Invariant to landing absorption depth.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.analysis.physics_engine import PhysicsEngine


def _pose_with_com_y(com_y_per_frame: list[float]) -> np.ndarray:
    """Build a (N, 17, 2) pose whose 2D CoM trajectory matches com_y_per_frame.

    ``calculate_com_trajectory_2d`` is a weighted sum of joint y-coords; we
    put the same y on every joint so the CoM y == that y per frame. x is a
    constant (height is a y-only metric).
    """
    n = len(com_y_per_frame)
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    poses[:, :, 0] = 0.5
    poses[:, :, 1] = np.asarray(com_y_per_frame, dtype=np.float32)[:, None]
    return poses


def test_jump_height_is_takeoff_minus_peak_not_full_range_repro():
    """#855: jump_height = takeoff − peak, not max − min over the window.

    Input joint y: takeoff=0.50, peak=0.20, landing=0.70. The 2D CoM trajectory
    scales these by a constant mass factor (~1.3): CoM y ≈ 0.65 / 0.26 / 0.91.
    Correct jump_height = takeoff_com − peak_com = 0.65 − 0.26 = 0.39.
    Buggy max−min over the window = 0.91 − 0.26 = 0.65 (landing as max).
    """
    engine = PhysicsEngine(body_mass=60.0)
    # Frames: takeoff(0)=0.50, flight peak(1)=0.20, landing(2)=0.70.
    poses = _pose_with_com_y([0.50, 0.20, 0.70])
    res = engine.analyze_2d(poses, takeoff_idx=0, landing_idx=2, fps=30.0)
    h = res["jump_height"]
    assert h is not None
    assert abs(h - 0.39) < 0.05, (
        f"#855 RED: jump_height={h} for takeoff=0.50 peak=0.20 landing=0.70 — "
        "full range (max−min over window, landing as max) used instead of "
        "takeoff−peak. Landing knee-bend below takeoff inflates the jump height."
    )


def test_jump_height_invariant_to_landing_depth_repro():
    """#855: same jump, two landing depths → same jump_height.

    takeoff_y=0.50, peak_y=0.20. Shallow landing_y=0.55, deep landing_y=0.85.
    Buggy: shallow→0.35, deep→0.65 (0.30 spread for the SAME jump).
    """
    engine = PhysicsEngine(body_mass=60.0)
    shallow = _pose_with_com_y([0.50, 0.20, 0.55])
    deep = _pose_with_com_y([0.50, 0.20, 0.85])
    h_shallow = engine.analyze_2d(shallow, takeoff_idx=0, landing_idx=2, fps=30.0)["jump_height"]
    h_deep = engine.analyze_2d(deep, takeoff_idx=0, landing_idx=2, fps=30.0)["jump_height"]
    assert h_shallow is not None and h_deep is not None
    assert abs(h_shallow - h_deep) < 0.01, (
        f"#855 RED: same jump, shallow landing→{h_shallow}, deep landing→{h_deep} — "
        "jump height varies with landing absorption depth, not jump height. "
        "A deeper knee-bend reports a taller jump."
    )
