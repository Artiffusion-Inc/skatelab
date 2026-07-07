"""RED repro — `PhysicsEngine.fit_jump_trajectory` and
`PhysicsEngine._fit_jump_trajectory_with_com` (3D physics paths) divide
by `fps` in the parabolic-fit and fallback paths. The existing guard
`fps <= 0` (lines 379 / 479) catches zero / negative fps, but NOT NaN:
`NaN <= 0` is `False`, so NaN falls through.

Inside the try-block, `t = np.arange(n_frames) / fps` becomes all-NaN,
`ss_tot` becomes NaN, and the NaN-blind clause `ss_tot > 0` is `False`,
so `r_squared = 0` — silent NaN→0 (BUG 1). In the except-fallback
path, `flight_time = n_frames / fps` becomes NaN (BUG 2). `analyze()`
calls `_fit_jump_trajectory_with_com` directly with no inner fps guard,
so the NaN leaks to the top-level `PhysicsResult.flight_time` field
(BUG 3).

PR #1131 / #1064 fixed the 2D sibling `analyze_2d` (line 629). This
file targets the 3D sibling — the same NaN-bypass family, in two
functions that PR 1131 did not touch.

Repro values (issue #1062):
    fps=30.0: {flight_time: 0.167, fit_quality: 0.9999}
    fps=NaN:  {flight_time: NaN,  fit_quality: 0.0}

Fix (NOT applied — repro only): at function entry of BOTH
`_fit_jump_trajectory_with_com` and `fit_jump_trajectory`, guard
`math.isfinite(fps) and fps > 0` — same pattern as PR #1043/#1044/
#1131 sibling fps-guard fixes. When fps is non-finite or non-positive,
return the all-zeros dict (mirroring the existing `fps <= 0` early
return contract).

Pure-Python (no GPU, no DB): these are pure-data functions over a
3D poses array and a 3D CoM trajectory.
"""

import inspect
import math

import numpy as np

from src.analysis.physics_engine import PhysicsEngine


def _flight_pose_3d(n: int = 12) -> np.ndarray:
    """12-frame 3D pose sequence with parabolic flight arc in Y.
    Frames 2..7 are the flight arc; the rest is flat stance.
    Y is "height" (positive up) so the arc is a downward parabola
    above the stance baseline.
    """
    poses = np.zeros((n, 17, 3), dtype=np.float32)
    for f in range(n):
        poses[f] = np.random.rand(17, 3) * 0.1
    for f in range(2, 8):
        h = -0.02 * (f - 2) * (7 - f)  # peak +0.08 at f=4..5
        poses[f, :, 1] = 1.0 + h
    return poses


# --------------------------------------------------------------------------- #
# Observable 1 (BUG 1): NaN fps → silent fit_quality=0.0 coercion in
# `fit_jump_trajectory` (3D path, the public entry). The `ss_tot > 0`
# clause is NaN-blind: NaN > 0 is False → r_squared = 0. Looks like a
# "bad parabolic fit" for an OTHERWISE valid arc — silently wrong.
# --------------------------------------------------------------------------- #


