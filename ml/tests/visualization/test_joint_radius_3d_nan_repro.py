"""RED repro — `get_joint_radius_3d` / `get_bone_thickness_3d` NaN-depth
bound silently coerces to 0.5 (tranche GA).

Bug: ml/src/visualization/skeleton/joints.py has

    t = (depth - depth_min) / (depth_max - depth_min) if depth_max > depth_min else 0.5

NaN depth_min / depth_max silently propagates through `>` comparison
because `NaN > x` is False for any x, so the else branch picks t=0.5:

    NaN depth_max  →  NaN > depth_min is False  →  t = 0.5  (silent)
    NaN depth_min  →  NaN > NaN     is False    →  t = 0.5  (silent)
    depth_max == depth_min  →  t = 0.5  (degenerate, same as NaN)

All three cases return the SAME radius/thickness — INDISTINGUISHABLE
for the caller, so upstream bugs (bad 3D lift, missing depth stats)
silently flatten the entire 3D skeleton to a single mid-depth
render instead of surfacing as a failure.

Concretely (base_radius=4, line_width=2, base_thickness=2):

    get_joint_radius_3d(1.0, 4, 0.0, 10.0) → 3  (correct: t=0.1, scale=0.95, int(4*0.95)=3)
    get_joint_radius_3d(1.0, 4, 0.0,  NaN) → 3  (BUG: silent t=0.5)
    get_joint_radius_3d(1.0, 4,  NaN,10.0) → 3  (BUG: silent t=0.5)
    get_joint_radius_3d(1.0, 4, 0.0,  0.0) → 3  (degenerate, same as NaN)
    get_joint_radius_3d(NaN, 4, 0.0, 10.0) → 2  (depth=NaN pre-coerced to mid)

    get_bone_thickness_3d(1.0, 2, 0.0,  NaN) → 1  (BUG: silent t=0.5)
    get_bone_thickness_3d(1.0, 2,  NaN,10.0) → 1  (BUG: silent t=0.5)

Prod impact: 3D skeleton render (`draw_skeleton_3d` in
`ml/src/visualization/skeleton/drawer.py:258,273`) calls both per
joint/bone. NaN depth bounds silently render the whole skeleton at
medium depth (no depth perception). User sees a flat skeleton
without any error, masking the upstream 3D-pose / depth-stats bug.

Fix (NOT applied — repro only): guard depth_min and depth_max with
`math.isfinite(...)` and require `depth_max > depth_min` (not
`>=`, since equal bounds are also degenerate), raising `ValueError`
at the trust boundary so upstream bugs surface instead of being
hidden by a uniform flat-render.

Methodology (per audit reglement):
- Each test names ONE observable bug behavior.
- Includes source-check via `inspect.getsource` to lock down the
  `math.isfinite` guard so a regression to the silent-0.5 ternary
  fails the suite (the original code had `if depth_max > depth_min`,
  not a finite-check — a naïve revert would pass the behavioral
  tests if the NaN-coercion still produced a "valid" int).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

# Add ml/src to sys.path so we can import the real `src` package without
# polluting sys.modules with stubs (which would break sibling test
# collection in the same pytest invocation).
_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from src.visualization.skeleton.joints import (  # noqa: E402
    get_bone_thickness_3d,
    get_joint_radius_3d,
)

NAN = float("nan")


# -----------------------------------------------------------------------------
# 1. Behavioral: NaN depth_max must raise (currently silently returns)
# -----------------------------------------------------------------------------
def test_joint_radius_3d_nan_depth_max_raises():
    """NaN depth_max is a contract violation — must raise, not silently
    collapse to t=0.5. Otherwise an upstream 3D-pose failure renders
    the entire skeleton at a uniform mid-depth with no visible error.
    """
    try:
        out = get_joint_radius_3d(1.0, 4, 0.0, NAN)
    except ValueError:
        return
    raise AssertionError(
        f"NaN depth_max must raise ValueError, got silent return {out!r} "
        f"(t collapsed to 0.5; upstream depth-stats bug hidden)"
    )


# -----------------------------------------------------------------------------
# 2. Behavioral: NaN depth_min must raise
# -----------------------------------------------------------------------------
def test_joint_radius_3d_nan_depth_min_raises():
    """NaN depth_min is a contract violation — must raise, not silently
    collapse to t=0.5 (NaN > NaN is False → else branch picked).
    """
    try:
        out = get_joint_radius_3d(1.0, 4, NAN, 10.0)
    except ValueError:
        return
    raise AssertionError(
        f"NaN depth_min must raise ValueError, got silent return {out!r} "
        f"(t collapsed to 0.5; upstream depth-stats bug hidden)"
    )


# -----------------------------------------------------------------------------
# 3. Behavioral: bone_thickness_3d NaN bound must raise too
# -----------------------------------------------------------------------------
def test_bone_thickness_3d_nan_depth_max_raises():
    """Same bug in get_bone_thickness_3d. Caller cannot tell apart
    'bones at uniform medium thickness' from 'real bones'.
    """
    try:
        out = get_bone_thickness_3d(1.0, 2, 0.0, NAN)
    except ValueError:
        return
    raise AssertionError(f"NaN depth_max must raise ValueError, got silent return {out!r}")


# -----------------------------------------------------------------------------
# 4. Regression: valid finite bounds must keep working
# -----------------------------------------------------------------------------
def test_joint_radius_3d_valid_finite_unchanged():
    """Sanity: a normal call (depth=1.0, bounds 0..10) must keep returning
    the pre-fix value 3 (t=0.1, scale=0.95, int(4*0.95)=3). Locks down
    that the fix doesn't regress the happy path.
    """
    out = get_joint_radius_3d(1.0, 4, 0.0, 10.0)
    assert out == 3, f"valid call regressed: expected 3, got {out!r}"


# -----------------------------------------------------------------------------
# 5. Source check: locks down `math.isfinite` guard so a future revert
#    to the silent-0.5 ternary fails the suite, even if the behavioral
#    tests are somehow worked around.
# -----------------------------------------------------------------------------
def test_joint_radius_3d_source_has_isfinite_guard():
    """Locks down the fix: the function must contain a `math.isfinite`
    guard for depth_min/depth_max. A naïve revert to
    `if depth_max > depth_min else 0.5` would pass the behavioral tests
    only if NaN coercion were removed; this test catches the case where
    the silent-0.5 ternary returns (correcting the symptom of the original
    bug) but the underlying finite check is gone.
    """
    src = inspect.getsource(get_joint_radius_3d)
    assert "math.isfinite" in src, (
        "get_joint_radius_3d must guard depth_min/depth_max with "
        "math.isfinite — NaN must not silently coerce to t=0.5. "
        "Source snippet:\n" + src
    )
