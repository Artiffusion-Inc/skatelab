"""Repro — `calculate_bounding_box` int(np.min(NaN)) crash (#1201).

Bug: ml/src/visualization/core/geometry.py:421-424

    x_min = max(0, int(np.min(x_coords)) - padding)
    y_min = max(0, int(np.min(y_coords)) - padding)
    x_max = min(width, int(np.max(x_coords)) + padding)
    y_max = min(height, int(np.max(y_coords)) + padding)

`np.min` is NaN-propagating (unlike Python builtin `min`). If any
point has a NaN x or y, `np.min = NaN` and `int(NaN)` raises
`ValueError: cannot convert float NaN to integer`. The crash happens
on lines 421-424 before the `max(0, ...)` clamp can save it.

Fix (NOT applied — repro only): add `math.isfinite` guard at function
entry mirroring PR #1147 (project_3d_to_2d scalar) and PR #1065/#1070
(clip_to_frame) patterns. NaN in any x/y of any point → raise
`ValueError` so upstream bugs surface at the trust boundary instead
of crashing the bbox computation downstream of an undetected NaN.

Methodology (per audit reglement):
  3 observables  (BUG present → PASS; flip to GREEN contract on fix)
  1 regression   (finite points → finite bbox tuple)
  1 source check (math.isfinite guard locked via inspect.getsource)
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from src.visualization.core.geometry import calculate_bounding_box

NAN = float("nan")


# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_calculate_bounding_box_has_isfinite_guard():
    """GREEN contract source check: `calculate_bounding_box` must guard
    NaN inputs with `math.isfinite` or `np.isfinite` BEFORE the int()
    cast. The unfixed function does `int(np.min(x_coords))` with no
    NaN check → `np.min(NaN) = NaN` → `int(NaN) = ValueError`.
    """
    src = inspect.getsource(calculate_bounding_box)

    assert "math.isfinite" in src or "np.isfinite" in src, (
        "calculate_bounding_box has no isfinite guard — "
        "np.min propagates NaN and int(NaN) crashes. "
        "Add an isfinite guard at function entry, before the "
        "np.min/np.max int() cast. Source snippet:\n" + src
    )


# =============================================================================
# Observables — BUG present → crash; fix flips these to raise ValueError.
# =============================================================================


def test_bbox_nan_x_point_raises_value_error():
    """Single NaN x in a point must raise ValueError at the trust
    boundary. The unfixed function crashes with
    `int(NaN) = ValueError: cannot convert float NaN to integer`."""
    pts = np.array([[100.0, 100.0], [200.0, 200.0], [NAN, 150.0]], dtype=np.float32)
    with pytest.raises(ValueError, match="finite"):
        calculate_bounding_box(pts, 1920, 1080, padding=10)


def test_bbox_nan_y_point_raises_value_error():
    """Single NaN y in a point must raise ValueError. Same root cause
    as NaN x — np.min of a NaN-bearing slice propagates NaN."""
    pts = np.array([[100.0, 100.0], [200.0, 200.0], [150.0, NAN]], dtype=np.float32)
    with pytest.raises(ValueError, match="finite"):
        calculate_bounding_box(pts, 1920, 1080, padding=10)


def test_bbox_all_nan_points_raises_value_error():
    """All points NaN — worst case. The unfixed code crashes at
    `int(np.min([NaN, NaN, ...]))`."""
    pts = np.array([[NAN, NAN], [NAN, NAN], [NAN, NAN]], dtype=np.float32)
    with pytest.raises(ValueError, match="finite"):
        calculate_bounding_box(pts, 1920, 1080, padding=10)


# =============================================================================
# Regression — valid finite points must still produce a correct bbox.
# =============================================================================


def test_bbox_finite_points_returns_correct_bbox():
    """Regression: three finite points (100,100), (200,200), (150,150)
    with padding=10 → (90, 90, 210, 210). Mirrors the docstring example.
    The isfinite guard must not regress the happy path."""
    pts = np.array([[100.0, 100.0], [200.0, 200.0], [150.0, 150.0]], dtype=np.float32)
    out = calculate_bounding_box(pts, 1920, 1080, padding=10)
    assert isinstance(out, tuple) and len(out) == 4
    x_min, y_min, x_max, y_max = out
    assert all(isinstance(v, (int, np.integer)) for v in out)
    assert (x_min, y_min, x_max, y_max) == (90, 90, 210, 210)