def test_fit_jump_trajectory_nan_fps_fit_quality_no_nan_repro():
    """CORRECT behavior: `fit_jump_trajectory(poses, takeoff_idx=2,
    landing_idx=7, fps=NaN)` must NOT leak NaN into the return dict.
    Existing `fps <= 0` guard does NOT catch NaN (`NaN <= 0` is False).
    NaN falls through into the try-block; the parabolic fit runs on
    NaN-time data, `ss_tot > 0` is False → `fit_quality = 0.0` (silent
    NaN→0, but `flight_time = t[-1] - t[0]` is NaN, leaking NaN into
    the dict — the actual BUG is the NaN leak, not the zero fit_quality,
    which is the explicit early-return value).

    RED now: `fit_jump_trajectory(fps=NaN)` returns `flight_time=NaN`
    and `height=0.12` (real CoM spread from the NaN-fit parabola, not
    a clean early-return zeros).
    """
    engine = PhysicsEngine()
    r = engine.fit_jump_trajectory(
        _flight_pose_3d(), takeoff_idx=2, landing_idx=7, fps=float("nan")
    )

    # The actual BUG observable: NaN leaks into the return dict via the
    # parabolic fit on NaN-time data, even though `ss_tot > 0 else 0`
    # silently zeros fit_quality.
    assert "flight_time" in r, f"BUG: missing 'flight_time' in result {r!r}."
    ft = r["flight_time"]
    assert ft is None or (isinstance(ft, (int, float)) and math.isfinite(ft)), (
        f"BUG: fit_jump_trajectory(fps=NaN) leaked NaN into flight_time="
        f"{ft!r}. NaN fps must yield None or finite (graceful unknown), "
        f"never NaN — NaN poisons JSON / DB / recommender."
    )
    assert "fit_quality" in r, f"BUG: missing 'fit_quality' in result {r!r}."
    fq = r["fit_quality"]
    assert fq is None or (isinstance(fq, (int, float)) and math.isfinite(fq)), (
        f"BUG: fit_jump_trajectory(fps=NaN) leaked NaN into fit_quality="
        f"{fq!r}. NaN fps must yield None or finite (graceful unknown), "
        f"never NaN."
    )


# --------------------------------------------------------------------------- #
# Observable 2 (BUG 2): NaN fps → flight_time=NaN propagates through the
# `except`-fallback path in `_fit_jump_trajectory_with_com` (private
# sibling, used by `analyze()`). Line 437: `flight_time = n_frames / fps`
# → NaN when fps=NaN. The `except` path can also be hit when `ss_tot`
# is NaN — `ss_res/ss_tot` is NaN, but r_squared is 0; the curve_fit
# itself succeeds with NaN-time data, so this BUG is observable on the
# happy path.
# --------------------------------------------------------------------------- #


def test_fit_jump_trajectory_with_com_nan_fps_flight_time_no_nan_repro():
    """CORRECT behavior: `_fit_jump_trajectory_with_com(poses, 2, 7,
    com, fps=NaN)` must NOT leak NaN into `flight_time`. The existing
    `fps <= 0` guard is NaN-blind.

    RED now: the try-block curve_fit runs on NaN-time data, succeeds
    silently, and `flight_time = t[-1] - t[0]` becomes NaN. This NaN
    leaks through `analyze()` into `PhysicsResult.flight_time`, which
    is what the recommender / JSON layer reads.
    """
    engine = PhysicsEngine()
    poses = _flight_pose_3d()
    com = engine.calculate_center_of_mass(poses)
    r = engine._fit_jump_trajectory_with_com(
        poses, takeoff_idx=2, landing_idx=7, com_trajectory=com, fps=float("nan")
    )

    assert "flight_time" in r, f"BUG: missing 'flight_time' in result {r!r}."
    ft = r["flight_time"]
    assert ft is None or (isinstance(ft, (int, float)) and math.isfinite(ft)), (
        f"BUG: _fit_jump_trajectory_with_com(fps=NaN) leaked NaN into "
        f"flight_time={ft!r}. NaN fps must yield None or finite (graceful "
        f"unknown), never NaN — NaN poisons JSON / DB / recommender."
    )


# --------------------------------------------------------------------------- #
# Observable 3 (BUG 3): NaN fps propagates through `analyze()` into the
# top-level `PhysicsResult.flight_time` field. `analyze()` does not have
# its own fps guard — it passes fps straight through to
# `_fit_jump_trajectory_with_com`, which silently returns NaN flight_time.
# --------------------------------------------------------------------------- #


