"""RED repro — `PhysicsEngine._fit_jump_trajectory_with_com` (3D jump-height
path, called by `analyze`) divides by `fps` in FIVE places with no fps=0 guard:

    t = np.arange(n_frames) / fps          # line 370 (#423: was / 30.0)
    flight_time = t[-1] - t[0]             # derived from t (all-zero when fps=0)
    "flight_time": n_frames / fps          # line 418 except-fallback
    # sibling fit_jump_trajectory (line 461, 509) — same /fps, same bug

Corrupt / truncated video reports `cv2.CAP_PROP_FPS = 0` (OpenCV sentinel
for unknown framerate). `meta.fps = 0.0` flows into `PhysicsEngine.analyze`
→ `_fit_jump_trajectory_with_com(..., fps=0.0)` → `np.arange(n) / 0.0` =
`ZeroDivisionError` (Python float division by 0.0 raises; numpy would emit
inf/nan but the FIRST `/fps` here is `np.arange(n_frames) / fps` where the
array-div-scalar path produces inf, then `curve_fit` on inf → `t_peak =
-b/(2a)` may be inf/nan, `parabola` returns nan, `jump_height = nan`,
`flight_time = t[-1]-t[0] = inf - inf = nan`). At minimum the fallback
`n_frames / fps` (line 418) is a hard `ZeroDivisionError` if `curve_fit`
raises (e.g. degenerate flight). Worker job crashes at the physics stage,
session marked failed — same failure family as #952 / #948 (fps=0
ZeroDivision in pose tracker / smoothing).

The phase-detector sibling (`phase_detector.py:234`) already guards fps=0,
the pose-tracker sibling (#952) falls back to dt=1.0, the smoothing kernel
(#948) falls back to dt=1.0. The physics engine is the unguarded sibling.

The fix (NOT applied — repro only): guard `fps <= 0` at the top of
`_fit_jump_trajectory_with_com` AND `fit_jump_trajectory`, mirroring the
existing `takeoff_idx > landing_idx` degenerate guard (line 360-366):
    if fps <= 0:
        return {"height": 0.0, "flight_time": 0.0,
                "takeoff_velocity": 0.0, "fit_quality": 0.0}
AND/OR guard the fallback division: `n_frames / fps if fps > 0 else 0.0`.
The top-of-method guard is the root-cause fix (one place per method, covers
every `/fps` site below it) — smallest diff, mirrors the existing degenerate
guard, returns the same zero-dict shape callers already expect from the
`takeoff_idx > landing_idx` path.

The correct contract: a corrupt video (fps=0) must NOT crash the physics
engine. `_fit_jump_trajectory_with_com(fps=0.0)` and `fit_jump_trajectory(
fps=0.0)` must return a finite zero-dict (graceful degradation, mirror the
degenerate-phase guard), NOT raise ZeroDivisionError and NOT leak inf/nan
into `height`/`flight_time`. `analyze(fps=0.0)` must not crash either — it
delegates to `_fit_jump_trajectory_with_com`.

RED now: the observable assertions below describe the CORRECT behavior —
fps=0 returns a finite zero-dict, no crash, no inf/nan. They FAIL because
`np.arange(n) / 0.0` → inf → curve_fit on inf → fallback `n_frames / 0.0`
→ ZeroDivisionError (or nan/inf leak). After the fix: the top-of-method
guard returns zeros before any `/fps`. The source-check test confirms the
`fps <= 0` guard is present in both methods (root cause locked).

Pure-Python (no GPU, no DB): `_fit_jump_trajectory_with_com`,
`fit_jump_trajectory`, and `analyze` are pure-data functions over a poses
array and a pre-computed CoM trajectory.
"""

import inspect

import numpy as np

from src.analysis.physics_engine import PhysicsEngine
from src.types import H36Key


