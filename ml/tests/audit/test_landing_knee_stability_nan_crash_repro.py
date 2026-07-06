"""RED repro — `BiomechanicsAnalyzer.compute_landing_knee_stability` calls
`compute_knee_angle_series` for BOTH left and right sides over the post-landing
frames, which calls `_compute_knee_angle_series_numba`, which calls
`angle_3pt_rad(hip, knee, foot)` with NO NaN guard. A NaN knee keypoint on a
post-landing frame (the routine occlusion case for a landing leg) raises
ZeroDivisionError under Numba `@njit(fastmath=True)` (`nan/nan`), killing the
whole `analyze()` call (tranche BK).

`compute_landing_knee_stability` (ml/src/analysis/metrics.py:830-869):

    left_knee_angles = self.compute_knee_angle_series(post_landing_poses, side="left")
    right_knee_angles = self.compute_knee_angle_series(post_landing_poses, side="right")
    left_std = float(np.std(left_knee_angles))
    right_std = float(np.std(right_knee_angles))
    avg_std = (left_std + right_std) / 2.0
    stability = max(0.0, 1.0 - avg_std / 15.0)

`_compute_knee_angle_series_numba` (metrics.py:38-68, `@njit(fastmath=True)`):

    for i in range(num_frames):
        hip = pose[hip_idx]; knee = pose[knee_idx]; foot = pose[foot_idx]
        angle_rad = angle_3pt_rad(hip, knee, foot)   # crash on NaN knee
        angles[i] = angle_rad * rad2deg

`angle_3pt_rad` (geometry.py:12-31, `@njit(fastmath=True)`):

    ba = a - b
    bc = c - b
    cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)

When `knee` is NaN: `ba = a - nan = nan`, `norm(ba) = nan`, denominator =
`nan * nan + 1e-8 = nan` (1e-8 + nan = nan), `dot = nan`, `nan/nan` under
fastmath → ZeroDivisionError (NOT NaN propagation).

This is DISTINCT from tranche BH (test_landing_quality_nan_knee_crash_repro):
  - BH crashes `compute_landing_quality` — the SINGLE landing-frame angle via
    `angle_3pt` (metrics.py:803-828), one knee, one frame.
  - BK crashes `compute_landing_knee_stability` — the POST-LANDING SERIES
    (`landing+1..end`) via `_compute_knee_angle_series_numba` (metrics.py:855-
    856), BOTH knees, multiple frames.

A single NaN knee on one post-landing frame kills `analyze()`. The two
metrics are computed at different call sites with different code paths; fixing
BH (the landing-frame `angle_3pt`) does NOT fix BK (the numba series), and vice
versa. Both must be guarded.

Reproduced (10 frames, fps=30, waltz_jump; landing=7; post-landing = frames
8..9; left knee valid 90°, right knee NaN on post-landing):

    analyze() → ZeroDivisionError('division by zero')

Consequences (prod impact — landing_knee_stability feeds the landing-quality
composite, GOE, recommender, gamification, the same chain as BH but via a
different metric):
  1. `analyze()` (metrics.py:251-255) emits `landing_knee_stability`; a NaN
     knee on a post-landing frame raises ZeroDivisionError up through
     `compute_landing_knee_stability` and `analyze()` — EVERY metric for the
     session (airtime, height, rotation, GOE, recommender, gamification XP)
     is lost, not just the stability metric.
  2. Knee occlusion on the post-landing frames is COMMON — the free leg is
     often hidden behind the landing leg, the knee is small, the tracker
     drops it. This is routine, not an edge case.
  3. `compute_knee_angle_series` is ALSO called at metrics.py:464 (step
     element knee angles) — the same numba crash path is reachable from the
     step-element branch, not just landing stability. One root cause, two
     callers.
  4. Existing tests miss it: `test_compute_landing_knee_stability_stable` /
     `wobbly` / `no_post_landing` (test_metrics.py:322-431) feed all-valid
     keypoints. The tranche-F test (`test_ml_audit_tranche_f_repro.py`) checks
     the missing `[0,1]` cap on stability — it does NOT feed a NaN knee and
     does not exercise the numba crash path.

The fix (NOT applied — repro only): guard NaN in the series. The root-cause
fix in `angle_3pt_rad` (return NaN on NaN input, not raise — `np.isnan` check
on `a/b/c` before the division, return `np.nan`) would fix this caller, the
BH caller, and the BI element_segmenter caller at once. Alternatively, guard
NaN per-frame in `_compute_knee_angle_series_numba` (skip NaN frames, append
0.0, matching the element_segmenter origin-skip contract) and use
`np.nanstd` / `np.nanmean` for the std.

A correct `avg_std` must also be NaN-safe — `np.std` of a NaN-contaminated
array returns NaN (not raises), but if the numba guard returns NaN angles,
`np.std` propagates NaN to `avg_std`, `1.0 - nan/15.0 = nan`, and `max(0.0,
nan) = 0.0` (the #454 arg-order trap, same as tranche BJ) — the stability
reads as WORST (0.0) for an occlusion, not as "no data". The fix must use
`np.nanstd` (or mask NaN frames before the std) so the stability degrades
gracefully, not to 0.0.

RED now: the observable assertions below describe the CORRECT behavior — a NaN
knee keypoint on a post-landing frame must not crash `analyze()`; the metric
must degrade gracefully (skip the NaN frame, or return a NaN-flagged value),
and `analyze()` must return the full metric list. They FAIL because
`_compute_knee_angle_series_numba` raises ZeroDivisionError. After the fix:
NaN is skipped / propagated and `analyze()` returns. The source-check test
confirms the unguarded `angle_3pt_rad(hip, knee, foot)` call and the
`max(0.0, 1.0 - avg_std / 15.0)` line are present (root cause locked).

Pure-Python (no GPU, no DB): `compute_landing_knee_stability` and `analyze`
are pure-data functions over a poses array + phase markers.
"""

