"""RED repro — `BiomechanicsAnalyzer.compute_relative_jump_height` computes the
CoM displacement between takeoff and peak, normalized by spine length:

    com_trajectory = calculate_com_trajectory(poses)   # weighted sum ALL kp
    takeoff_com = com_trajectory[phases.takeoff]
    flight_com = com_trajectory[phases.takeoff : phases.landing + 1]
    peak_com = np.min(flight_com)                       # NaN-propagating min
    com_displacement = float(takeoff_com - peak_com)    # nan - nan = nan
    return com_displacement / avg_spine                 # nan / finite = nan

`calculate_com_trajectory` (geometry.py:287-335) is a weighted sum of ALL 17
keypoint Y-coordinates; a NaN keypoint on the takeoff frame (or any flight
frame) makes the CoM NaN for those frames. `np.min` of a NaN-contaminated
slice is NaN (NumPy propagates NaN, not raises). `takeoff_com - peak_com =
nan - nan = nan`. `com_displacement / avg_spine = nan / finite = nan`. So
`relative_jump_height = nan` for a jump with ONE occluded keypoint on the
takeoff/flight frame — a false "no measurement", not "no jump" (tranche BP).

The `nan` then flows into the GOE grader (`compute_goe_score`, metrics.py:1542-
1543):

    rel_height = self.compute_relative_jump_height(poses, phases)
    height_score = min(1.0, rel_height / 1.0)   # min(1.0, nan) = 1.0 (#454)

Python `min(1.0, nan) = 1.0` (NaN-unsafe arg-order-dependent, #454: `min(1.0,
nan) = 1.0` because `1.0 < nan` is False, FIRST arg wins; `min(nan, 1.0) =
nan`). So a jump with one occluded keypoint reads `height_score = 1.0` — the
BEST (maximum) height score, not "no data" — a false BEST that inflates the
GOE total (height_score * 0.20 → +0.20 to GOE, +2.0 to the 0-10 score). The
INVERSE polarity of BJ/BL/BM (NaN → worst 0.0); here NaN → best 1.0, same
#454 arg-order trap as BN (`compute_hard_landing`).

Reproduced (12 frames, fps=30, waltz_jump; takeoff=2, peak=4, landing=7;
CoM rises at frames 4..6 (all keypoints shift UP, Y decreases) → rel_height
~0.98 valid):

    all-valid jump                       → rel_height = 0.975 (correct)
                                          → GOE = 5.625
    NaN RKNEE on takeoff frame (2..3)    → rel_height = nan  (BUG: no data)
                                          → height_score = min(1.0, nan) = 1.0
                                          → GOE = 6.675 (BUG: inflated +1.05)

Consequences (prod impact — relative_jump_height feeds analyze() emission,
the GOE height component, the recommender, gamification):
  1. `analyze()` (metrics.py:273-280) emits `relative_jump_height` with
     `value=nan`; the `is_good=False` gate is hardcoded (reference_range=(0,0)),
     but downstream consumers (recommender, multi_score, gamification) read
     `value` directly — NaN propagates into the recommender height band and
     the `compute_subscores` takeoff_power weighted sum.
  2. `compute_goe_score` (metrics.py:1542-1543) does `height_score = min(1.0,
     rel_height / 1.0)`; `min(1.0, nan) = 1.0` → height_score = 1.0 (BEST).
     GOE = height_score*0.20 + ... → the NaN inflates GOE by ~+0.20 (weighted)
     vs the all-valid case for the same jump. A jump with one occluded
     keypoint scores HIGHER than the same jump with all keypoints visible —
     the occlusion is rewarded.
  3. `compute_relative_jump_height` is ALSO the height metric for the
     recommender (`test_recommender_max_height_zero_range_spam_repro` documents
     the override at metrics.py:162-167 uses relative_jump_height, not
     max_height). A NaN rel_height feeds the recommender's height band logic.
  4. The CoM-weighted-sum means the bug triggers on NaN in ANY of the 17
     keypoints on the takeoff frame OR any flight frame (takeoff..landing) —
     wide blast radius, same root cause as BM/BN (`calculate_com_trajectory`).
     A single occluded wrist on the takeoff frame NaNs the height.
  5. Existing tests miss it: `test_compute_relative_jump_height`
     (test_metrics.py:436) and `test_compute_relative_jump_height_no_jump`
     (test_metrics.py:487) feed all-valid keypoints. No test feeds a NaN
     keypoint through the CoM into rel_height, and no test exercises the
     `min(1.0, nan) = 1.0` arg-order trap on the GOE height_score line.

The fix (NOT applied — repro only): make the metric NaN-aware. Either:
  - mask NaN before the displacement: `if not np.isfinite(takeoff_com) or not
    np.isfinite(peak_com): return <sentinel>` (e.g. 0.0 "no jump" or NaN
    flagged); or
  - use `np.nanmin(flight_com)` (NaN-safe min over the finite flight frames)
    AND a NaN guard on `takeoff_com`; and
  - replace `min(1.0, rel_height / 1.0)` with `np.nan_to_num(rel_height / 1.0,
    nan=0.0)` (NaN → neutral 0.0, not best 1.0) and clip with `np.clip`.
  - The deeper fix is in `calculate_com_trajectory`: NaN-aware CoM (mask NaN
    keypoints, renormalize masses over valid keypoints per frame), which
    fixes every CoM-based metric (smoothness BM, hard_landing BN,
    relative_jump_height BP, peak_com) at once — same root-cause approach as
    fixing `angle_3pt_rad` for the knee-angle callers (BH/BK/BI).

The correct contract: a NaN keypoint on the takeoff/flight frame must NOT
read as the BEST height score (1.0 in GOE, nan in the emitted metric). The
metric must skip the NaN frame (`np.nanmin` + NaN guard) and degrade
gracefully (close to the all-valid rel_height, or a neutral sentinel), and
the GOE height_score must NOT inflate to 1.0.

RED now: the observable assertions below describe the CORRECT behavior — a
jump with one occluded keypoint must NOT report the BEST GOE height_score
(1.0) and must NOT inflate the GOE total. They FAIL because `min(1.0, nan) =
1.0` and `nan / finite = nan`. After the fix: the NaN is handled and the
height_score does not inflate to 1.0. The source-check test confirms the
`min(1.0, rel_height / 1.0)` line and the unguarded CoM displacement are
present (root cause locked).

Pure-Python (no GPU, no DB): `compute_relative_jump_height`,
`compute_goe_score`, and `calculate_com_trajectory` are pure-data functions
over a poses array + phase markers.
"""

