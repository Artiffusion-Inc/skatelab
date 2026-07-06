"""RED repro — `PhysicsEngine.analyze_2d` (2D physics path, common no-3D-lift
case) divides by `fps` in THREE places with no fps=0 guard:

    flight_time = flight_frames / fps        # line 621
    dt = 1.0 / fps                            # line 641 (inside `if takeoff_idx > 0`)
    t_flight = np.arange(flight_frames) / fps # line 649 (np.polyfit)

Corrupt / truncated video reports `cv2.CAP_PROP_FPS = 0` (OpenCV sentinel
for unknown framerate). `meta.fps = 0.0` flows into `analyze_2d(..., fps=
0.0)` → `flight_frames / 0.0` → ZeroDivisionError (Python scalar /0.0
raises). Worker job crashes on the 2D physics path — same fps=0 failure
family as #937 (3D sibling, fixed), #952 (pose tracker), #948 (smoothing),
phase_detector:234 (already guarded).

`analyze_2d` is the common path: when 3D lift is disabled (default —
CorrectiveLens is off), 2D CoM parabolic fit is how jump height / flight
time are computed. So fps=0 crashes the no-3D-lift case that most sessions
use.

The 3D sibling `_fit_jump_trajectory_with_com` / `fit_jump_trajectory`
(#937) guard `fps <= 0` at the top, returning a zero-dict. `analyze_2d`
returns a dict whose non-fps fields (`jump_height`, `flight_time`,
`takeoff_velocity`, `fit_quality`) default to `None` (lines 609-612) and
are only set inside the `if takeoff_idx is not None and landing_idx is not
None:` block. So the natural fps<=0 contract here: skip the jump-physics
block entirely (leave the four fields `None`) — degrade to "unknown jump
metrics", not crash. `avg_inertia` stays `None` (2D has no inertia).

The fix (NOT applied — repro only): guard `fps <= 0` at the top of the
`if takeoff_idx is not None and landing_idx is not None:` block (line 614)
and skip the block — return the all-None dict early. Mirrors #937's
"guard before any /fps" pattern, but here the graceful result is `None`
(the existing default), not a zero-dict, because the 2D method's contract
already treats "no phases" as `None`. Smallest diff: one `if fps <= 0:`
early-return-of-block, covers all three `/fps` sites below it.

The correct contract: a corrupt video (fps=0) must NOT crash the 2D
physics engine. `analyze_2d(..., fps=0.0)` with takeoff/landing given must
return a dict with `jump_height`/`flight_time`/`takeoff_velocity`/
`fit_quality` = `None` (graceful "unknown"), NOT raise ZeroDivisionError.

RED now: the observable assertions below describe the CORRECT behavior —
fps=0 with takeoff/landing returns None fields, no crash. They FAIL because
`flight_frames / 0.0` raises. The source-check confirms the `fps <= 0` guard
is present in `analyze_2d` (root cause locked).

Pure-Python (no GPU, no DB): `analyze_2d` is a pure-data function over a
2D poses array and a 2D CoM trajectory.
"""

import inspect

import numpy as np

from src.analysis.physics_engine import PhysicsEngine
from src.types import H36Key


