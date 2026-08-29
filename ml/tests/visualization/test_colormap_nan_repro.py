"""Repro tests for #1204: get_heatmap_color crashes on NaN value.

Bug: get_heatmap_color raises ValueError on non-finite input at the
isfinite guard, but the colormap branches (jet, viridis, magma, hot)
all hit `int(NaN)` if the guard is bypassed. The crash aborts the
whole colormap sample — should return a gray "unknown" color
(matching get_depth_color, interpolate_color, fade_color patterns)
so missing data is visually distinct instead of aborting the render.

Contract: get_heatmap_color must return (128, 128, 128) for non-finite
input — no raise, no silent end-color mapping, no int(NaN) crash.
"""

from __future__ import annotations

import importlib.util
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

UNKNOWN_GRAY = (128, 128, 128)


def test_viridis_nan_does_not_crash():
    """NaN value with viridis colormap must not raise (issue #1204).

    Old code: int(NaN) in else branch of viridis (line 201) → ValueError.
    New contract: return gray "unknown" (128, 128, 128).
    """
    result = get_heatmap_color(float("nan"), 0.0, 1.0, "viridis")
    assert result == UNKNOWN_GRAY, f"viridis NaN should return gray, got {result}"


def test_magma_nan_does_not_crash():
    """NaN value with magma colormap must not raise (issue #1204).

    Old code: int(NaN) in else branch of magma → ValueError.
    """
    result = get_heatmap_color(float("nan"), 0.0, 1.0, "magma")
    assert result == UNKNOWN_GRAY, f"magma NaN should return gray, got {result}"


def test_jet_nan_does_not_crash():
    """NaN value with jet colormap must not raise (issue #1204).

    Old code: int(NaN) in else branch of jet → ValueError.
    """
    result = get_heatmap_color(float("nan"), 0.0, 1.0, "jet")
    assert result == UNKNOWN_GRAY, f"jet NaN should return gray, got {result}"


def test_hot_nan_does_not_crash():
    """NaN value with hot colormap must not raise (issue #1204)."""
    result = get_heatmap_color(float("nan"), 0.0, 1.0, "hot")
    assert result == UNKNOWN_GRAY, f"hot NaN should return gray, got {result}"


def test_finite_regression_jet_midpoint():
    """Valid finite values still map correctly (regression: don't break normal path).

    jet at t=0.5 is cyan (0, 255, 255) in BGR.
    """
    result = get_heatmap_color(0.5, 0.0, 1.0, "jet")
    assert result == (0, 255, 255), f"jet mid should be cyan BGR, got {result}"
