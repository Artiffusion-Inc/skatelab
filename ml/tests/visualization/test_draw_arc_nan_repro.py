"""Repro — `JointAngleLayer._draw_arc` int(NaN) crash (#1244).

Bug: ml/src/visualization/layers/joint_angle_layer.py:365

    cv2.ellipse(
        frame,
        (int(vx), int(vy)),
        ...
    )

When `vertex` has NaN coords (corrupt joint position, missing skeletal
data, partial tracking), `int(NaN) = ValueError: cannot convert float
NaN to integer`. Crash happens before cv2.ellipse is called.

Fix (NOT applied — repro only): add `math.isfinite(...)` guard on the
vertex so NaN arcs are silently skipped, mirroring the existing
`np.isnan(pose[...])` skip in `render()` (line 216-221). One-line guard
in the shared function — every caller routes through it.

Methodology (per audit reglement):
  3 observables  (BUG present → crash; fix flips these to no-op)
  1 regression   (finite vertex → arc still rendered)
  1 source check (math.isfinite guard locked via inspect.getsource)
"""

from __future__ import annotations

import inspect

import numpy as np

from src.visualization.layers.joint_angle_layer import JointAngleLayer

NAN = float("nan")


# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_draw_arc_has_isfinite_guard():
    """GREEN contract source check: `_draw_arc` must guard NaN vertex
    coords with `math.isfinite` or `np.isfinite` BEFORE the `int()`
    cast. The unfixed function does `(int(vx), int(vy))` with no
    NaN check → `int(NaN) = ValueError: cannot convert float NaN to
    integer`.
    """
    src = inspect.getsource(JointAngleLayer._draw_arc)

    assert "math.isfinite" in src or "np.isfinite" in src, (
        "_draw_arc has no isfinite guard — int(NaN) crashes. "
        "Add an isfinite guard at function entry, before the "
        "int() cast on the vertex. Source snippet:\n" + src
    )


# =============================================================================
# Observables — BUG present → crash; fix flips these to no-op.
# =============================================================================


def test_draw_arc_nan_vertex_x_does_not_crash():
    """NaN x in vertex must not crash. The unfixed function raises
    `ValueError: cannot convert float NaN to integer` at line 365."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    vertex = np.array([NAN, 240.0], dtype=np.float64)
    pa = np.array([300.0, 180.0], dtype=np.float64)
    pc = np.array([300.0, 300.0], dtype=np.float64)
    # Must not raise.
    JointAngleLayer._draw_arc(frame, vertex, pa, pc, 10, (255, 255, 255))


def test_draw_arc_nan_vertex_y_does_not_crash():
    """NaN y in vertex must not crash. Same root cause as NaN x —
    both vx and vy hit `int()` cast unguarded."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    vertex = np.array([300.0, NAN], dtype=np.float64)
    pa = np.array([300.0, 180.0], dtype=np.float64)
    pc = np.array([300.0, 300.0], dtype=np.float64)
    JointAngleLayer._draw_arc(frame, vertex, pa, pc, 10, (255, 255, 255))


def test_draw_arc_all_nan_vertex_does_not_crash():
    """All-NaN vertex — worst case. The unfixed code crashes at
    `(int(NaN), int(NaN))` on the first call into cv2.ellipse args."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    vertex = np.array([NAN, NAN], dtype=np.float64)
    pa = np.array([300.0, 180.0], dtype=np.float64)
    pc = np.array([300.0, 300.0], dtype=np.float64)
    JointAngleLayer._draw_arc(frame, vertex, pa, pc, 10, (255, 255, 255))


# =============================================================================
# Regression — valid finite vertex must still draw the arc.
# =============================================================================


def test_draw_arc_finite_vertex_renders():
    """Regression: finite vertex (300, 240) with pa=(300,180), pc=(300,300)
    must draw an arc (frame pixel count > 0). The isfinite guard must
    not regress the happy path."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    vertex = np.array([300.0, 240.0], dtype=np.float64)
    pa = np.array([300.0, 180.0], dtype=np.float64)
    pc = np.array([300.0, 300.0], dtype=np.float64)
    JointAngleLayer._draw_arc(frame, vertex, pa, pc, 10, (255, 255, 255))
    assert frame.any(), "finite vertex should draw at least one pixel"
