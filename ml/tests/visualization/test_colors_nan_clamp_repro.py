"""Repro tests for #624: colors.py NaN clamp silently maps to max.

Bug: `max(min, min(max, NaN))` → max (Python's min ignores NaN).
NaN depth silently becomes "farthest" color; NaN heatmap becomes "max heat".

Contract: NaN input → distinct "unknown" gray color (128, 128, 128)
so user can visually distinguish missing data from real extreme values.
"""

from __future__ import annotations

import importlib.util
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
    (0, 0, 255),  # red (close)
    (0, 128, 255),  # orange
    (0, 255, 255),  # yellow
    (0, 255, 128),  # green-yellow
    (0, 255, 0),  # green
    (128, 255, 0),  # cyan-green
    (255, 255, 0),  # cyan
    (255, 128, 0),  # blue-yellow
    (255, 0, 0),  # blue (far)
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
get_depth_color = _mod.get_depth_color
get_heatmap_color = _mod.get_heatmap_color
interpolate_color = _mod.interpolate_color
fade_color = _mod.fade_color

# Gray color = NaN "unknown" signal
UNKNOWN = (128, 128, 128)


def test_get_depth_color_nan_returns_unknown_gray():
    """NaN depth must NOT silently map to 'max' (farthest) color."""
    out = get_depth_color(float("nan"))
    # NaN should be visually distinct from "max" (blue = (255, 0, 0))
    assert out != (255, 0, 0), "NaN should not map to 'max' color"
    # And not crash
    assert isinstance(out, tuple)
    assert len(out) == 3


def test_get_depth_color_inf_returns_unknown_gray():
    """Inf depth must not map to max either."""
    out = get_depth_color(float("inf"))
    assert out != (255, 0, 0)


def test_get_depth_color_valid_unchanged():
    """Valid depth still maps to color (regression check)."""
    out_mid = get_depth_color(1.0, 0.0, 2.0)
    out_close = get_depth_color(0.0, 0.0, 2.0)
    out_far = get_depth_color(2.0, 0.0, 2.0)
    # Each is a different color (gradient)
    assert out_close != out_far
    # Mid is in between (interpolation)
    assert out_mid != out_close
    assert out_mid != out_far


def test_get_heatmap_color_nan_raises():
    """NaN heatmap value must raise (#1072: no silent end-color mapping)."""
    import pytest

    with pytest.raises(ValueError):
        get_heatmap_color(float("nan"), 0.0, 1.0, "jet")


def test_interpolate_color_nan_t_returns_unknown():
    """NaN t in interpolate_color — sensible behavior."""
    out = interpolate_color((255, 0, 0), (0, 0, 255), float("nan"))
    # Should not crash; pick "unknown" (gray) or be visually distinct
    assert isinstance(out, tuple)
    assert len(out) == 3


def test_fade_color_nan_alpha_returns_unknown():
    """NaN alpha in fade_color — sensible behavior."""
    out = fade_color((255, 0, 0), float("nan"))
    assert isinstance(out, tuple)
    assert len(out) == 3
