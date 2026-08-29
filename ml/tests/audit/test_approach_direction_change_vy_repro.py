"""Repro tests — compute_approach_direction_change ignores vy (#851).

``compute_approach_direction_change`` (metrics.py:1098-1125) computes the
heading as ``arctan2(vx, np.ones_like(vx))`` — the second argument is a
constant 1.0, so the call collapses to ``arctan(vx)``. The vertical CoM
velocity ``vy`` never enters the formula. A curved / vertical approach
(CoM rises then falls, vx≈const) yields ~0° — indistinguishable from a
straight approach. GOE bullet 4 "steps_creative_entry" (>=40°) never fires.

Fix (#851): use the real 2D heading ``arctan2(vy, vx)``.

Tests:
  - observable: a vertical CoM swing (vx=const, vy sign flip) reports a
    large direction change (RED: ~0°).
  - observable: a curved approach (vx varies, vy varies) reports non-trivial
    change distinguishable from straight.
  - source-asserting: the source uses arctan2(vy, vx), not arctan2(vx, ones).
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.src.analysis.element_defs import get_element_def
from ml.src.analysis.metrics import BiomechanicsAnalyzer
from ml.src.types import ElementPhase, H36Key


def _poses_with_com_xy(com_xy: np.ndarray) -> np.ndarray:
    """Build (n,17,2) poses whose CoM xy follows com_xy (n,2).

    Hips + shoulders set so calculate_com_trajectory_2d tracks com_xy.
    """
    n = len(com_xy)
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for i in range(n):
        x, y = float(com_xy[i, 0]), float(com_xy[i, 1])
        # CoM is roughly mid-hip / pelvis; set hips + shoulders around it.
        for k in (H36Key.LHIP, H36Key.RHIP):
            poses[i, k, 0] = x
            poses[i, k, 1] = y
        for k in (H36Key.LSHOULDER, H36Key.RSHOULDER):
            poses[i, k, 0] = x
            poses[i, k, 1] = y - 0.5
    return poses


def test_vertical_com_swing_reports_direction_change_repro():
    """#851: CoM moves purely vertically (up then down), vx≈const. Real heading
    rotates ~180°; the buggy arctan(vx) metric reports ~0°.

    RED without the fix: arctan2(vx, ones)=arctan(vx)≈const → sum|diffs|≈0.
    """
    element_def = get_element_def("waltz_jump")
    analyzer = BiomechanicsAnalyzer(element_def)

    n = 21
    t = np.linspace(0, 1, n)
    # vx constant (gentle forward drift); vy swings down then up (jump shape).
    com_x = 0.2 * t  # constant forward velocity
    com_y = 0.3 * (2 * (t - 0.5) ** 2 - 0.5)  # parabola: down then up
    com_xy = np.stack([com_x, com_y], axis=1)
    poses = _poses_with_com_xy(com_xy)

    phases = ElementPhase(name="waltz_jump", start=0, takeoff=15, peak=17, landing=18, end=20)
    change = analyzer.compute_approach_direction_change(poses, phases, fps=30.0)
    # Real heading arctan2(vy, vx) swings well past 40° across the arc.
    assert change > 40.0, (
        f"#851 RED: vertical CoM swing reported direction_change={change:.3f}° — "
        "vy ignored (arctan(vx)≈const). Real heading rotates >40°."
    )


def test_curved_approach_exceeds_straight_repro():
    """#851: a curved approach (both vx and vy vary) must report a larger
    direction change than a purely straight (constant-vx, vy=0) approach.

    RED without the fix: both read ~0° because vy is ignored and vx is the
    only signal — a curve dominated by vy reads the same as straight.
    """
    element_def = get_element_def("waltz_jump")
    analyzer = BiomechanicsAnalyzer(element_def)

    n = 21
    t = np.linspace(0, 1, n)
    # Straight: vx const, vy=0.
    straight = _poses_with_com_xy(np.stack([0.2 * t, np.zeros(n)], axis=1))
    # Curved: vx const, vy swings (turn-in then extension).
    curved = _poses_with_com_xy(np.stack([0.2 * t, 0.25 * np.sin(np.pi * t)], axis=1))

    phases = ElementPhase(name="waltz_jump", start=0, takeoff=15, peak=17, landing=18, end=20)
    straight_change = analyzer.compute_approach_direction_change(straight, phases, fps=30.0)
    curved_change = analyzer.compute_approach_direction_change(curved, phases, fps=30.0)
    assert curved_change > straight_change, (
        f"#851 RED: curved ({curved_change:.3f}°) not > straight "
        f"({straight_change:.3f}°) — vy contribution ignored."
    )


def test_source_uses_vy_vx_heading_repro():
    """#851 GREEN: source must compute heading as arctan2(vy, vx), not
    arctan2(vx, ones)."""
    import inspect

    src = inspect.getsource(BiomechanicsAnalyzer.compute_approach_direction_change)
    assert "np.ones_like" not in src, (
        "#851: compute_approach_direction_change still uses arctan2(vx, "
        "np.ones_like(vx)) = arctan(vx) — vy ignored. Use arctan2(vy, vx)."
    )
    assert "arctan2" in src, "#851: must use arctan2 for full 2D heading."
