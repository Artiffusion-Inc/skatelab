"""Repro tests for #1078: fade_color NaN alpha returns original color.

Bug: `min(1.0, NaN) = 1.0` (Python's min ignores NaN, first-arg wins).
NaN alpha silently coerces to 1.0 (the "no fade" default), so the
ORIGINAL color is returned for corrupted input — indistinguishable
from a legitimate alpha=1.0.

Contract: fade_color must reject non-finite alpha with a distinguishable
"unknown" result (e.g. gray) so corrupted fade parameters are visible
to the user, not silently rendered as if no fade was requested.

Methodology (audit reglement):
  3 observables  (NaN/Inf alpha must NOT return original color)
  1 regression   (valid alpha=0.5 still produces dim color)
  1 source check (inspect.getsource confirms isfinite guard present)
"""

from __future__ import annotations

import importlib.util
import inspect
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
_COLORS_PATH = _HERE.parent.parent / "src" / "visualization" / "core" / "colors.py"
_spec = importlib.util.spec_from_file_location("src.visualization.core.colors", _COLORS_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["src.visualization.core.colors"] = _mod

fade_color = _mod.fade_color


# =============================================================================
# Observables (NaN/Inf alpha must NOT silently return original color)
# =============================================================================


def test_fade_color_nan_alpha_does_not_return_original():
    """NaN alpha must not silently return the input color (#1078).

    Bug: min(1.0, NaN) = 1.0, so int(color[0] * 1.0) = color[0].
    Contract: NaN alpha must produce a distinguishable "unknown" result.
    """
    out = fade_color((255, 0, 0), float("nan"))
    assert out != (255, 0, 0), (
        f"NaN alpha silently returned original color {out}; "
        "must produce a distinguishable 'unknown' color (e.g. gray)."
    )


def test_fade_color_pos_inf_alpha_does_not_return_original():
    """+Inf alpha must not silently return the input color (#1078).

    Bug: min(1.0, +Inf) = 1.0, so int(color[0] * 1.0) = color[0].
    Contract: +Inf alpha must produce a distinguishable "unknown" result.
    """
    out = fade_color((255, 0, 0), float("inf"))
    assert out != (255, 0, 0), (
        f"+Inf alpha silently returned original color {out}; "
        "must produce a distinguishable 'unknown' color."
    )


def test_fade_color_neg_inf_alpha_does_not_return_original():
    """-Inf alpha must not silently return black (#1078 sibling check).

    Bug: max(0.0, -Inf) = 0.0, so int(color[0] * 0.0) = 0. Symmetric
    silent failure mode to NaN.
    Contract: -Inf alpha must produce a distinguishable "unknown" result.
    """
    out = fade_color((255, 0, 0), float("-inf"))
    assert out != (0, 0, 0), (
        f"-Inf alpha silently returned black {out}; must produce a distinguishable 'unknown' color."
    )


# =============================================================================
# Regression (valid alpha must still work)
# =============================================================================


def test_fade_color_valid_alpha_unchanged():
    """Regression: alpha=0.5 must still dim the color correctly."""
    out = fade_color((255, 0, 0), 0.5)
    assert out == (127, 0, 0), f"alpha=0.5 should dim red to (127, 0, 0), got {out}"


# =============================================================================
# Source check (root-cause guard must exist in source)
# =============================================================================


def test_fade_color_has_isfinite_guard():
    """Root cause: NaN-blind min/max in fade_color. Lock the fix in source.

    Without `math.isfinite(alpha)` check, Python's min(1.0, NaN) = 1.0
    silently coerces NaN to 1.0. Lock the guard via inspect.getsource
    to prevent future regression (e.g. someone removing it as "redundant").
    """
    src = inspect.getsource(fade_color)
    assert "math.isfinite" in src, (
        "fade_color must guard against non-finite alpha via math.isfinite; "
        "silent NaN→1.0 coercion via min/max is the bug (#1078)."
    )