def _flight_pose_3d(n: int = 12) -> np.ndarray:
    """A 12-frame 3D pose sequence with a parabolic flight arc — CoM rises
    (Y decreases) during flight (frames 2..7) via `Y -= 0.02*(f-2)*(7-f)`,
    so the all-valid `height` from the parabola fit at fps=30 is finite
    nonzero (~0.125 m). Used by `fit_jump_trajectory` (computes its own CoM)
    and `analyze` (computes CoM then delegates to `_fit_jump_trajectory_with_com`).
    """
    poses = np.zeros((n, 17, 3), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.HEAD] = [0.0, 0.0, 0.0]
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.1, 0.0]
        poses[f, H36Key.RSHOULDER] = [0.2, 0.1, 0.0]
        poses[f, H36Key.LHIP] = [-0.1, 0.5, 0.0]
        poses[f, H36Key.RHIP] = [0.1, 0.5, 0.0]
        poses[f, H36Key.LKNEE] = [-0.1, 0.9, 0.0]
        poses[f, H36Key.RKNEE] = [0.1, 0.9, 0.0]
        poses[f, H36Key.LFOOT] = [-0.1, 1.0, 0.0]
        poses[f, H36Key.RFOOT] = [0.1, 1.0, 0.0]
    for f in range(2, 8):
        poses[f, :, 1] -= 0.02 * (f - 2) * (7 - f)
    return poses


def _com_trajectory(poses_3d: np.ndarray) -> np.ndarray:
    """Pre-computed CoM for `_fit_jump_trajectory_with_com` (which takes a
    CoM arg, unlike `fit_jump_trajectory` which computes its own)."""
    return PhysicsEngine().calculate_center_of_mass(poses_3d)


# --------------------------------------------------------------------------- #
# Observable 1: `_fit_jump_trajectory_with_com(fps=0.0)` — no crash, finite
# zero-dict. Corrupt video → meta.fps=0 → ZeroDivisionError today.
# --------------------------------------------------------------------------- #


def test_fit_jump_trajectory_with_com_fps_zero_no_crash_repro():
    """CORRECT behavior: `_fit_jump_trajectory_with_com(..., fps=0.0)` must
    return a finite zero-dict (height=0, flight_time=0, takeoff_velocity=0,
    fit_quality=0), NOT raise ZeroDivisionError and NOT leak inf/nan.

    RED now: `np.arange(n_frames) / 0.0` → inf array → `curve_fit` on inf
    data → either raises or returns inf/nan params → `t_peak=-b/(2a)` =
    nan, `jump_height=nan`, `flight_time=inf-inf=nan`; if curve_fit raises
    the except-fallback hits `n_frames / 0.0` → ZeroDivisionError. Either
    way the method does not return a finite zero-dict. After the fix: the
    top-of-method `fps <= 0` guard returns zeros before any `/fps`.
    """
    engine = PhysicsEngine()
    poses = _flight_pose_3d()
    com = _com_trajectory(poses)

    r = engine._fit_jump_trajectory_with_com(poses, 2, 7, com, fps=0.0)

    assert isinstance(r, dict), (
        f"BUG: _fit_jump_trajectory_with_com(fps=0.0) did not return a dict "
        f"(got {type(r).__name__}: {r!r}). Corrupt video reports fps=0 "
        f"(cv2.CAP_PROP_FPS sentinel); the method must degrade gracefully."
    )
    for key in ("height", "flight_time", "takeoff_velocity", "fit_quality"):
        assert key in r, f"BUG: missing key {key!r} in fps=0 result {r!r}."
        assert np.isfinite(r[key]), (
            f"BUG: _fit_jump_trajectory_with_com(fps=0.0) leaked non-finite "
            f"{key}={r[key]!r}. np.arange(n)/0.0=inf → curve_fit on inf → "
            f"nan/inf in derived values, or except-fallback n_frames/0.0 → "
            f"ZeroDivisionError. fps=0 (corrupt video) must return finite "
            f"zeros, mirroring the takeoff>landing degenerate guard."
        )


# --------------------------------------------------------------------------- #
# Observable 2: `analyze(fps=0.0)` — the public 3D entry point delegates to
# `_fit_jump_trajectory_with_com`; must not crash when takeoff/landing given.
# --------------------------------------------------------------------------- #