import inspect

import numpy as np

from src.analysis.element_defs import ELEMENT_DEFS
from src.analysis.metrics import (
    BiomechanicsAnalyzer,
    _compute_knee_angle_series_numba,
)
from src.types import ElementPhase, H36Key


def _post_landing_nan_pose(nan_side: str = "right", n: int = 10) -> np.ndarray:
    """A 10-frame waltz-jump pose sequence whose post-landing frames (8..9)
    have a NaN knee keypoint on the chosen side (occlusion) and a valid 90°
    knee on the other side.

    Landing frame = 7. Phases: start=0, takeoff=2, peak=4, landing=7, end=9.
    Pre-landing and landing frames have valid knees so the landing-frame
    metric (BH) does not crash first — the crash must come from the
    post-landing series (BK).
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.LHIP] = [0.0, 0.0]
        poses[f, H36Key.LKNEE] = [1.0, 1.0]
        poses[f, H36Key.LFOOT] = [2.0, 0.0]
        poses[f, H36Key.RHIP] = [0.0, 0.0]
        poses[f, H36Key.RFOOT] = [2.0, 0.0]
        # Default: both knees valid.
        poses[f, H36Key.RKNEE] = [1.0, 1.0]
        if nan_side == "right" and f >= 8:
            poses[f, H36Key.RKNEE] = [np.nan, np.nan]
        elif nan_side == "left" and f >= 8:
            poses[f, H36Key.LKNEE] = [np.nan, np.nan]
    return poses


def _phases(n: int = 10):
    return ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=4, landing=7, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: a NaN knee keypoint on a post-landing frame must NOT crash
# analyze() — distinct from BH (landing-frame single angle).
# --------------------------------------------------------------------------- #


def test_nan_post_landing_right_knee_does_not_crash_analyze_repro():
    """CORRECT behavior: a NaN right-knee keypoint on the POST-LANDING frames
    (the routine occlusion case — free leg hidden behind landing leg after
    touchdown) must not crash `BiomechanicsAnalyzer.analyze()`. The analyzer
    must degrade gracefully — skip the NaN frame in the knee-angle series,
    or return a NaN-flagged stability — and still return the full metric list.

    RED now: `compute_landing_knee_stability` calls
    `compute_knee_angle_series(post_landing_poses, side="right")` →
    `_compute_knee_angle_series_numba` → `angle_3pt_rad(hip, nan_knee, foot)`,
    which raises ZeroDivisionError under Numba fastmath (norm of NaN vertex =
    nan, denominator nan*nan+1e-8 = nan, nan/nan → ZeroDivisionError). The
    crash propagates out of `analyze()`. After the fix: NaN is skipped /
    propagated and `analyze()` returns.
    """
    poses = _post_landing_nan_pose(nan_side="right")
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    try:
        results = analyzer.analyze(poses, _phases(), fps=30.0)
    except ZeroDivisionError as e:
        raise AssertionError(
            f"BUG: BiomechanicsAnalyzer.analyze() raised ZeroDivisionError "
            f"({e!r}) when a post-landing frame has a NaN right-knee keypoint. "
            f"`compute_landing_knee_stability` (metrics.py:855) calls "
            f"`compute_knee_angle_series(post_landing_poses, side='right')` → "
            f"`_compute_knee_angle_series_numba` → `angle_3pt_rad(hip, knee, "
            f"foot)` with no NaN guard. Under Numba `@njit(fastmath=True)` the "
            f"division `dot(ba,bc) / (norm*norm + 1e-8)` has a NaN denominator "
            f"(1e-8 + nan = nan) and raises ZeroDivisionError instead of "
            f"returning NaN. The crash propagates through `analyze()`, killing "
            f"EVERY metric for the session. This is tranche BK, DISTINCT from "
            f"tranche BH (which crashes the landing-FRAME single angle at "
            f"`compute_landing_quality`, not the post-landing SERIES). Knee "
            f"occlusion on post-landing frames is routine (free leg hidden "
            f"behind landing leg), so this is a routine input, not an edge case."
        ) from e

    names = [r.name for r in results]
    assert "landing_knee_stability" in names, (
        f"test fixture broken or contract changed: analyze() returned metrics "
        f"{names} with no landing_knee_stability. The repro needs the stability "
        f"metric present (graceful degradation, not silent drop)."
    )


# --------------------------------------------------------------------------- #
# Observable 2: symmetric — NaN LEFT knee on post-landing also crashes.
# --------------------------------------------------------------------------- #


def test_nan_post_landing_left_knee_does_not_crash_analyze_repro():
    """CORRECT behavior: a NaN LEFT-knee keypoint on the post-landing frames
    must also not crash `analyze()`. The crash is symmetric —
    `compute_landing_knee_stability` reads BOTH knees (line 855 left, line 856
    right), so a NaN on either side reaches the numba crash path.

    RED now: `angle_3pt_rad` on the NaN left knee raises the same
    ZeroDivisionError. After the fix: graceful degradation on both sides.
    """
    poses = _post_landing_nan_pose(nan_side="left")
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    try:
        results = analyzer.analyze(poses, _phases(), fps=30.0)
    except ZeroDivisionError as e:
        raise AssertionError(
            f"BUG: analyze() raised ZeroDivisionError ({e!r}) when a "
            f"post-landing frame has a NaN LEFT-knee keypoint. "
            f"`compute_landing_knee_stability` calls "
            f"`compute_knee_angle_series(..., side='left')` (metrics.py:855); "
            f"the numba series crashes on the NaN left knee the same way as the "
            f"right. The crash is symmetric in which knee is NaN — both sides "
            f"are vulnerable. Fixing only the right-side path would leave the "
            f"left-side path broken."
        ) from e

    names = [r.name for r in results]
    assert "landing_knee_stability" in names, (
        f"test fixture broken: analyze() returned {names} with no landing_knee_stability."
    )


# --------------------------------------------------------------------------- #
# Observable 3: a NaN post-landing knee must not report the WORST stability
# (0.0). The metric must degrade gracefully, not fall into the
# `max(0.0, nan) = 0.0` (#454) trap. A perfectly stable landing with one
# occluded post-landing frame must report stability close to the all-valid
# case (~1.0), not 0.0.
# --------------------------------------------------------------------------- #


def test_nan_post_landing_knee_does_not_report_worst_stability_repro():
    """CORRECT behavior: a perfectly stable landing (constant 90° knee on the
    valid side, NaN on the occluded side for one post-landing frame) must NOT
    report the WORST stability (0.0). The metric must degrade gracefully —
    skip the NaN frame (`np.nanstd`) and report stability close to the
    all-valid case (~1.0), not a false "totally unstable" diagnosis.

    RED now: if the numba guard returns NaN angles for the NaN frame (instead
    of raising), `np.std` of the NaN-contaminated series is NaN, `avg_std =
    (left_std + right_std) / 2.0 = nan` (if either side is NaN), `1.0 - nan/15.0
    = nan`, and Python `max(0.0, nan) = 0.0` (the #454 arg-order trap). The
    stability reads as WORST (0.0) for an occlusion, not as "no data". After
    the fix: `np.nanstd` (or NaN-mask) skips the NaN frame → stability ~1.0.

    NOTE: this test only asserts the graceful contract IF the crash is fixed
    (the numba path returns rather than raises). Today the numba path RAISES
    (observable 1), so this test catches the ZeroDivisionError and asserts
    the stability is not 0.0 — today it FAILS with the crash; after the fix
    it FAILS if the fix uses `np.std` (NaN-poisons to 0.0) instead of
    `np.nanstd` (graceful). Either way it is RED against the current code.
    """
    poses = _post_landing_nan_pose(nan_side="right")
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    try:
        results = analyzer.analyze(poses, _phases(), fps=30.0)
    except ZeroDivisionError as e:
        raise AssertionError(
            f"BUG: analyze() raised ZeroDivisionError ({e!r}) on a NaN "
            f"post-landing knee. The numba series crash (observable 1) also "
            f"blocks this graceful-degradation contract. After the crash fix, "
            f"the stability must not fall into `max(0.0, nan) = 0.0` (#454) — "
            f"it must use `np.nanstd` to skip the NaN frame."
        ) from e

    stab = next(r for r in results if r.name == "landing_knee_stability")
    assert stab.value > 0.3, (
        f"BUG: landing_knee_stability = {stab.value:.3f} (WORST) for a "
        f"perfectly stable landing with one occluded post-landing knee frame. "
        f"The NaN-contaminated knee-angle series makes `np.std` return NaN, "
        f"`avg_std = nan`, `1.0 - nan/15.0 = nan`, and Python `max(0.0, nan) = "
        f"0.0` (#454 arg-order NaN-unsafe). A stable landing reads as totally "
        f"unstable — a false diagnosis when the truth is 'no data for that "
        f"frame'. The fix must use `np.nanstd` (or mask NaN frames before the "
        f"std) so the stability degrades gracefully, not to 0.0."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid post-landing still reports ~1.0 stability.
# --------------------------------------------------------------------------- #


def test_all_valid_landing_stability_unchanged_repro():
    """Regression guard: when both knees are valid on every post-landing
    frame, `compute_landing_knee_stability` must still report ~1.0 (stable).
    The fix (NaN guard + np.nanstd) must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    n = 10
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.LHIP] = [0.0, 0.0]
        poses[f, H36Key.LKNEE] = [1.0, 1.0]
        poses[f, H36Key.LFOOT] = [2.0, 0.0]
        poses[f, H36Key.RHIP] = [0.0, 0.0]
        poses[f, H36Key.RKNEE] = [1.0, 1.0]
        poses[f, H36Key.RFOOT] = [2.0, 0.0]

    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    stab = analyzer.compute_landing_knee_stability(poses, _phases())
    assert stab > 0.7, (
        f"BUG (regression): all-valid landing reported stability {stab:.3f}, "
        f"expected ~1.0 (stable). The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — unguarded angle_3pt_rad in numba series
# and max(0.0, 1.0 - avg_std / 15.0) NaN-unsafe max.
# --------------------------------------------------------------------------- #


def test_landing_knee_stability_unguarded_source_repro():
    """Source check (GREEN contract): the #868 fix is in place.

    Root cause was two-layer:
      1. `_compute_knee_angle_series_numba` called `angle_3pt_rad(hip, knee,
         foot)` with no NaN guard. Under @njit(fastmath=True), `nan/nan` raises
         ZeroDivisionError (NOT NaN propagation) -- crashing analyze() and
         killing every session metric. A guard *inside* the @njit core does
         not help: fastmath reorders / ignores the finite check (verified:
         NUMBA_DISABLE_JIT=1 -> guard works, with JIT -> still crashes). So
         the fix lives in the Python wrapper `compute_knee_angle_series`: it
         masks NaN frames to a finite placeholder before the jitted core, then
         restores NaN on the occluded frames so callers can skip them.
      2. `compute_landing_knee_stability` ended with `max(0.0, 1.0 - avg_std /
         15.0)` (Python max -- NaN-unsafe, arg-order-dependent, #454:
         `max(0.0, nan) = 0.0`) and used `np.std` (NaN-propagating). Fix:
         `np.nanstd` + finite-side filter + `np.clip` (NaN-safe after the
         finite guard).
    """
    # Fix layer 1: the Python wrapper masks NaN before the jitted core.
    wrapper_src = inspect.getsource(BiomechanicsAnalyzer.compute_knee_angle_series)
    assert "np.isfinite" in wrapper_src, (
        "BUG: compute_knee_angle_series must guard NaN frames before the "
        "jitted core (#868). The @njit core cannot guard under fastmath."
    )
    assert "np.nan_to_num" in wrapper_src, (
        "BUG: compute_knee_angle_series must mask NaN frames to a finite "
        "placeholder before _compute_knee_angle_series_numba (#868)."
    )
    assert "angles[~finite_frames]" in wrapper_src and "np.nan" in wrapper_src, (
        "BUG: compute_knee_angle_series must restore NaN on occluded frames "
        "after the jitted core so callers can skip them (#868)."
    )
    # The @njit core stays unguarded (a guard inside fastmath does not work).
    numba_src = inspect.getsource(_compute_knee_angle_series_numba)
    assert "angle_3pt_rad(hip, knee, foot)" in numba_src, (
        "BUG: _compute_knee_angle_series_numba must still call "
        "`angle_3pt_rad(hip, knee, foot)` -- the guard lives in the wrapper, "
        "not the @njit core (fastmath ignores finite checks)."
    )

    # Fix layer 2: compute_landing_knee_stability is NaN-safe.
    stab_src = inspect.getsource(BiomechanicsAnalyzer.compute_landing_knee_stability)
    assert "np.nanstd" in stab_src, (
        "BUG: compute_landing_knee_stability must use np.nanstd (#868) -- "
        "np.std propagates NaN over the whole array."
    )
    assert "np.std(left_knee_angles)" not in stab_src, (
        "BUG: compute_landing_knee_stability still uses np.std(left_knee_angles) "
        "(NaN-propagating) -- must be np.nanstd (#868)."
    )
    assert "np.clip(1.0 - avg_std / 15.0, 0.0, 1.0)" in stab_src, (
        "BUG: compute_landing_knee_stability must use np.clip (NaN-safe after "
        "the finite guard) instead of max(0.0, ...) (#454, #868)."
    )
    assert "max(0.0, 1.0 - avg_std / 15.0)" not in stab_src, (
        "BUG: compute_landing_knee_stability still uses the Python max(0.0, ...) "
        "form -- NaN-unsafe arg-order (#454). Must be np.clip (#868)."
    )
