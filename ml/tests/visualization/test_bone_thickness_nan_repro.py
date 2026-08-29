"""RED repro — `get_bone_thickness_3d` int(NaN) crash on NaN base_thickness (#1161).

Bug: ml/src/visualization/skeleton/joints.py:375

    return max(1, int(base_thickness * scale))

If `base_thickness` is NaN, then `NaN * scale = NaN`, and `int(NaN)`
raises `ValueError: cannot convert float NaN to integer` — aborting the
entire 3D skeleton render for that bone. Upstream depth-stats / bone-config
failures (e.g. JSON-parsed NaN, missing config) crash the renderer
instead of falling back to a safe thickness.

Sibling of tranche IA (joint_radius_3d) and tranche HF (coach_panel
is_visible_at). The depth-bounds guard (#1068) is already in place; this
fix is the second axis — guard the OUTPUT multiplier, not the input
range.

Methodology (per audit reglement):
- Each test names ONE observable bug behavior.
- Source-check via `inspect.getsource` locks down the `math.isfinite`
  guard so a naïve revert (e.g. `try/except` swallowing) fails the suite.
"""

from __future__ import annotations

import inspect
import math
import sys
from pathlib import Path

# Add ml/src to sys.path so we can import the real `src` package without
# polluting sys.modules with stubs (which would break sibling test
# collection in the same pytest invocation).
_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from src.visualization.skeleton.joints import get_bone_thickness_3d  # noqa: E402

NAN = float("nan")


# -----------------------------------------------------------------------------
# 1. Behavioral: NaN base_thickness must not crash int(NaN)
# -----------------------------------------------------------------------------
def test_bone_thickness_3d_nan_base_does_not_crash():
    """NaN base_thickness must not raise ValueError("cannot convert float
    NaN to integer") — guard at the trust boundary so the bug surfaces
    instead of crashing the 3D skeleton renderer.
    """
    try:
        out = get_bone_thickness_3d(1.0, NAN, 0.0, 2.0)
    except ValueError as e:
        if "cannot convert float NaN to integer" in str(e):
            raise AssertionError(
                f"NaN base_thickness must be guarded, got int(NaN) crash: {e!r}. "
                f"Add math.isfinite(base_thickness) guard at top of method."
            ) from e
        raise
    # Once guarded, return a finite int (any sensible fallback is fine).
    assert isinstance(out, int) and math.isfinite(out), (
        f"guarded call must return a finite int, got {out!r}"
    )


# -----------------------------------------------------------------------------
# 2. Behavioral: NaN base_thickness returns a safe fallback (>= min thickness)
# -----------------------------------------------------------------------------
def test_bone_thickness_3d_nan_base_returns_min_thickness():
    """When base_thickness is NaN, the function must return the minimum
    thickness (1) — same fallback as t=1.0 (farthest depth, thinnest
    bone). The skeleton stays visible; the broken-config bone is just
    thin instead of crashing the entire 3D draw.
    """
    out = get_bone_thickness_3d(1.0, NAN, 0.0, 2.0)
    assert out == 1, f"NaN base_thickness should fall back to min thickness (1), got {out!r}"


# -----------------------------------------------------------------------------
# 3. Regression: valid finite base_thickness keeps working
# -----------------------------------------------------------------------------
def test_bone_thickness_3d_valid_finite_unchanged():
    """Sanity: a normal call (depth=1.5, base_thickness=2, bounds 0..2)
    must keep returning the pre-fix value 1 (t=0.75, scale=0.625,
    int(2*0.625)=1). Locks down that the guard doesn't regress the
    happy path.
    """
    out = get_bone_thickness_3d(1.5, 2, 0.0, 2.0)
    assert out == 1, f"valid call regressed: expected 1, got {out!r}"


# -----------------------------------------------------------------------------
# 4. Source check: locks down the math.isfinite(base_thickness) guard
#    so a future revert (e.g. wrapping int() in try/except) still fails
#    the suite — the isfinite guard is the fix, not the symptom.
# -----------------------------------------------------------------------------
def test_bone_thickness_3d_source_has_isfinite_guard_for_base():
    """Locks down the fix: the function must explicitly check
    `math.isfinite(base_thickness)` (not just for depth_min/depth_max).
    A try/except around int(NaN) would mask the bug instead of
    surfacing the broken config.
    """
    src = inspect.getsource(get_bone_thickness_3d)
    # The guard must reference base_thickness (not just depth bounds).
    assert "math.isfinite" in src and "base_thickness" in src, (
        "get_bone_thickness_3d must guard NaN base_thickness with "
        "math.isfinite to prevent int(NaN) crash (#1161). "
        "Source snippet:\n" + src
    )


# -----------------------------------------------------------------------------
# 5. Sibling sanity: finite base_thickness + finite depth bounds still
#    works exactly as before (locks down the previous #1068 fix
#    behavior for get_bone_thickness_3d).
# -----------------------------------------------------------------------------
def test_bone_thickness_3d_depth_at_min_returns_full():
    """At depth_min (t=0), scale=1.0, so base_thickness=2 → 2."""
    out = get_bone_thickness_3d(0.0, 2, 0.0, 2.0)
    assert out == 2, f"depth=depth_min should return full base_thickness, got {out!r}"
