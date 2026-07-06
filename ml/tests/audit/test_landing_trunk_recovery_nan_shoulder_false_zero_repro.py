"""RED repro — `BiomechanicsAnalyzer.compute_landing_trunk_recovery` computes
`avg_lean = np.mean(np.abs(trunk_lean))` over the post-landing frames, then
`recovery = max(0.0, 1.0 - avg_lean / 30.0)`. When ANY post-landing frame has
a NaN shoulder keypoint (occlusion — the normal case for a skater turned
away from the camera on landing), `trunk_lean` contains NaN, `avg_lean` is
NaN (`np.mean` of a NaN-contaminated array), `1.0 - nan/30.0 = nan`, and
Python `max(0.0, nan)` returns `0.0` (arg-order NaN-unsafe, #454: `max(0.0,
nan) = 0.0` but `max(nan, 0.0) = nan`). So a skater with an OCCLUDED shoulder
is reported as having the WORST trunk recovery (0.0), not as "no data" — a
false diagnosis (tranche BJ).

`compute_landing_trunk_recovery` (ml/src/analysis/metrics.py:871-904):

    trunk_lean = self.compute_trunk_lean(post_landing_poses)
    avg_lean = float(np.mean(np.abs(trunk_lean)))
    # 30 degrees is a reasonable threshold for "poor recovery"
    recovery = max(0.0, 1.0 - avg_lean / 30.0)
    return float(recovery)

`_compute_trunk_lean_series_numba` (metrics.py:72-105):

    mid_hip = (pose[l_hip] + pose[r_hip]) * 0.5
    mid_shoulder = (pose[l_shoulder] + pose[r_shoulder]) * 0.5
    spine_vector = mid_shoulder - mid_hip
    lean = np.arctan2(spine_vector[0], -spine_vector[1])
    leans[i] = lean * rad2deg

When `RSHOULDER` is NaN: `mid_shoulder = (LSHOULDER + nan) * 0.5 = nan`,
`spine_vector = nan`, `np.arctan2(nan, ...) = nan` (NaN propagation — NOT a
crash), `lean = nan`. So `trunk_lean` for that frame is NaN.

Then:
  - `np.abs([nan, ...]) = [nan, ...]`
  - `np.mean([nan, ...]) = nan` (NumPy mean propagates NaN)
  - `1.0 - nan / 30.0 = nan`
  - `max(0.0, nan)` = 0.0  ← Python `max` is NaN-unsafe and arg-order-dependent
                                 (#454): `max(0.0, nan) = 0.0` because nan is not
                                 `> 0.0`, so the finite operand wins. `max(nan,
                                 0.0)` would return nan.

So a single NaN shoulder on one post-landing frame → recovery = 0.0 (worst).
The score claims the skater has "poor trunk recovery" when the truth is
"no data for that frame" — the metric confuses occlusion with bad posture.

Reproduced (12 frames, waltz_jump; landing=7; post-landing = frames 8..11;
upright trunk the whole time — LSHOULDER/RSHOULDER at y=-1.0, hips at y=0.0,
so trunk is vertical → lean ≈ 0° → recovery should be 1.0):

    all-valid post-landing              → recovery = 1.0   (correct: upright)
    RSHOULDER NaN on post-landing frames → recovery = 0.0   (BUG: occlusion
                                                            read as worst)

    np.mean(np.abs([nan, ...])) = nan
    1.0 - nan / 30.0             = nan
    max(0.0, nan)                 = 0.0   (#454 arg-order NaN-unsafe)
    max(nan, 0.0)                 = nan

Consequences (prod impact — landing_trunk_recovery feeds is_good, the
landing-quality composite score, GOE, recommender, gamification):
  1. `analyze()` (metrics.py:262-266) emits `landing_trunk_recovery` with
     `value=0.0` and the `is_good` gate `(0.5, 1.0)` (element_defs.py:88
     etc.) → 0.0 not in range → `is_good=False`. A skater with an occluded
     shoulder reads as "poor recovery" — a false bad metric.
  2. `compute_landing_quality_score` (metrics.py:1557) computes
     `trunk_recovery * 0.15` — the 0.0 contributes nothing, deflating the
     composite landing-quality score for an occlusion, not for bad posture.
  3. `_compute_overall_score` (pipeline.py:608-629) counts `is_good` over
     metrics; the false `is_good=False` loses a `good_count` point → overall
     deflated → gamification XP (`award_session_xp int(overall)`) and skill
     unlocks (`check_skill_unlocks`) penalized for an occlusion, not for
     performance. Cross-layer with #437/#852-class.
  4. Diagnostics `check_new_pr` / `check_declining_trend` see a 0.0 recovery
     as a real personal-record-low or declining trend — false diagnostics.
  5. Existing tests miss it: `test_landing_trunk_recovery_*` feed all-valid
     keypoints. No test feeds a NaN shoulder on a post-landing frame. The
     `max(0.0, nan) = 0.0` arg-order trap (the #454 defect) is not exercised
     on this method.

The fix (NOT applied — repro only): make the metric NaN-aware. Either:
  - mask NaN before the mean: `avg_lean = float(np.nanmean(np.abs(trunk_lean)))`
    and return a NaN-flagged value (or 1.0 = "no data → no penalty") when
    `np.all(np.isnan(trunk_lean))`; or
  - replace Python `max(0.0, x)` with `np.nan_to_num(..., nan=1.0)` /
    `np.fmax(0.0, 1.0 - avg_lean/30.0)` (NaN-safe — but `np.fmax(0.0, nan) =
    nan`, so this alone returns NaN, which still needs a downstream guard).

The correct contract: an occluded shoulder frame must NOT read as the worst
recovery. The metric must either skip the NaN frame (`np.nanmean`) or
return a NaN/degraded sentinel that the caller can flag as "no data", not
0.0.

RED now: the observable assertions below describe the CORRECT behavior — a
post-landing NaN shoulder must not produce recovery=0.0 (worst); an
upright trunk with one occluded frame must report a recovery close to the
all-valid case (graceful degradation), not 0.0. They FAIL because
`max(0.0, nan) = 0.0`. After the fix: `np.nanmean` (or equivalent) keeps
the recovery in the upright range. The source-check test confirms the
`max(0.0, 1.0 - avg_lean / 30.0)` line is present (root cause locked).

Pure-Python (no GPU, no DB): `compute_landing_trunk_recovery` and
`compute_trunk_lean` are pure-data functions over a poses array + phase
markers.
"""