def test_analyze_nan_fps_flight_time_no_nan_repro():
    """CORRECT behavior: `analyze(poses, takeoff_idx=2, landing_idx=7,
    fps=NaN)` must NOT leak NaN into `PhysicsResult.flight_time`. The
    `analyze()` wrapper has no fps guard; it forwards to
    `_fit_jump_trajectory_with_com`, which silently returns
    `flight_time=NaN`.

    RED now: `analyze(fps=NaN).flight_time` is `nan` (not None, not 0).
    """
    engine = PhysicsEngine()
    r = engine.analyze(_flight_pose_3d(), takeoff_idx=2, landing_idx=7, fps=float("nan"))

    assert r.flight_time is None or (
        isinstance(r.flight_time, (int, float)) and math.isfinite(r.flight_time)
    ), (
        f"BUG: analyze(fps=NaN) leaked NaN into PhysicsResult.flight_time="
        f"{r.flight_time!r}. NaN fps must yield None or finite (graceful "
        f"unknown), never NaN — NaN poisons JSON / DB / recommender."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid fps=30 still reports finite, nonzero
# flight_time, fit_quality. The NaN-fps guard must not change the
# valid-fps path. Mirrors the analyze_2d regression test from PR #1131.
# --------------------------------------------------------------------------- #


def test_fit_jump_trajectory_valid_fps_finite_nonzero_repro():
    """Regression guard: an all-valid parabolic flight at fps=30 with
    takeoff/landing must still report finite, > 0 `flight_time` and
    finite `fit_quality`. The NaN-fps guard must not regress the
    valid-fps case.
    """
    engine = PhysicsEngine()
    r = engine.fit_jump_trajectory(_flight_pose_3d(), takeoff_idx=2, landing_idx=7, fps=30.0)

    assert r["flight_time"] is not None and math.isfinite(r["flight_time"]), (
        f"BUG (regression): all-valid fps=30 flight reported flight_time="
        f"{r['flight_time']!r}, expected finite. The NaN-fps guard must not "
        f"change the valid-fps case."
    )
    assert r["flight_time"] > 0, (
        f"BUG (regression): valid fps=30 reported flight_time="
        f"{r['flight_time']!r} (not > 0). Expected positive seconds."
    )
    fq = r["fit_quality"]
    assert fq is not None and math.isfinite(fq), (
        f"BUG (regression): all-valid fps=30 flight reported fit_quality="
        f"{fq!r}, expected finite. The NaN-fps guard must not regress the "
        f"valid-fps case."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `math.isfinite(fps)` guard present
# at the top of BOTH `fit_jump_trajectory` and
# `_fit_jump_trajectory_with_com`, before the first /fps. Confirms the
# contract that NaN fps is treated as "unknown framerate" and yields
# graceful zeros. Mirrors the source check in PR #1131.
# --------------------------------------------------------------------------- #


def test_fit_jump_trajectory_nan_fps_guard_source_repro():
    """GREEN contract source check: the NaN-fps leak is fixed by adding
    a `math.isfinite(fps) and fps > 0` guard at the top of BOTH
    `fit_jump_trajectory` and `_fit_jump_trajectory_with_com`, before
    the first `/fps`. The existing `fps <= 0` guard is necessary but
    not sufficient — it does NOT catch NaN (`NaN <= 0` is False).
    Mirror PR #1043/#1044/#1131 sibling pattern.
    """
    src_fit = inspect.getsource(PhysicsEngine.fit_jump_trajectory)
    src_with_com = inspect.getsource(PhysicsEngine._fit_jump_trajectory_with_com)
    for name, src in [
        ("fit_jump_trajectory", src_fit),
        ("_fit_jump_trajectory_with_com", src_with_com),
    ]:
        assert "math.isfinite" in src, (
            f"BUG: {name} must guard `math.isfinite(fps) and fps > 0` "
            f"before the first `/fps`. The existing `fps <= 0` guard is "
            f"NaN-blind (NaN <= 0 is False), so NaN fps propagates to "
            f"flight_time and silently coerces fit_quality to 0.0. "
            f"Mirror PR #1043/#1044/#1131 sibling pattern."
        )
