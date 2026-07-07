"""Repro tests for #1072: get_heatmap_color NaN value silent end color.

Bug: `min(1.0, NaN)` returns 1.0 (Python's min ignores NaN, first-arg wins
when one operand is NaN). NaN value silently coerces to colormap end color
('max heat' red for jet, yellow for viridis, white for hot).

Contract: get_heatmap_color must reject non-finite input with ValueError
so silent "perfect match" output is impossible for corrupted input
(NaN similarity, broken sensor, gap-fill failure).
"""

from __future__ import annotations

import importlib.util
import inspect
import math
import sys
import types
from pathlib import Path

# Stub heavy deps to avoid cv2/PIL/scipy chain
_viz_pkg = types.ModuleType("src.visualization")
_viz_pkg.__path__ = []
sys.modules.setdefault("src", types.ModuleType("src"))
sys.modules.setdefault("src.visualization", _viz_pkg)

_config_stub = types.ModuleType("src.visualization.config")
_config_stub.DEPTH_COLORS = [
    (0, 0, 255),
    (0, 128, 255),
    (0, 255, 255),
    (0, 255, 128),
    (0, 255, 0),
    (128, 255, 0),
    (255, 255, 0),
    (255, 128, 0),
    (255, 0, 0),
]
_config_stub.blade_inside_color = (0, 255, 0)
_config_stub.blade_outside_color = (0, 0, 255)
_config_stub.blade_flat_color = (0, 255, 255)
_config_stub.blade_unknown_color = (255, 255, 255)
sys.modules["src.visualization.config"] = _config_stub

_types_stub = types.ModuleType("src.types")


class _BladeType:
    INSIDE = "inside"
    OUTSIDE = "outside"
    FLAT = "flat"
    TOE_PICK = "toe_pick"
    UNKNOWN = "unknown"


_types_stub.BladeType = _BladeType
sys.modules["src.types"] = _types_stub

# Load colors.py
_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src" / "visualization" / "core" / "colors.py"
_spec = importlib.util.spec_from_file_location("colors_under_test", _SRC)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["colors_under_test"] = _mod
_spec.loader.exec_module(_mod)
get_heatmap_color = _mod.get_heatmap_color


def test_heatmap_color_nan_value_raises():
    """NaN value must raise ValueError, not silently map to end color.

    End color for jet is dark red (0, 0, 127). Without guard, NaN+jet
    returns the 'max heat' red — false-positive 'perfect match' for
    similarity heatmaps.
    """
    try:
        result = get_heatmap_color(float("nan"), 0.0, 1.0, "jet")
    except ValueError:
        return
    raise AssertionError(f"get_heatmap_color(NaN) returned {result} instead of raising ValueError")


def test_heatmap_color_inf_value_raises():
    """Inf value must raise ValueError, not silently map to end color."""
    try:
        result = get_heatmap_color(float("inf"), 0.0, 1.0, "viridis")
    except ValueError:
        return
    raise AssertionError(f"get_heatmap_color(inf) returned {result} instead of raising ValueError")


def test_heatmap_color_nan_with_degenerate_range_raises():
    """NaN + vmax==vmin path: old code `t = 0.5` silently. Must raise."""
    try:
        result = get_heatmap_color(float("nan"), 1.0, 1.0, "jet")
    except ValueError:
        return
    raise AssertionError(f"get_heatmap_color(NaN, 1.0, 1.0) returned {result} instead of raising")


def test_heatmap_color_valid_finite_regression():
    """Valid finite values still map to colors (no regression on fix)."""
    # Midpoint of jet is cyan
    out_mid = get_heatmap_color(0.5, 0.0, 1.0, "jet")
    assert out_mid == (0, 255, 255), f"jet mid should be cyan, got {out_mid}"
    # Min is blue
    out_min = get_heatmap_color(0.0, 0.0, 1.0, "jet")
    assert out_min == (255, 0, 0), f"jet min should be blue, got {out_min}"
    # Max is dark red
    out_max = get_heatmap_color(1.0, 0.0, 1.0, "jet")
    assert out_max == (0, 0, 127), f"jet max should be dark red, got {out_max}"


def test_heatmap_color_source_uses_isfinite_guard():
    """Source-check: math.isfinite guard must be in get_heatmap_color body.

    The fix is an explicit `not math.isfinite(value)` check that raises
    before the min/max clamp. Source inspection guards against a future
    refactor that re-introduces silent NaN coercion.
    """
    src = inspect.getsource(get_heatmap_color)
    assert "isfinite" in src, (
        f"get_heatmap_color must use math.isfinite() to guard non-finite input. Source:\n{src}"
    )
    # And the guard must raise, not silently return gray
    assert "ValueError" in src or "raise" in src, (
        f"get_heatmap_color must raise on non-finite input (not return gray). Source:\n{src}"
    )