import inspect

import numpy as np

from src.analysis.element_defs import ELEMENT_DEFS
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _upright_pose(nan_post_landing: bool, n: int = 12) -> np.ndarray:
    """A 12-frame waltz-jump pose sequence with an UPRIGHT trunk the whole
    time (LSHOULDER/RSHOULDER at y=-1.0, hips at y=0.0 → spine vertical →
    lean ≈ 0° → recovery should be 1.0).

    Landing frame = 7; post-landing = frames 8..11. When `nan_post_landing`
    is True, RSHOULDER is NaN on the post-landing frames — the occlusion
    case (skater turned away from camera on landing).
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.LHIP] = [-0.1, 0.0]
        poses[f, H36Key.RHIP] = [0.1, 0.0]
        poses[f, H36Key.LSHOULDER] = [-0.1, -1.0]
        poses[f, H36Key.RSHOULDER] = [0.1, -1.0]
    if nan_post_landing:
        for f in range(8, n):
            poses[f, H36Key.RSHOULDER] = [np.nan, np.nan]
    return poses


def _phases(n: int = 12):
    return ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=4,
                        landing=7, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: an upright trunk with an occluded post-landing shoulder must
# NOT report the worst recovery (0.0); it must degrade gracefully (close to
# the all-valid recovery of 1.0).
# --------------------------------------------------------------------------- #


def test_nan_post_landing_shoulder_does_not_report_worst_recovery_repro():
    """CORRECT behavior: a skater with an upright trunk (lean ≈ 0° →
    recovery should be ~1.0) and a NaN shoulder on the post-landing frames
    (occlusion) must not be reported as the WORST recovery (0.0). The metric
    must degrade gracefully — either skip the NaN frame (`np.nanmean`,
    recovery ≈ 1.0) or return a NaN/degraded sentinel that the caller can
    flag as "no data". It must NOT return 0.0 (a false "poor recovery"
    diagnosis).

    RED now: `trunk_lean` contains NaN for the occluded frames → `avg_lean =
    np.mean(np.abs(trunk_lean)) = nan` → `1.0 - nan/30.0 = nan` →
    `max(0.0, nan) = 0.0` (Python max is NaN-unsafe and arg-order-dependent,
    #454: `max(0.0, nan) = 0.0`). So an upright trunk with an occluded
    shoulder reads as recovery=0.0 (worst), not as ~1.0. After the fix:
    `np.nanmean` (or equivalent) skips the NaN frame → recovery ≈ 1.0.
    """
    norm = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    # Baseline: all-valid upright trunk → recovery should be ~1.0.
    h_valid = norm.compute_landing_trunk_recovery(_upright_pose(False), _phases())
    assert abs(h_valid - 1.0) < 0.1, (
        f"test fixture broken: all-valid upright trunk reported recovery "
        f"{h_valid:.3f}, expected ~1.0. The fixture needs a vertical spine "
        f"(lean ≈ 0°) so the all-valid baseline is ~1.0 — otherwise the "
        f"NaN-vs-valid contrast is meaningless."
    )

    # OCcluded post-landing shoulder — same upright trunk, one frame NaN.
    h_nan = norm.compute_landing_trunk_recovery(_upright_pose(True), _phases())

    # CORRECT contract: the occluded-frame recovery must NOT be 0.0 (worst).
    # It must be close to the all-valid recovery (graceful NaN-skip), or at
    # worst a NaN/degraded sentinel — NOT a false "poor recovery" diagnosis.
    assert h_nan > 0.3, (
        f"BUG: compute_landing_trunk_recovery returned {h_nan:.3f} for an "
        f"upright trunk (lean ≈ 0°, all-valid recovery = {h_valid:.3f}) with "
        f"a NaN RSHOULDER on the post-landing frames (occlusion). The "
        f"NaN-contaminated `trunk_lean` makes `avg_lean = "
        f"np.mean(np.abs(trunk_lean)) = nan`, so `1.0 - nan/30.0 = nan` and "
        f"Python `max(0.0, nan) = 0.0` (arg-order NaN-unsafe, #454: max(0.0, "
        f"nan) = 0.0). A skater with an occluded shoulder reads as the WORST "
        f"trunk recovery (0.0) — a false 'poor recovery' diagnosis when the "
        f"truth is 'no data for that frame'. The metric confuses occlusion "
        f"with bad posture. (Sanity: all-valid recovery = {h_valid:.3f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the recovery must NOT depend on which shoulder is occluded
# (LSHOULDER NaN vs RSHOULDER NaN must give the same result — symmetric).
# --------------------------------------------------------------------------- #


def test_nan_shoulder_recovery_is_symmetric_repro():
    """CORRECT behavior: occluding LSHOULDER vs RSHOULDER on the post-landing
    frames must give the SAME recovery (both feed the same `mid_shoulder`
    average; one NaN poisons it the same way). The metric must be symmetric.

    RED now: both give `avg_lean = nan` → `max(0.0, nan) = 0.0`, so they ARE
    symmetric — both report the WORST recovery. This is a regression guard
    that PASSES today (both 0.0) and must keep passing after the fix (both
    should report the same graceful-degradation value, ~1.0). It locks the
    symmetry contract so a fix that only handles one shoulder does not pass.
    """
    norm = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    n = 12
    poses_l = _upright_pose(False)
    poses_r = _upright_pose(False)
    for f in range(8, n):
        poses_l[f, H36Key.LSHOULDER] = [np.nan, np.nan]  # LSHOULDER occluded
        poses_r[f, H36Key.RSHOULDER] = [np.nan, np.nan]  # RSHOULDER occluded

    h_left_nan = norm.compute_landing_trunk_recovery(poses_l, _phases())
    h_right_nan = norm.compute_landing_trunk_recovery(poses_r, _phases())

    assert abs(h_left_nan - h_right_nan) < 0.02, (
        f"BUG (symmetry): occluding LSHOULDER vs RSHOULDER gives different "
        f"recoveries ({h_left_nan:.3f} vs {h_right_nan:.3f}). Both feed the "
        f"same `mid_shoulder = (LSHOULDER + RSHOULDER) * 0.5` average, so one "
        f"NaN poisons it identically — the metric must be symmetric in which "
        f"shoulder is occluded. A fix that only handles one shoulder would "
        f"break this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid upright trunk still reports ~1.0 recovery
# --------------------------------------------------------------------------- #


def test_all_valid_recovery_unchanged_repro():
    """Regression guard: an all-valid upright trunk must still report
    recovery ~1.0. The fix (np.nanmean or NaN-aware max) must not change the
    no-NaN case.

    This PASSES today; it locks the contract so a fix cannot regress the
    all-valid case.
    """
    norm = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    h = norm.compute_landing_trunk_recovery(_upright_pose(False), _phases())
    assert abs(h - 1.0) < 0.1, (
        f"BUG (regression): all-valid upright trunk reported recovery "
        f"{h:.3f}, expected ~1.0. The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `max(0.0, 1.0 - avg_lean / 30.0)` and the
# np.mean-without-nanmean line.
# --------------------------------------------------------------------------- #


def test_trunk_recovery_max_nan_unsafe_source_repro():
    """Source check: `compute_landing_trunk_recovery` computes
    `avg_lean = float(np.mean(np.abs(trunk_lean)))` (NOT `np.nanmean` —
    propagates NaN) and `recovery = max(0.0, 1.0 - avg_lean / 30.0)` (Python
    `max`, NaN-unsafe and arg-order-dependent, #454). Root cause locked.

    RED now: the `np.mean` (not nanmean) line and the `max(0.0, ...)` line
    are present (PASS — root cause locked). After the fix: the mean becomes
    `np.nanmean` (or a NaN mask) and/or the max becomes NaN-safe — this test
    FAILS, signaling the observable tests above should flip to GREEN.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_landing_trunk_recovery)
    # The np.mean (NOT nanmean) line is present — propagates NaN.
    assert "np.mean(np.abs(trunk_lean))" in src, (
        "BUG: compute_landing_trunk_recovery must compute "
        "`np.mean(np.abs(trunk_lean))` (NaN-propagating, not `np.nanmean`) "
        "for this repro to be valid. If it was changed to `np.nanmean` (or a "
        "NaN mask), the NaN-poisons-mean bug is fixed — update the observable "
        "tests to the GREEN contract."
    )
    assert "np.nanmean" not in src, (
        "BUG: compute_landing_trunk_recovery now uses `np.nanmean` — the "
        "NaN-poisons-mean bug is fixed; update the observable tests to the "
        "GREEN contract."
    )
    # The Python `max(0.0, ...)` line is present — NaN-unsafe, arg-order.
    assert "max(0.0, 1.0 - avg_lean / 30.0)" in src, (
        "BUG: compute_landing_trunk_recovery must compute "
        "`max(0.0, 1.0 - avg_lean / 30.0)` (Python max — NaN-unsafe, "
        "arg-order-dependent, #454) for this repro to be valid. If it was "
        "changed to a NaN-safe form (e.g. `np.fmax`, `np.nan_to_num`), the "
        "arg-order-NaN bug is fixed — update the observable tests to the "
        "GREEN contract."
    )