"""Repro tests for #1072: get_heatmap_color NaN value silent end color.

Original bug: `min(1.0, NaN)` returns 1.0 (Python's min ignores NaN, first-arg
wins when one operand is NaN). NaN value silently coerced to colormap end
color ('max heat' red for jet, yellow for viridis, white for hot).

Contract (updated by #1204): get_heatmap_color must return gray "unknown"
(128, 128, 128) for non-finite input — visually distinct from real
end colors and from the colormap mid-range, so missing data is
distinguishable from a real extreme value.
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


def test_heatmap_color_nan_value_returns_gray():
    """NaN value must return gray "unknown", not silently map to end color.

    End color for jet is dark red (0, 0, 127). Without guard, NaN+jet
    returns the 'max heat' red — false-positive 'perfect match' for
    similarity heatmaps. With #1204 fix: return gray (128, 128, 128).
    """
    result = get_heatmap_color(float("nan"), 0.0, 1.0, "jet")
    assert result == (128, 128, 128), (
        f"get_heatmap_color(NaN) returned {result}, expected gray (128, 128, 128)"
    )


def test_heatmap_color_inf_value_returns_gray():
    """Inf value must return gray, not silently map to end color."""
    result = get_heatmap_color(float("inf"), 0.0, 1.0, "viridis")
    assert result == (128, 128, 128), f"get_heatmap_color(inf) returned {result}, expected gray"


def test_heatmap_color_nan_with_degenerate_range_returns_gray():
    """NaN + vmax==vmin path: old code `t = 0.5` silently. Must return gray."""
    result = get_heatmap_color(float("nan"), 1.0, 1.0, "jet")
    assert result == (128, 128, 128), (
        f"get_heatmap_color(NaN, 1.0, 1.0) returned {result}, expected gray"
    )


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

    Source inspection guards against a future refactor that re-introduces
    silent NaN coercion (either via int(NaN) crash or end-color mapping).
    """
    src = inspect.getsource(get_heatmap_color)
    assert "isfinite" in src, (
        f"get_heatmap_color must use math.isfinite() to guard non-finite input. Source:\n{src}"
    )