def test_analyze_fps_zero_no_crash_repro():
    """CORRECT behavior: `PhysicsEngine.analyze(poses, takeoff_idx=2,
    landing_idx=7, fps=0.0)` must not raise and must produce a finite
    `jump_height` / `flight_time` (None or 0.0, not nan/inf).

    RED now: analyze delegates to `_fit_jump_trajectory_with_com(..., fps=
    0.0)` which divides by fps → ZeroDivisionError / nan leak propagates
    into PhysicsResult.jump_height / flight_time. After the fix: the guard
    in `_fit_jump_trajectory_with_com` returns zeros, analyze packs them
    into PhysicsResult.
    """
    engine = PhysicsEngine()
    poses = _flight_pose_3d()

    result = engine.analyze(poses, takeoff_idx=2, landing_idx=7, fps=0.0)

    assert result.jump_height is None or np.isfinite(result.jump_height), (
        f"BUG: analyze(fps=0.0) produced non-finite jump_height "
        f"{result.jump_height!r}. Delegates to "
        f"_fit_jump_trajectory_with_com(fps=0.0) which divides by fps."
    )
    assert result.flight_time is None or np.isfinite(result.flight_time), (
        f"BUG: analyze(fps=0.0) produced non-finite flight_time {result.flight_time!r}."
    )


# --------------------------------------------------------------------------- #
# Observable 3: sibling `fit_jump_trajectory(fps=0.0)` — same /fps bug, same
# guard needed. Root-cause fix covers BOTH 3D trajectory-fit methods.
# --------------------------------------------------------------------------- #


def test_fit_jump_trajectory_fps_zero_no_crash_repro():
    """CORRECT behavior: the sibling `fit_jump_trajectory(..., fps=0.0)`
    (public method, computes its own CoM) must also return a finite
    zero-dict, NOT raise / leak inf/nan. It has the same `np.arange(n)/fps`
    (line 461) and `n_frames/fps` fallback (line 509).

    RED now: same as observable 1. After the fix: top-of-method `fps <= 0`
    guard, mirroring its existing `takeoff_idx > landing_idx` guard.
    """
    engine = PhysicsEngine()
    poses = _flight_pose_3d()

    r = engine.fit_jump_trajectory(poses, 2, 7, fps=0.0)

    assert isinstance(r, dict), (
        f"BUG: fit_jump_trajectory(fps=0.0) did not return a dict (got {type(r).__name__}: {r!r})."
    )
    for key in ("height", "flight_time", "takeoff_velocity", "fit_quality"):
        assert key in r, f"BUG: missing key {key!r} in fps=0 result {r!r}."
        assert np.isfinite(r[key]), (
            f"BUG: fit_jump_trajectory(fps=0.0) leaked non-finite "
            f"{key}={r[key]!r}. Same /fps bug as "
            f"_fit_jump_trajectory_with_com; same guard needed."
        )


# --------------------------------------------------------------------------- #
# Regression guard: valid fps unchanged — fps=30 still reports finite,
# nonzero height.
# --------------------------------------------------------------------------- #


def test_fit_jump_trajectory_valid_fps_unchanged_repro():
    """Regression guard: an all-valid parabolic flight at fps=30 must still
    report a finite, nonzero `height`. The fps<=0 guard must not change the
    valid-fps case. PASSES today; locks the contract so the guard cannot
    regress the normal path.
    """
    engine = PhysicsEngine()
    r = engine.fit_jump_trajectory(_flight_pose_3d(), 2, 7, fps=30.0)
    assert np.isfinite(r["height"]) and r["height"] > 0.0, (
        f"BUG (regression): all-valid fps=30 flight reported height "
        f"{r['height']}, expected finite > 0. The fps<=0 guard must not "
        f"change the valid-fps case."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `fps <= 0` guard present in both 3D
# trajectory-fit methods.
# --------------------------------------------------------------------------- #


def test_fit_jump_fps_zero_guard_source_repro():
    """GREEN contract source check: the fps=0 crash is fixed by a
    top-of-method `fps <= 0` guard in BOTH `_fit_jump_trajectory_with_com`
    and `fit_jump_trajectory`, mirroring the existing
    `takeoff_idx > landing_idx` degenerate-phase guard (which returns the
    same zero-dict shape). One guard per method covers every `/fps` site
    below it — root-cause fix, smallest diff.
    """
    for method in (
        PhysicsEngine._fit_jump_trajectory_with_com,
        PhysicsEngine.fit_jump_trajectory,
    ):
        src = inspect.getsource(method)
        assert "fps <= 0" in src, (
            f"BUG: {method.__name__} must guard `fps <= 0` at the top "
            f"(return the zero-dict, mirroring the takeoff>landing "
            f"degenerate guard) before any `/fps` division. Corrupt video "
            f"reports fps=0 → ZeroDivisionError / inf/nan leak today."
        )
