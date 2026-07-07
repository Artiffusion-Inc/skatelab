"""RED repro — `PhysicsEngine.analyze_2d` (2D physics path) divides by `fps`
in THREE places. The existing guard `fps <= 0` (line 625) catches zero /
negative fps, but NOT NaN: `NaN <= 0` is `False`, so NaN falls through and
`flight_frames / NaN` → NaN, `1.0 / NaN` → NaN, `np.arange / NaN` → NaN.
`fit_quality` silently becomes `0.0` because `NaN > 0` is `False` (BUG 3,
silent NaN->0). Result: 3 dict fields contaminated with NaN — breaks
recommender / JSON serialization / DB persistence.

Repro values (issue #1064):
    fps=30.0: {flight_time: 0.7, takeoff_velocity: 0.45, fit_quality: 0.71}
    fps=NaN:  {flight_time: NaN, takeoff_velocity: NaN, fit_quality: 0.0}

Family: tranche FW — same NaN-bypass family as FO/FP/FQ/FR/FS/FT/FU/FV.
Sibling: `analyze_2d` is the 2D path; the 3D sibling (`fit_jump_trajectory`)
has its own NaN-coord guards (#937/883 family), but the 2D NaN-fps path is
uncovered.

Fix (NOT applied — repro only): at function entry, guard
`math.isfinite(fps) and fps > 0` — same pattern as PR #1043/#1044 (sibling
fps-guard fixes). When fps is not finite or not positive, return the
all-None dict (graceful "unknown jump metrics"), mirroring the existing
`fps <= 0` early-return-of-block contract.

Pure-Python (no GPU, no DB): `analyze_2d` is a pure-data function over a
2D poses array and a 2D CoM trajectory.
"""

import inspect
import math

import numpy as np

from src.analysis.physics_engine import PhysicsEngine
from src.types import H36Key