import inspect

import numpy as np

from src.analysis.element_defs import ELEMENT_DEFS
from src.analysis.metrics import BiomechanicsAnalyzer
from src.utils.geometry import calculate_com_trajectory
from src.types import ElementPhase, H36Key


def _jump_pose(nan_keypoint: str | None = None, n: int = 12) -> np.ndarray:
    """A 12-frame waltz-jump pose sequence where the CoM rises at frames 4..6
    (all keypoints shift UP, Y decreases in normalized coords) → rel_height
    should be ~0.98 (a real jump). takeoff=2, peak=4, landing=7.

    When `nan_keypoint` is set, that keypoint is NaN on frames 2 and 3
    (takeoff window) — the occlusion case. `calculate_com_trajectory` is a
    weighted sum over all 17 keypoints, so the CoM of those frames is NaN;
    `takeoff_com = nan`, `peak_com = nan` (np.min propagates NaN), and
    `rel_height = nan / avg_spine = nan`. The GOE grader then does
    `min(1.0, nan / 1.0) = 1.0` → false BEST height_score.
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
    # Jump: CoM rises at frames 4..6 (Y decreases).
    for f in range(4, 7):
        poses[f, :, 1] -= 0.3
    if nan_keypoint:
        kp = {"rknee": H36Key.RKNEE, "rwrist": H36Key.RWRIST,
              "lfoot": H36Key.LFOOT}[nan_keypoint]
        # NaN on takeoff frame AND takeoff+1 (the takeoff window 2..3 feeds
        # both takeoff_com and the spine-length average).
        poses[2, kp] = [np.nan, np.nan]
        poses[3, kp] = [np.nan, np.nan]
    return poses


def _phases(n: int = 12):
    return ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=4,
                        landing=7, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: a jump with one occluded keypoint on the takeoff frame must
# NOT report `relative_jump_height = nan`. The metric must degrade gracefully
# (close to the all-valid rel_height, or a neutral sentinel), not emit NaN.
# --------------------------------------------------------------------------- #


def test_nan_knee_rel_height_does_not_emit_nan_repro():
    """CORRECT behavior: a real jump (CoM rises at the peak → rel_height
    ~0.98) with ONE occluded knee keypoint on the takeoff frame must NOT
    report `relative_jump_height = nan`. The metric must degrade gracefully
    — skip the NaN frame in the CoM (`np.nanmin` + NaN guard) and report a
    height close to the all-valid case, or a neutral sentinel. It must NOT
    return nan (a false "no measurement" when the truth is "one keypoint
    occluded, the jump is real").

    RED now: `RKNEE` NaN on frames 2..3 → `calculate_com_trajectory` is a
    weighted sum over ALL 17 keypoints, so the CoM of those frames is NaN →
    `takeoff_com = nan` → `flight_com` has NaN → `np.min(flight_com) = nan`
    (NumPy propagates NaN) → `com_displacement = nan - nan = nan` →
    `rel_height = nan / avg_spine = nan`. A real jump reads as "no
    measurement". After the fix: the NaN frame is skipped and rel_height
    stays close to the all-valid value.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    # Baseline: all-valid jump → rel_height should be ~0.98 (a real jump).
    v_valid = analyzer.compute_relative_jump_height(_jump_pose(None), _phases())
    assert v_valid > 0.5, (
        f"test fixture broken: all-valid jump reported rel_height "
        f"{v_valid:.3f}, expected ~0.98 (a real jump, CoM rises at the peak). "
        f"The fixture needs the CoM to rise at frames 4..6 so the all-valid "
        f"baseline is a clear positive height — otherwise the NaN-vs-valid "
        f"contrast is meaningless."
    )

    # One occluded knee on takeoff window — same jump, one NaN keypoint.
    v_nan = analyzer.compute_relative_jump_height(_jump_pose("rknee"), _phases())

    # CORRECT contract: the occluded-keypoint height must NOT be NaN. It must
    # be a finite value close to the all-valid height (graceful NaN-skip), or
    # a neutral sentinel (e.g. 0.0) — NOT a false "no measurement" nan that
    # propagates into the GOE grader's `min(1.0, nan) = 1.0` trap.
    assert np.isfinite(v_nan), (
        f"BUG: compute_relative_jump_height returned {v_nan} (NaN) for a real "
        f"jump (all-valid rel_height = {v_valid:.3f}) with a NaN RKNEE on the "
        f"takeoff window (occlusion). `calculate_com_trajectory` is a weighted "
        f"sum over ALL 17 keypoints, so one NaN keypoint makes the CoM NaN for "
        f"those frames; `takeoff_com = nan`; `np.min(flight_com) = nan` (NumPy "
        f"propagates NaN); `com_displacement = nan - nan = nan`; "
        f"`rel_height = nan / avg_spine = nan`. A real jump reads as 'no "
        f"measurement' when the truth is 'one keypoint occluded, the jump is "
        f"real'. The NaN then flows into the GOE grader "
        f"`min(1.0, rel_height/1.0) = min(1.0, nan) = 1.0` (#454 arg-order "
        f"NaN-unsafe) → false BEST height_score. The metric must skip the NaN "
        f"frame (`np.nanmin` + NaN guard on `takeoff_com`) and degrade "
        f"gracefully. (Sanity: all-valid rel_height = {v_valid:.3f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint (CoM weighted sum),
# not just the knee — a NaN wrist (small, easily lost by the tracker) also
# NaNs the height. Wide blast radius.
# --------------------------------------------------------------------------- #


def test_nan_wrist_rel_height_does_not_emit_nan_repro():
    """CORRECT behavior: a real jump with one occluded WRIST on the takeoff
    frame must also not report `relative_jump_height = nan`. The CoM weighted
    sum includes the arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist
    poisons the CoM the same way as a NaN knee. The bug has a wide blast
    radius — ANY of the 17 keypoints, not just the knee.

    RED now: `RWRIST` NaN → CoM NaN → `rel_height = nan`. After the fix:
    graceful degradation on any occluded keypoint.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    v_nan = analyzer.compute_relative_jump_height(_jump_pose("rwrist"), _phases())

    assert np.isfinite(v_nan), (
        f"BUG: compute_relative_jump_height returned {v_nan} (NaN) for a real "
        f"jump with a NaN RWRIST on the takeoff window. The CoM weighted sum "
        f"includes the arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist "
        f"poisons the CoM the same way as a NaN knee. The bug has a wide blast "
        f"radius — ANY of the 17 keypoints, not just the knee. A fix that only "
        f"guards the knee (or only the legs) would leave the arm/head keypoints "
        f"broken. The root-cause fix is NaN-aware CoM "
        f"(`calculate_com_trajectory`) or `np.nanmin` + a NaN guard on "
        f"`takeoff_com`."
    )


# --------------------------------------------------------------------------- #
# Observable 3: the NaN must NOT inflate the GOE height_score to 1.0 (BEST).
# `compute_goe_score` does `height_score = min(1.0, rel_height / 1.0)`; the
# arg-order trap `min(1.0, nan) = 1.0` reads the occlusion as the MAX height
# score. A jump with one occluded keypoint must NOT score higher than the
# same jump with all keypoints visible.
# --------------------------------------------------------------------------- #


def test_nan_knee_goe_height_score_does_not_inflate_to_best_repro():
    """CORRECT behavior: the GOE height_score for a jump with one occluded
    keypoint must NOT be 1.0 (BEST). `compute_goe_score` (metrics.py:1542-
    1543) computes `height_score = min(1.0, rel_height / 1.0)`; the arg-order
    trap `min(1.0, nan) = 1.0` (#454) reads a NaN rel_height as the MAX
    height score. A jump with one occluded keypoint must NOT score higher
    than the same jump with all keypoints visible — the occlusion must not
    be rewarded.

    RED now: `RKNEE` NaN → `rel_height = nan` → `height_score = min(1.0,
    nan/1.0) = min(1.0, nan) = 1.0` (first arg wins, #454) → GOE inflated by
    ~+0.20 (height weight) vs the all-valid case. After the fix: the NaN is
    handled (neutral 0.0 or graceful skip) and height_score does not inflate
    to 1.0.

    This is the INVERSE polarity of BJ/BL/BM (NaN → worst 0.0): here NaN →
    best 1.0, same #454 arg-order trap as BN (`compute_hard_landing`).
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    # GOE for the all-valid jump (baseline).
    goe_valid = analyzer.compute_goe_score(_jump_pose(None), _phases(), fps=30.0)
    # GOE for the same jump with one occluded knee on the takeoff window.
    goe_nan = analyzer.compute_goe_score(_jump_pose("rknee"), _phases(), fps=30.0)

    # CORRECT contract: the occluded-keypoint GOE must NOT be higher than the
    # all-valid GOE. The occlusion must not inflate the score. (Today the NaN
    # inflates height_score to 1.0, pushing GOE up by ~+0.20.)
    assert goe_nan <= goe_valid + 0.05, (
        f"BUG: compute_goe_score with a NaN RKNEE on the takeoff window "
        f"returned GOE = {goe_nan:.3f}, HIGHER than the all-valid GOE = "
        f"{goe_valid:.3f} for the SAME jump. `compute_relative_jump_height` "
        f"returns nan (one NaN keypoint poisons the CoM weighted sum); "
        f"`compute_goe_score` does `height_score = min(1.0, rel_height / 1.0)` "
        f"= `min(1.0, nan) = 1.0` (Python min is NaN-unsafe arg-order-"
        f"dependent, #454: `min(1.0, nan) = 1.0` because `1.0 < nan` is False, "
        f"first arg wins). The occlusion is read as the MAX height score "
        f"(1.0), inflating the GOE total by ~+0.20 (height weight 0.20). A "
        f"jump with one occluded keypoint scores HIGHER than the same jump "
        f"with all keypoints visible — the occlusion is rewarded. This is the "
        f"INVERSE polarity of BJ/BL/BM (NaN → worst 0.0): here NaN → best 1.0, "
        f"same #454 trap as BN (`compute_hard_landing`). The fix must use "
        f"`np.nan_to_num(rel_height / 1.0, nan=0.0)` (NaN → neutral, not best) "
        f"or guard `rel_height` before the min. (Sanity: all-valid GOE = "
        f"{goe_valid:.3f}, NaN GOE = {goe_nan:.3f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 4: occluding LKNEE vs RKNEE must give the same rel_height —
# symmetric in which side is occluded.
# --------------------------------------------------------------------------- #


def test_nan_knee_rel_height_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE on the takeoff window must
    give the same rel_height — both poison the CoM weighted sum identically
    (one NaN term). The metric must be symmetric in which side is occluded.

    RED now: both give `rel_height = nan` (symmetric today, both NaN/BUGGY).
    This is a regression guard that PASSES today (both nan) and must keep
    passing after the fix (both should report the same graceful-degradation
    value, close to the all-valid rel_height). It locks the symmetry
    contract so a fix that only handles one side does not pass.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    poses_r = _jump_pose("rknee")
    poses_l = _jump_pose(None)
    poses_l[2, H36Key.LKNEE] = [np.nan, np.nan]
    poses_l[3, H36Key.LKNEE] = [np.nan, np.nan]

    v_right_nan = analyzer.compute_relative_jump_height(poses_r, _phases())
    v_left_nan = analyzer.compute_relative_jump_height(poses_l, _phases())

    # Both NaN today (symmetric); after the fix both should be the same finite
    # graceful-degradation value. The symmetry contract must hold either way.
    both_nan = np.isnan(v_right_nan) and np.isnan(v_left_nan)
    both_finite_close = (np.isfinite(v_right_nan) and np.isfinite(v_left_nan)
                         and abs(v_right_nan - v_left_nan) < 0.05)
    assert both_nan or both_finite_close, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different rel_height "
        f"({v_left_nan:.3f} vs {v_right_nan:.3f}). Both poison the CoM weighted "
        f"sum identically (one NaN term) — the metric must be symmetric in "
        f"which side is occluded. A fix that only handles one side would break "
        f"this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid jump still reports a finite positive rel_height.
# --------------------------------------------------------------------------- #


def test_all_valid_rel_height_unchanged_repro():
    """Regression guard: an all-valid jump must still report a finite positive
    rel_height (~0.98). The fix (NaN-aware CoM / np.nanmin) must not change
    the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    v = analyzer.compute_relative_jump_height(_jump_pose(None), _phases())
    assert np.isfinite(v) and v > 0.5, (
        f"BUG (regression): all-valid jump reported rel_height {v:.3f}, "
        f"expected a finite positive value (~0.98). The no-NaN case must be "
        f"unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — min(1.0, rel_height / 1.0) in GOE +
# unguarded CoM displacement in compute_relative_jump_height + plain weighted
# sum in calculate_com_trajectory.
# --------------------------------------------------------------------------- #


def test_relative_jump_height_nan_unsafe_source_repro():
    """Source check: `compute_relative_jump_height` computes
    `takeoff_com = com_trajectory[phases.takeoff]` and
    `peak_com = np.min(flight_com)` (NOT `np.nanmin` — propagates NaN) and
    `com_displacement = float(takeoff_com - peak_com)` (no NaN guard) and
    `return com_displacement / avg_spine` (no NaN guard) — root cause of the
    NaN rel_height. And `compute_goe_score` computes
    `height_score = min(1.0, rel_height / 1.0)` (Python min — NaN-unsafe,
    arg-order-dependent, #454: `min(1.0, nan) = 1.0`) — root cause of the
    false BEST height_score. Root cause locked.

    RED now: the unguarded lines and the `min(1.0, rel_height / 1.0)` line
    are present (PASS — root cause locked). After the fix: a NaN guard
    appears on `takeoff_com` / `peak_com` (or `np.nanmin`) and/or the min
    becomes NaN-safe — this test FAILS, signaling the observable tests above
    should flip to GREEN.
    """
    rel_src = inspect.getsource(BiomechanicsAnalyzer.compute_relative_jump_height)
    # The unguarded CoM displacement line is present.
    assert "com_displacement = float(takeoff_com - peak_com)" in rel_src, (
        "BUG: compute_relative_jump_height must compute "
        "`com_displacement = float(takeoff_com - peak_com)` (no NaN guard) "
        "for this repro to be valid. If a NaN guard was added (e.g. "
        "`if not np.isfinite(takeoff_com): return <sentinel>`), the "
        "NaN-rel-height bug is fixed — update the observable tests to the "
        "GREEN contract."
    )
    # The std np.min (NOT nanmin) is present — propagates NaN.
    assert "peak_com = np.min(flight_com)" in rel_src, (
        "BUG: compute_relative_jump_height must compute "
        "`peak_com = np.min(flight_com)` (NaN-propagating, not `np.nanmin`) "
        "for this repro to be valid. If it was changed to `np.nanmin(flight_"
        "com)`, the NaN-poisons-min bug is fixed — update the observable "
        "tests to the GREEN contract."
    )
    assert "np.nanmin" not in rel_src, (
        "BUG: compute_relative_jump_height now uses `np.nanmin` — the "
        "NaN-poisons-min bug is fixed; update the observable tests to the "
        "GREEN contract."
    )
    assert "np.isfinite" not in rel_src and "np.isnan" not in rel_src, (
        "BUG: a NaN guard (`np.isfinite` / `np.isnan`) appeared in "
        "compute_relative_jump_height — the NaN-rel-height bug is fixed; "
        "update the observable tests to the GREEN contract."
    )

    # The GOE height_score min(1.0, nan) = 1.0 arg-order trap is present.
    goe_src = inspect.getsource(BiomechanicsAnalyzer.compute_goe_score)
    assert "height_score = min(1.0, rel_height / 1.0)" in goe_src, (
        "BUG: compute_goe_score must compute "
        "`height_score = min(1.0, rel_height / 1.0)` (Python min — NaN-unsafe, "
        "arg-order-dependent, #454: min(1.0, nan) = 1.0) for this repro to be "
        "valid. If it was changed to a NaN-safe form (e.g. `np.nan_to_num`, "
        "`np.clip` with a NaN guard), the arg-order-NaN bug is fixed — update "
        "the observable tests to the GREEN contract."
    )

    # And the CoM trajectory is a plain weighted sum (no NaN masking) —
    # proving a NaN keypoint poisons the CoM. Same root cause as BM/BN.
    com_src = inspect.getsource(calculate_com_trajectory)
    assert "np.isnan" not in com_src and "np.isfinite" not in com_src and \
        "nanmean" not in com_src and "nansum" not in com_src, (
        "BUG: calculate_com_trajectory now has a NaN-aware path "
        "(np.isnan / np.isfinite / nanmean / nansum) — the CoM NaN-propagation "
        "bug is fixed at the source; update the observable tests to the GREEN "
        "contract. (This would also fix every CoM-based metric — smoothness "
        "BM, hard_landing BN, peak_com — at once.)"
    )