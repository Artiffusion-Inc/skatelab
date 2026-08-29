"""Repro tests for #1242: blend_colors crashes on NaN weight.

Bug: `(int(b), int(g), int(r))` raises `ValueError: cannot convert float NaN
to integer` when any weight is NaN. `if total_weight == 0` does NOT catch
NaN (NaN != 0, and `if NaN` is truthy), so NaN falls through to the int() cast.

Contract: NaN weight must NOT crash. Return gray "unknown" (128, 128, 128)
to be consistent with other NaN guards in colors.py (see fade_color, #624).
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
blend_colors = _mod.blend_colors

# Gray "unknown" signal — consistent with #624 NaN guards
UNKNOWN = (128, 128, 128)


def test_blend_colors_nan_weight_does_not_crash():
    """NaN weight must not raise ValueError (#1242)."""
    colors = [(255, 0, 0), (0, 0, 255)]
    weights = [float("nan"), 1.0]
    # Must not raise
    out = blend_colors(colors, weights)
    assert isinstance(out, tuple)
    assert len(out) == 3


def test_blend_colors_all_nan_weights_returns_unknown():
    """All-NaN weights must return gray "unknown" (no total_weight=0 fallback)."""
    colors = [(255, 0, 0), (0, 0, 255)]
    weights = [float("nan"), float("nan")]
    out = blend_colors(colors, weights)
    # NaN should be visually distinct from a normal blend
    # (255,0,0)+(0,0,255) would be ~(128,0,128) — gray signals "unknown"
    assert out == UNKNOWN, f"All-NaN weights should return gray, got {out}"


def test_blend_colors_nan_weight_in_middle():
    """NaN weight in middle of list must not crash."""
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    weights = [0.5, float("nan"), 0.5]
    out = blend_colors(colors, weights)
    assert isinstance(out, tuple)
    assert len(out) == 3


def test_blend_colors_inf_weight_does_not_crash():
    """Inf weight must not crash (same class of bug as NaN)."""
    colors = [(255, 0, 0), (0, 0, 255)]
    weights = [float("inf"), 1.0]
    out = blend_colors(colors, weights)
    assert isinstance(out, tuple)
    assert len(out) == 3
    # All ints, no NaN/Inf leaked
    for ch in out:
        assert isinstance(ch, int)
        assert not (isinstance(ch, float) and math.isnan(ch))


def test_blend_colors_valid_unchanged_regression():
    """Valid finite weights must still blend correctly (no regression)."""
    colors = [(255, 0, 0), (0, 0, 255)]
    weights = [0.5, 0.5]
    out = blend_colors(colors, weights)
    # Equal blend: BGR average (int truncates 127.5 → 127)
    # c1 = (255, 0, 0) BGR, c2 = (0, 0, 255) BGR
    # b_avg = int(255*0.5 + 0*0.5) = 127, g_avg = 0, r_avg = int(0*0.5 + 255*0.5) = 127
    assert out == (127, 0, 127), f"Expected equal blend (127,0,127), got {out}"


def test_blend_colors_zero_weight_still_works_regression():
    """All-zero weights still hit the existing (0,0,0) path (#1242 must not break this)."""
    colors = [(255, 0, 0), (0, 0, 255)]
    weights = [0.0, 0.0]
    out = blend_colors(colors, weights)
    assert out == (0, 0, 0)