def _flight_pose_2d(n: int = 12) -> np.ndarray:
    """A 12-frame 2D pose sequence with a parabolic flight arc — CoM rises
    (Y decreases) during flight (frames 2..7) via `Y -= 0.02*(f-2)*(7-f)`,
    so the all-valid `jump_height` at fps=30 is finite nonzero. `analyze_2d`
    uses 2D CoM (`calculate_com_trajectory_2d`), not the 3D CoM.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.HEAD] = [0.0, 0.0]
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.1]
        poses[f, H36Key.RSHOULDER] = [0.2, 0.1]
        poses[f, H36Key.LHIP] = [-0.1, 0.5]
        poses[f, H36Key.RHIP] = [0.1, 0.5]
        poses[f, H36Key.LKNEE] = [-0.1, 0.9]
        poses[f, H36Key.RKNEE] = [0.1, 0.9]
        poses[f, H36Key.LFOOT] = [-0.1, 1.0]
        poses[f, H36Key.RFOOT] = [0.1, 1.0]
    for f in range(2, 8):
        poses[f, :, 1] -= 0.02 * (f - 2) * (7 - f)
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: `analyze_2d(fps=0.0)` with takeoff/landing — no crash, None
# jump metrics (graceful "unknown"), not ZeroDivisionError.
# --------------------------------------------------------------------------- #


def test_analyze_2d_fps_zero_no_crash_repro():
    """CORRECT behavior: `analyze_2d(poses, takeoff_idx=2, landing_idx=7,
    fps=0.0)` must return a dict with `jump_height`/`flight_time`/
    `takeoff_velocity`/`fit_quality` = `None` (graceful "unknown jump
    metrics"), NOT raise ZeroDivisionError.

    RED now: `flight_frames / 0.0` (line 621) raises ZeroDivisionError before
    any field is set. After the fix: the `fps <= 0` guard skips the
    jump-physics block, leaving the four fields at their `None` default.
    """
    engine = PhysicsEngine()
    poses = _flight_pose_2d()

    r = engine.analyze_2d(poses, takeoff_idx=2, landing_idx=7, fps=0.0)

    assert isinstance(r, dict), (
        f"BUG: analyze_2d(fps=0.0) did not return a dict (got "
        f"{type(r).__name__}: {r!r}). Corrupt video reports fps=0 "
        f"(cv2.CAP_PROP_FPS sentinel); the method must degrade gracefully."
    )
    # fps=0 → cannot compute frame→time → jump metrics unknown, not crash.
    for key in ("jump_height", "flight_time", "takeoff_velocity", "fit_quality"):
        assert key in r, f"BUG: missing key {key!r} in fps=0 result {r!r}."
        assert r[key] is None, (
            f"BUG: analyze_2d(fps=0.0) set {key}={r[key]!r}, expected None "
            f"(graceful unknown). fps=0 → flight_frames/fps ZeroDivisionError "
            f"today; guard must skip the jump-physics block (fields stay None)."
        )
    # avg_inertia is None for 2D regardless of fps.
    assert r["avg_inertia"] is None, (
        f"BUG: analyze_2d avg_inertia should be None for 2D, got {r['avg_inertia']!r}."
    )


# --------------------------------------------------------------------------- #
# Observable 2: no phases (takeoff/landing=None) — fps irrelevant, no crash.
# Locks the existing "no phases → None fields" contract (fps=0 must not
# regress it).
# --------------------------------------------------------------------------- #


def test_analyze_2d_fps_zero_no_phases_none_fields_repro():
    """CORRECT behavior: `analyze_2d(poses, takeoff_idx=None,
    landing_idx=None, fps=0.0)` must return None jump metrics — the
    `if takeoff_idx is not None and landing_idx is not None:` block is
    skipped, so the fps<=0 guard inside it is never reached. This PASSES
    today (the block is skipped); it locks the no-phases contract so the
    fps<=0 guard cannot regress it.
    """
    engine = PhysicsEngine()
    r = engine.analyze_2d(_flight_pose_2d(), takeoff_idx=None, landing_idx=None, fps=0.0)
    assert r["jump_height"] is None and r["flight_time"] is None, (
        f"BUG: no-phases analyze_2d should return None jump metrics, got {r!r}."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid fps unchanged — fps=30 with phases reports
# finite jump_height.
# --------------------------------------------------------------------------- #


def test_analyze_2d_valid_fps_unchanged_repro():
    """Regression guard: an all-valid parabolic flight at fps=30 with
    takeoff/landing must still report a finite `jump_height`. The fps<=0
    guard must not change the valid-fps case. PASSES today; locks the
    contract so the guard cannot regress the normal path.
    """
    engine = PhysicsEngine()
    r = engine.analyze_2d(_flight_pose_2d(), takeoff_idx=2, landing_idx=7, fps=30.0)
    assert r["jump_height"] is not None and np.isfinite(r["jump_height"]), (
        f"BUG (regression): all-valid fps=30 flight reported jump_height "
        f"{r['jump_height']}, expected finite. The fps<=0 guard must not "
        f"change the valid-fps case."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `fps <= 0` guard present in analyze_2d
# before the first /fps.
# --------------------------------------------------------------------------- #


def test_analyze_2d_fps_zero_guard_source_repro():
    """GREEN contract source check: the fps=0 crash is fixed by a
    `fps <= 0` guard in `analyze_2d`, before the first `/fps` (line 621
    `flight_frames / fps`). When fps<=0 the jump-physics block is skipped
    (fields stay None), mirroring the #937 "guard before any /fps" pattern.
    """
    src = inspect.getsource(PhysicsEngine.analyze_2d)
    assert "fps <= 0" in src, (
        "BUG: analyze_2d must guard `fps <= 0` before the first `/fps` "
        "(flight_frames/fps). Corrupt video reports fps=0 → "
        "ZeroDivisionError today. Mirror #937: skip the jump-physics block "
        "(fields stay None) when fps<=0."
    )
