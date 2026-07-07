"""Repro — `JointAngleLayer._project_3d_arc_2d` silently propagates NaN (#1263).

Bug: ml/src/visualization/layers/joint_angle_layer.py:281,289,295

    cos_angle = np.clip(np.dot(e1, vc_hat), -1.0, 1.0)
    sweep = np.arccos(cos_angle)

Issue: any 3D keypoint NaN → va/vc NaN → va_len/vc_len NaN →
`< 1e-6` guard returns False (NaN < X = False) → e1/vc_hat NaN →
np.dot NaN → `np.clip(NaN, -1.0, 1.0) = NaN` silently → arccos(NaN) = NaN
→ sweep = NaN → arc_local NaN → broken arc in video overlay.

Compound: the early-return guards `va_len < 1e-6`, `vc_len < 1e-6`,
`normal_len < 1e-6` all MISS NaN (NaN < X = False), so corrupt data
flows past the safety net.

Fix (NOT applied — repro only): `math.isfinite(...) and ... >= 1e-6`
guards on lengths, `math.isfinite(cos_angle)` guard before arccos.
Surgical, one function, all callers route through it.

Methodology (per audit reglement):
  3 RED observables  (BUG present → NaN leaks; fix flips these to None)
  1 regression       (finite input → real arc returned)
  1 source check     (isfinite + isfinite-NaN guard locked via inspect)
"""

from __future__ import annotations

import inspect

import numpy as np

from src.visualization.layers.joint_angle_layer import JointAngleLayer

NAN = float("nan")


def _valid_3d():
    """Triangle in 3D space — non-degenerate, non-collinear."""
    return (
        np.array([0.0, 1.0, 0.0], dtype=np.float64),  # a_3d
        np.array([0.0, 0.0, 0.0], dtype=np.float64),  # v_3d
        np.array([1.0, 0.0, 0.0], dtype=np.float64),  # c_3d
        np.array([300.0, 180.0], dtype=np.float64),  # a_2d
        np.array([300.0, 240.0], dtype=np.float64),  # v_2d
        np.array([300.0, 300.0], dtype=np.float64),  # c_2d
    )


# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_project_3d_arc_2d_has_isfinite_guards():
    """GREEN contract source check: `_project_3d_arc_2d` must guard NaN
    inputs with `math.isfinite` on the length checks AND before the
    `np.clip`/arccos path. The unfixed function only checks `len < 1e-6`,
    which is False for NaN — corrupt NaN flows past the guard.
    """
    src = inspect.getsource(JointAngleLayer._project_3d_arc_2d)

    assert "math.isfinite" in src or "np.isfinite" in src, (
        "_project_3d_arc_2d has no isfinite guard — NaN inputs "
        "propagate silently through np.clip + arccos. "
        "Add isfinite guards on va_len/vc_len/normal_len and on "
        "cos_angle before arccos. Source snippet:\n" + src
    )


# =============================================================================
# Observables — BUG present → NaN leaks; fix flips these to None.
# =============================================================================


def test_project_3d_arc_2d_nan_in_a_3d_returns_none():
    """NaN in a_3d must not produce a NaN array. The unfixed function
    returns an array full of NaN because va_len, vc_len are NaN, the
    `< 1e-6` guard is False for NaN, and np.clip(NaN) = NaN."""
    a_3d, v_3d, c_3d, a_2d, v_2d, c_2d = _valid_3d()
    a_3d = np.array([NAN, NAN, NAN], dtype=np.float64)
    result = JointAngleLayer._project_3d_arc_2d(a_3d, v_3d, c_3d, a_2d, v_2d, c_2d, radius=0.1)
    # Fix flips this to None. BUG returns a NaN array.
    assert result is None, (
        f"Expected None for NaN input, got array with NaN: "
        f"{result if result is None else np.isnan(result).any()}"
    )


def test_project_3d_arc_2d_nan_in_v_3d_returns_none():
    """NaN in v_3d (the vertex) — degenerate by definition since
    va = a_3d - v_3d and vc = c_3d - v_3d. Same NaN-leak path."""
    a_3d, v_3d, c_3d, a_2d, v_2d, c_2d = _valid_3d()
    v_3d = np.array([NAN, NAN, NAN], dtype=np.float64)
    result = JointAngleLayer._project_3d_arc_2d(a_3d, v_3d, c_3d, a_2d, v_2d, c_2d, radius=0.1)
    assert result is None, (
        f"Expected None for NaN vertex, got array with NaN: "
        f"{result if result is None else np.isnan(result).any()}"
    )


def test_project_3d_arc_2d_nan_in_c_3d_returns_none():
    """NaN in c_3d — corrupt 3D skeleton data, should not produce a
    NaN array. Same NaN-leak path as the others."""
    a_3d, v_3d, c_3d, a_2d, v_2d, c_2d = _valid_3d()
    c_3d = np.array([NAN, NAN, NAN], dtype=np.float64)
    result = JointAngleLayer._project_3d_arc_2d(a_3d, v_3d, c_3d, a_2d, v_2d, c_2d, radius=0.1)
    assert result is None, (
        f"Expected None for NaN c_3d, got array with NaN: "
        f"{result if result is None else np.isnan(result).any()}"
    )


def test_project_3d_arc_2d_partial_nan_returns_none():
    """Single-NaN component in a_3d (e.g. corrupt depth) — same NaN
    propagation, must return None."""
    a_3d, v_3d, c_3d, a_2d, v_2d, c_2d = _valid_3d()
    a_3d = np.array([0.0, 1.0, NAN], dtype=np.float64)
    result = JointAngleLayer._project_3d_arc_2d(a_3d, v_3d, c_3d, a_2d, v_2d, c_2d, radius=0.1)
    assert result is None, (
        f"Expected None for partial NaN, got array with NaN: "
        f"{result if result is None else np.isnan(result).any()}"
    )


# =============================================================================
# Regression — finite input must still produce a real arc.
# =============================================================================


def test_project_3d_arc_2d_finite_input_returns_valid_arc():
    """Regression: clean 3D triangle (non-collinear, non-NaN) must
    return an (n_points+1, 2) array of finite 2D pixel positions.
    The isfinite guards must not regress the happy path."""
    a_3d, v_3d, c_3d, a_2d, v_2d, c_2d = _valid_3d()
    result = JointAngleLayer._project_3d_arc_2d(
        a_3d, v_3d, c_3d, a_2d, v_2d, c_2d, radius=0.1, n_points=24
    )
    assert result is not None, "finite input must produce an arc, got None"
    assert result.shape == (25, 2), f"expected (25, 2), got {result.shape}"
    assert np.isfinite(result).all(), f"finite input must not contain NaN/inf: {result}"
