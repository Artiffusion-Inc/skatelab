"""Repro tests for #1241: depth_to_color silently clamps NaN depth to max.

Bug: `max(depth_min, min(depth_max, NaN))` returns depth_max because Python's
min/max skip NaN operands. NaN depth silently rendered as the "far" color
(DEPTH_COLORS[-1] = (0, 0, 255) BGR / blue), hiding data quality loss from
the coach.

Contract:
- Scalar `get_depth_color(NaN)` must NOT return the "max/far" color.
  It must return the gray "unknown" sentinel (128, 128, 128).
- Vectorized `get_depth_colors_vectorized(NaN array)` must not produce
  garbage (np.int64.min) indices, RuntimeWarnings, or NaN pixels.
- Valid depth values must still map to the gradient (regression).
- Inf must also be guarded (same code path).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np

# Stub heavy deps to avoid cv2/PIL/scipy chain
_viz_pkg = types.ModuleType("src.visualization")
_viz_pkg.__path__ = []
sys.modules.setdefault("src", types.ModuleType("src"))
sys.modules.setdefault("src.visualization", _viz_pkg)

_config_stub = types.ModuleType("src.visualization.config")
_config_stub.DEPTH_COLORS = [
    (255, 0, 0),  # close (BGR)
    (128, 128, 0),
    (0, 255, 0),
    (0, 128, 128),
    (0, 0, 255),  # far (BGR)
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
get_depth_colors_vectorized = _mod.get_depth_colors_vectorized

# "Unknown" gray sentinel
UNKNOWN = (128, 128, 128)
# "Max/far" color (DEPTH_COLORS[-1] in BGR) — the silent-clamp output pre-fix
FAR = (0, 0, 255)


# ---------------------------------------------------------------------------
# Scalar get_depth_color
# ---------------------------------------------------------------------------


def test_get_depth_color_nan_not_silently_max():
    """NaN depth must NOT return the 'max/far' color (the silent-clamp bug).

    Pre-fix: max(0.0, min(2.0, NaN)) = 2.0 → DEPTH_COLORS[-1] = (0, 0, 255).
    Post-fix: math.isfinite guard returns gray (128, 128, 128).
    """
    out = get_depth_color(float("nan"), 0.0, 2.0)
    assert out != FAR, f"NaN depth must not silently clamp to max color; got {out} (== FAR)"
    assert out == UNKNOWN, f"NaN depth should return gray 'unknown' sentinel; got {out}"


def test_get_depth_color_inf_not_silently_max():
    """Inf depth must also be guarded (same code path, same contract)."""
    out = get_depth_color(float("inf"), 0.0, 2.0)
    assert out != FAR, f"Inf depth must not silently clamp to max; got {out}"
    assert out == UNKNOWN, f"Inf depth should return gray 'unknown' sentinel; got {out}"


def test_get_depth_color_valid_unchanged_regression():
    """Valid depth must still map to gradient (regression — fix did not break the path)."""
    out_close = get_depth_color(0.0, 0.0, 2.0)
    out_far = get_depth_color(2.0, 0.0, 2.0)
    out_mid = get_depth_color(1.0, 0.0, 2.0)

    # Endpoints anchor gradient
    assert out_close == (255, 0, 0), f"close endpoint broken: {out_close}"
    assert out_far == (0, 0, 255), f"far endpoint broken: {out_far}"
    # Mid interpolates between two distinct endpoints
    assert out_mid != out_close, "mid must differ from close"
    assert out_mid != out_far, "mid must differ from far"


def test_get_depth_color_negative_inf_not_silently_min():
    """-Inf depth must also be guarded (NaN/Inf are non-finite in both directions)."""
    out = get_depth_color(float("-inf"), 0.0, 2.0)
    assert out == UNKNOWN, f"-Inf depth should return gray 'unknown'; got {out}"


# ---------------------------------------------------------------------------
# Vectorized get_depth_colors_vectorized
# ---------------------------------------------------------------------------


def test_get_depth_colors_vectorized_nan_not_garbage():
    """Vectorized version must also guard NaN.

    Pre-fix: np.clip(NaN, 0, 1) = NaN, NaN.astype(int) = np.int64.min
    → negative index, RuntimeWarning, garbage RGB.
    Post-fix: NaN pixels must be the gray 'unknown' sentinel.
    """
    depths = np.array([0.0, 1.0, np.nan, 2.0], dtype=np.float32)
    out = get_depth_colors_vectorized(depths, 0.0, 2.0)
    # Output shape preserves input shape + color dim
    assert out.shape == (4, 3), f"unexpected shape {out.shape}"
    # NaN row must equal the gray 'unknown' sentinel
    nan_row = tuple(int(v) for v in out[2])
    assert nan_row == UNKNOWN, f"NaN row must be gray 'unknown' (128,128,128); got {nan_row}"
    # And NOT the far color
    assert nan_row != (0, 0, 255), f"NaN row must not be FAR color; got {nan_row}"
    # No NaN leaks into output
    assert not np.any(np.isnan(out)), "NaN must not leak into output pixels"