def _flight_pose_2d(n: int = 12) -> np.ndarray:
    """12-frame 2D pose sequence with parabolic flight (Y down). Frames 2..7
    are the flight arc; the rest is flat stance. Used for valid-fps baseline.
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
# Observable 1 (BUG 1): NaN fps → flight_time = NaN. The first /fps site
# (`flight_frames / fps` at line 639) propagates NaN into the returned dict.
# --------------------------------------------------------------------------- #


def test_analyze_2d_nan_fps_flight_time_no_nan_repro():
    """CORRECT behavior: `analyze_2d(poses, takeoff_idx=2, landing_idx=7,
    fps=NaN)` must NOT leak NaN into `flight_time`. fps=NaN is a corrupt /
    missing-framerate sentinel; the method must return `flight_time=None`
    (graceful "unknown"), NOT a NaN that contaminates the recommender /
    JSON output.

    RED now: `flight_frames / NaN` = NaN (Python float, not 0-divide
    exception). The existing `fps <= 0` guard does NOT catch NaN
    (`NaN <= 0` is False). NaN falls through into the return dict.
    """
    engine = PhysicsEngine()
    r = engine.analyze_2d(_flight_pose_2d(), takeoff_idx=2, landing_idx=7, fps=float("nan"))

    assert "flight_time" in r, f"BUG: missing 'flight_time' in result {r!r}."
    assert r["flight_time"] is None or (
        isinstance(r["flight_time"], (int, float)) and math.isfinite(r["flight_time"])
    ), (
        f"BUG: analyze_2d(fps=NaN) leaked NaN into flight_time="
        f"{r['flight_time']!r}. fps=NaN must yield None or finite (graceful "
        f"unknown), never NaN — NaN poisons JSON / DB / recommender."
    )


# --------------------------------------------------------------------------- #
# Observable 2 (BUG 2): NaN fps → takeoff_velocity = NaN. The second /fps
# site (`dt = 1.0 / fps` at line 659) propagates NaN. The `isfinite` guard
# on the diff catches NaN only at the assignment, but the current code
# DOES already guard the diff itself — so this site is actually protected
# by the `np.isfinite(takeoff_velocity_y) else 0.0` clause. BUG 2 is
# observable only if the guard is removed. Lock the diff NaN-protection.
# --------------------------------------------------------------------------- #


def test_analyze_2d_nan_fps_takeoff_velocity_finite_repro():
    """CORRECT behavior: `analyze_2d(poses, takeoff_idx=2, landing_idx=7,
    fps=NaN)` must NOT leak NaN into `takeoff_velocity`. Existing #883
    NaN-diff guard (`np.isfinite(takeoff_velocity_y) else 0.0`) keeps this
    finite, but the contract must hold — NaN fps must yield finite
    (preferably None) takeoff_velocity, never NaN.
    """
    engine = PhysicsEngine()
    r = engine.analyze_2d(_flight_pose_2d(), takeoff_idx=2, landing_idx=7, fps=float("nan"))

    assert "takeoff_velocity" in r, f"BUG: missing 'takeoff_velocity' in result {r!r}."
    tv = r["takeoff_velocity"]
    assert tv is None or (isinstance(tv, (int, float)) and math.isfinite(tv)), (
        f"BUG: analyze_2d(fps=NaN) leaked NaN into takeoff_velocity="
        f"{tv!r}. Existing #883 diff-guard should keep this finite, but the "
        f"contract is: NaN fps must never poison the return dict."
    )


# --------------------------------------------------------------------------- #
# Observable 3 (BUG 3, silent): NaN fps → fit_quality = 0.0 (silent NaN->0).
# The `ss_tot > 0` clause is NaN-blind: `NaN > 0` is False → fit_quality=0.0.
# A 0 fit_quality for an OTHERWISE valid flight arc is silently misleading.
# --------------------------------------------------------------------------- #


def test_analyze_2d_nan_fps_fit_quality_no_silent_zero_repro():
    """CORRECT behavior: `analyze_2d(poses, takeoff_idx=2, landing_idx=7,
    fps=NaN)` must NOT silently coerce NaN→0 for `fit_quality`. The
    `if ss_tot > 0` clause is NaN-blind: `NaN > 0` is `False`, so a
    NaN-fps input drops fit_quality to a misleading 0.0 (looks
    like a "bad fit" for an OTHERWISE valid arc). The method must return
    None (graceful "unknown fit") when fps is non-finite or non-positive.

    RED now: `np.polyfit(NaN_array, finite_y, 2)` raises LinAlgError, the
    `except` fallback emits `fit_quality = 0.0` — silently wrong.
    """
    engine = PhysicsEngine()
    r = engine.analyze_2d(_flight_pose_2d(), takeoff_idx=2, landing_idx=7, fps=float("nan"))

    assert "fit_quality" in r, f"BUG: missing 'fit_quality' in result {r!r}."
    fq = r["fit_quality"]
    # The contract: NaN fps → None (graceful unknown). A 0.0 here would
    # mean "terrible fit" downstream — silently wrong.
    assert fq is None, (
        f"BUG: analyze_2d(fps=NaN) yielded fit_quality={fq!r}. NaN fps must "
        f"yield None (graceful unknown) — silently emitting 0.0 makes a "
        f"missing-framerate video look like a perfect-parabola misfit."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid fps=30 with phases still reports finite,
# nonzero flight_time, takeoff_velocity, fit_quality. Locks the normal path.
# --------------------------------------------------------------------------- #


def test_analyze_2d_valid_fps_finite_nonzero_repro():
    """Regression guard: an all-valid parabolic flight at fps=30 with
    takeoff/landing must still report finite, > 0 `flight_time`,
    `takeoff_velocity`, and `fit_quality`. The NaN-fps guard must not
    change the valid-fps case.
    """
    engine = PhysicsEngine()
    r = engine.analyze_2d(_flight_pose_2d(), takeoff_idx=2, landing_idx=7, fps=30.0)

    assert r["flight_time"] is not None and math.isfinite(r["flight_time"]), (
        f"BUG (regression): all-valid fps=30 flight reported flight_time="
        f"{r['flight_time']!r}, expected finite. The NaN-fps guard must not "
        f"change the valid-fps case."
    )
    assert r["flight_time"] > 0, (
        f"BUG (regression): valid fps=30 reported flight_time="
        f"{r['flight_time']!r} (not > 0). Expected positive seconds."
    )
    assert r["takeoff_velocity"] is not None and math.isfinite(r["takeoff_velocity"]), (
        f"BUG (regression): all-valid fps=30 flight reported takeoff_velocity="
        f"{r['takeoff_velocity']!r}, expected finite."
    )
    assert r["fit_quality"] is not None and math.isfinite(r["fit_quality"]), (
        f"BUG (regression): all-valid fps=30 flight reported fit_quality="
        f"{r['fit_quality']!r}, expected finite. The NaN-fps guard must not "
        f"regress the valid-fps case."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `math.isfinite(fps)` guard present at
# the top of `analyze_2d`, before the first /fps. Confirms the contract that
# NaN fps is treated as "unknown framerate" and yields graceful None.
# --------------------------------------------------------------------------- #


def test_analyze_2d_nan_fps_guard_source_repro():
    """GREEN contract source check: the NaN-fps leak is fixed by adding a
    `math.isfinite(fps) and fps > 0` guard at the top of `analyze_2d`,
    before the first `/fps` (`flight_frames / fps` at line 639). The
    existing `fps <= 0` guard is necessary but not sufficient — it does
    NOT catch NaN (`NaN <= 0` is False). Mirror PR #1043/#1044 pattern.
    """
    src = inspect.getsource(PhysicsEngine.analyze_2d)
    assert "math.isfinite" in src, (
        "BUG: analyze_2d must guard `math.isfinite(fps) and fps > 0` "
        "before the first `/fps`. The existing `fps <= 0` guard is "
        "NaN-blind (NaN <= 0 is False), so NaN fps propagates to "
        "flight_time, takeoff_velocity, and silently coerces fit_quality "
        "to 0.0. Mirror PR #1043/#1044 sibling pattern."
    )
