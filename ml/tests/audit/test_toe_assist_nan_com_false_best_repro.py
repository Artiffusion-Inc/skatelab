"""RED repro — `BiomechanicsAnalyzer.compute_toe_assist_proxy` computes the
CoM vertical-velocity acceleration (jerk) around the landing frame, then
`score = max(0.0, min(1.0, 1.0 + peak_decel / 5.0))`. The CoM trajectory
(`calculate_com_trajectory`) is a weighted sum of ALL 17 keypoint
Y-coordinates; a NaN keypoint on the landing frame (or landing-1) makes the
CoM NaN, `vy_y = nan`, `ay = np.diff([..., nan, ...]) = nan`,
`peak_decel = np.min(ay) = nan` (NumPy propagates NaN), `1.0 + nan/5.0 = nan`,
and Python `min(1.0, nan) = 1.0` (NaN-unsafe and arg-order-dependent, #454:
`min(1.0, nan) = 1.0` because `1.0 < nan` is False, FIRST arg wins; `min(nan,
1.0) = nan`). Then `max(0.0, 1.0) = 1.0`. So a TOE-ASSIST landing (hard impact
spike, `peak_decel` very negative → score should be 0.0 = toe assist) with
ONE occluded keypoint on the landing frame is reported as the BEST score
(1.0 = perfectly clean edge), not as "no data" — a false diagnosis (tranche BQ).

This is the INVERSE of BJ/BL/BM (NaN → worst 0.0); `compute_toe_assist_proxy`
reads NaN as the BEST score (`max(0.0, min(1.0, 1.0 + nan/5.0)) = max(0.0,
1.0) = 1.0`), the SAME polarity as BN (`compute_hard_landing` reads NaN as
best 1.0 via `min(1.0, nan) = 1.0`). Same #454 arg-order trap. A NaN keypoint
masks a real toe-assist landing as a "perfectly clean edge" — the inverse
diagnosis.

`compute_toe_assist_proxy` (ml/src/analysis/metrics.py:1013-1051):

    com_trajectory = calculate_com_trajectory(poses)
    vy_y = -(com_trajectory[1:] - com_trajectory[:-1]) * fps
    landing_idx = phases.landing
    post_end = min(landing_idx + 3, len(vy_y))
    start_idx = max(0, landing_idx - 1)
    ay = np.diff(vy_y[start_idx:post_end])
    peak_decel = np.min(ay)            # NaN-propagating min
    score = max(0.0, min(1.0, 1.0 + peak_decel / 5.0))
    return float(score)

`calculate_com_trajectory` (geometry.py:287-335) — weighted sum of all 17
keypoint Y-coordinates. Any NaN keypoint → `com_y[frame] = nan`.

When a keypoint is NaN on the landing frame (or landing-1, both in the
`start_idx:post_end` window):
  - `com_trajectory[landing] = nan` (or `com_trajectory[landing-1] = nan`)
  - `vy_y[landing-1] = -(nan - x) * fps = nan` (or the adjacent diff is nan)
  - `ay = np.diff([..., nan, ...]) = nan`
  - `peak_decel = np.min(ay) = nan`
  - `1.0 + nan / 5.0 = nan`
  - `min(1.0, nan) = 1.0`  ← Python min is NaN-unsafe and arg-order-dependent
                              (#454): `min(1.0, nan) = 1.0` (first arg, because
                              `1.0 < nan` is False); `min(nan, 1.0) = nan`.
  - `max(0.0, 1.0) = 1.0`  ← score = 1.0 (BEST = perfectly clean edge)

Reproduced (12 frames, fps=30, waltz_jump; landing=7; HARD impact landing —
CoM spikes sharply at frame 7 (all keypoints shift down +0.15 at frame 7) →
`peak_decel` very negative → score = 0.0 toe assist):

    all-valid hard impact landing         → score = 0.0  (correct: toe assist)
    NaN knee on landing+landing-1 frames  → score = 1.0  (BUG: hard impact read
                                                          as clean edge/best)

Consequences (prod impact — toe_assist feeds the landing-quality composite,
the GOE landing_score, gamification):
  1. `analyze()` (metrics.py:313-319) emits `toe_assist_proxy` with
     `value=1.0`; the `is_good` gate → 1.0 in range → `is_good=True`. A
     toe-assist landing with one occluded keypoint reads as "perfectly clean
     edge" — a false good metric. The inverse polarity of BJ/BL/BM.
  2. `compute_landing_quality_score` (metrics.py:1550-1552) averages
     `hard_landing` with smoothness/stability/toe_assist
     (`(landing_smooth + landing_stab + hard_landing + toe_assist) / 4.0`);
     a false 1.0 inflates the composite for a toe-assist landing, masking a
     real edge-quality problem. Same composite as BN.
  3. The GOE grader's landing_score (metrics.py:1548) weights
     `landing_score * 0.25`; a false 1.0 toe_assist inflates GOE.
  4. The CoM-weighted-sum means the bug triggers on NaN in ANY of the 17
     keypoints on the landing frame (or landing-1) — wide blast radius, same
     as BM/BN/BP (`compute_landing_smoothness`/`compute_hard_landing`/
     `compute_relative_jump_height`).
  5. Existing tests miss it: `test_compute_toe_assist_proxy` (test_metrics.py:715)
     feeds all-valid keypoints and only asserts `0.0 <= score <= 1.0` (a
     range check, not a content check). No test feeds a NaN keypoint through
     the CoM into the toe-assist score. The `min(1.0, nan) = 1.0` arg-order
     trap (#454) is not exercised on this method.

The fix (NOT applied — repro only): make the metric NaN-aware. Either:
  - mask NaN before the score: `if not np.isfinite(peak_decel): return <sentinel>`
    (e.g. return 0.5 "no data", or NaN, or skip); or
  - use `np.nanmin(ay)` (NaN-safe min over the finite frames) and a NaN guard
    on the result; and
  - replace `max(0.0, min(1.0, 1.0 + peak_decel / 5.0))` with
    `np.nan_to_num(1.0 + peak_decel / 5.0, nan=<neutral>)` and clip with
    `np.clip` (NaN-aware).
  - The deeper fix is in `calculate_com_trajectory` (NaN-aware CoM — mask NaN
    keypoints, renormalize masses over valid keypoints per frame), which
    fixes every CoM-based metric (smoothness BM, hard_landing BN,
    relative_jump_height BP, toe_assist BQ, peak_com) at once — same
    root-cause approach as fixing `angle_3pt_rad` for the knee-angle callers
    (BH/BK/BI).

The correct contract: a NaN keypoint on the landing frame must NOT read as
the BEST toe-assist score (1.0 = clean edge). The metric must skip the NaN
frame (or return a neutral/degraded sentinel) and NOT inflate the
landing-quality composite or mask a real toe-assist landing.

RED now: the observable assertions below describe the CORRECT behavior — a
toe-assist landing with one occluded keypoint must NOT report the best score
(1.0); it must degrade gracefully (close to the all-valid toe-assist score
0.0, or a neutral sentinel). They FAIL because `min(1.0, nan) = 1.0` then
`max(0.0, 1.0) = 1.0`. After the fix: the NaN is handled and the score does
not inflate to 1.0. The source-check test confirms the
`max(0.0, min(1.0, 1.0 + peak_decel / 5.0))` line is present (root cause
locked).

Pure-Python (no GPU, no DB): `compute_toe_assist_proxy` and
`calculate_com_trajectory` are pure-data functions over a poses array.
"""

import inspect

import numpy as np

from src.analysis.element_defs import ELEMENT_DEFS
from src.analysis.metrics import BiomechanicsAnalyzer
from src.utils.geometry import calculate_com_trajectory
from src.types import ElementPhase, H36Key


def _toe_assist_pose(nan_keypoint: str | None = None, n: int = 12) -> np.ndarray:
    """A 12-frame pose sequence with a TOE-ASSIST landing — the body
    ACCELERATES downward across the landing frames (frames 7 then 8 shift
    down by increasing amounts), so the CoM vertical velocity becomes more
    negative each frame → `ay = np.diff(vy_y)` has a large negative value →
    `peak_decel = np.min(ay) ≈ -6.9` → `score = max(0, min(1, 1 + (-6.9)/5))
    = 0.0` (toe assist). A sustained shift (one spike then constant) would
    give `ay = [+recovery, 0, 0]`, `min = 0`, `score = 1.0` (clean edge) —
    wrong fixture; the acceleration must continue through the window.

    Shift schedule (all keypoints shift together → CoM shifts identically,
    since the CoM weights sum to 1):
      frame 6: Y += 0.00     (com[6] = base)
      frame 7: Y += 0.07     (com[7] = base + 0.07 → vy_y[6] = -2.1)
      frame 8: Y += 0.37     (com[8] = base + 0.37 → vy_y[7] = -9.0)
      frames 9-11: Y += 0.37 (constant → vy_y[8:] = 0)
    Window `vy_y[6:10] = [-2.1, -9.0, 0, 0]`, `ay = [-6.9, +9, 0]`,
    `min(ay) = -6.9` → score = 0.0.

    When `nan_keypoint` is set, that keypoint is NaN on frames 6 and 7
    (landing-1 and landing) — the occlusion case. The CoM of those frames is
    NaN (`calculate_com_trajectory` is a weighted sum over all 17 keypoints)
    → `vy_y[6] = vy_y[7] = nan` → `ay = [nan, nan, 0]` →
    `np.min(ay) = nan` (NumPy propagates NaN) → `1.0 + nan/5.0 = nan` →
    Python `min(1.0, nan) = 1.0` (#454 arg-order) → `max(0.0, 1.0) = 1.0` →
    score = 1.0 (best/clean edge, BUG).
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
    # Toe-assist landing: accelerating downward shift across frames 7,8.
    shifts = {7: 0.07, 8: 0.37}
    for f in range(7, n):
        poses[f, :, 1] += shifts.get(f, 0.37)
    if nan_keypoint:
        kp = {"rknee": H36Key.RKNEE, "rwrist": H36Key.RWRIST,
              "lfoot": H36Key.LFOOT}[nan_keypoint]
        # NaN on landing frame AND landing-1 (both feed the vy_y diff window).
        poses[6, kp] = [np.nan, np.nan]
        poses[7, kp] = [np.nan, np.nan]
    return poses


def _phases(n: int = 12):
    return ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=4,
                        landing=7, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: a toe-assist landing with one occluded keypoint must NOT
# report the BEST score (1.0); it must degrade gracefully (close to the
# all-valid toe-assist score 0.0, or a neutral sentinel).
# --------------------------------------------------------------------------- #


def test_nan_knee_toe_assist_does_not_report_best_score_repro():
    """CORRECT behavior: a TOE-ASSIST landing (CoM spikes sharply at the
    landing frame → `peak_decel` very negative → score should be 0.0 = toe
    assist) with ONE occluded knee keypoint on the landing frame must not be
    reported as the BEST score (1.0 = perfectly clean edge). The metric must
    degrade gracefully — return a neutral/degraded sentinel, or skip the NaN
    frame — and NOT inflate to 1.0. It must NOT return 1.0 (a false "perfectly
    clean edge" diagnosis that masks a real toe-assist landing).

    RED now: `RKNEE` NaN on frames 6 and 7 → `calculate_com_trajectory` is a
    weighted sum over all 17 keypoints, so the CoM of those frames is NaN →
    `vy_y = -(nan - nan) * fps = nan` → `ay = np.diff([..., nan, ...]) = nan`
    → `peak_decel = np.min(ay) = nan` → `1.0 + nan/5.0 = nan` → Python
    `min(1.0, nan) = 1.0` (NaN-unsafe arg-order, #454: `min(1.0, nan) = 1.0`
    because `1.0 < nan` is False, first arg wins) → `max(0.0, 1.0) = 1.0`. A
    toe-assist landing reads as the BEST score (1.0). After the fix: the NaN
    is handled and the score does not inflate to 1.0.

    This is the INVERSE polarity of BJ/BL/BM (NaN → worst 0.0); here NaN →
    best 1.0, same #454 trap as BN (`compute_hard_landing`).
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    # Baseline: all-valid toe-assist landing → score should be ~0.0 (toe assist).
    s_valid = analyzer.compute_toe_assist_proxy(_toe_assist_pose(None), _phases(), fps=30.0)
    assert s_valid < 0.1, (
        f"test fixture broken: all-valid toe-assist landing reported score "
        f"{s_valid:.3f}, expected ~0.0 (toe assist). The fixture needs a sharp "
        f"CoM spike at the landing frame (all keypoints shift down at frame 7) "
        f"so `peak_decel` is very negative and the all-valid baseline is ~0.0 — "
        f"otherwise the NaN-vs-valid contrast is meaningless."
    )

    # One occluded knee on landing+landing-1 — same toe-assist landing, one NaN.
    s_nan = analyzer.compute_toe_assist_proxy(_toe_assist_pose("rknee"), _phases(), fps=30.0)

    # CORRECT contract: the occluded-keypoint score must NOT be 1.0 (best).
    # It must be close to the all-valid toe-assist score (graceful degradation)
    # or a neutral sentinel — NOT a false "perfectly clean edge" 1.0 that
    # masks a real toe-assist landing.
    assert s_nan < 0.7, (
        f"BUG: compute_toe_assist_proxy returned {s_nan:.3f} for a TOE-ASSIST "
        f"landing (all-valid score = {s_valid:.3f}, expected ~0.0) with a NaN "
        f"RKNEE on the landing+landing-1 frames (occlusion). "
        f"`calculate_com_trajectory` is a weighted sum over ALL 17 keypoints, "
        f"so one NaN keypoint makes the CoM NaN for those frames; "
        f"`vy_y = -(nan - nan) * fps = nan`; `ay = np.diff([..., nan, ...]) = "
        f"nan`; `peak_decel = np.min(ay) = nan`; `1.0 + nan/5.0 = nan`; Python "
        f"`min(1.0, nan) = 1.0` (arg-order NaN-unsafe, #454: min(1.0, nan) = 1.0 "
        f"because 1.0 < nan is False, first arg wins); `max(0.0, 1.0) = 1.0`. A "
        f"toe-assist landing reads as the BEST score (1.0) — a false 'perfectly "
        f"clean edge' diagnosis when the truth is 'no data for that frame'. The "
        f"metric confuses occlusion with a clean edge, masking a real "
        f"toe-assist landing. This is the INVERSE polarity of BJ/BL/BM "
        f"(NaN → worst 0.0): here NaN → best 1.0, same #454 arg-order trap as "
        f"BN (`compute_hard_landing`). (Sanity: all-valid score = "
        f"{s_valid:.3f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint (CoM weighted sum),
# not just the knee — a NaN wrist also inflates the score to 1.0.
# --------------------------------------------------------------------------- #


def test_nan_wrist_toe_assist_does_not_report_best_score_repro():
    """CORRECT behavior: a toe-assist landing with one occluded WRIST on the
    landing frame must also not report the best score. The CoM weighted sum
    includes the arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist
    poisons the CoM the same way as a NaN knee. The bug has a wide blast
    radius — ANY of the 17 keypoints, same as BM/BN/BP.

    RED now: `RWRIST` NaN → CoM NaN → `vy_y = nan` → `min(1.0, nan) = 1.0` →
    `max(0.0, 1.0) = 1.0`. After the fix: graceful degradation on any occluded
    keypoint.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    s_nan = analyzer.compute_toe_assist_proxy(_toe_assist_pose("rwrist"), _phases(), fps=30.0)

    assert s_nan < 0.7, (
        f"BUG: compute_toe_assist_proxy returned {s_nan:.3f} for a TOE-ASSIST "
        f"landing with a NaN RWRIST on the landing+landing-1 frames. The CoM "
        f"weighted sum includes the arms (r_forearm = (RELBOW + RWRIST) / 2), "
        f"so a NaN wrist poisons the CoM the same way as a NaN knee. The bug "
        f"has a wide blast radius — ANY of the 17 keypoints, not just the knee. "
        f"A fix that only guards the knee (or only the legs) would leave the "
        f"arm/head keypoints broken. The root-cause fix is NaN-aware CoM "
        f"(`calculate_com_trajectory`) or `np.nanmin` + a NaN guard on "
        f"`peak_decel`."
    )


# --------------------------------------------------------------------------- #
# Observable 3: occluding LKNEE vs RKNEE must give the same toe-assist score
# — symmetric in which side is occluded.
# --------------------------------------------------------------------------- #


def test_nan_knee_toe_assist_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE on the landing frames must
    give the same toe-assist score — both poison the CoM weighted sum
    identically. The metric must be symmetric in which side is occluded.

    RED now: both give `min(1.0, nan) = 1.0` → `max(0.0, 1.0) = 1.0`
    (symmetric today, both best/BUGGY). This is a regression guard that
    PASSES today (both 1.0) and must keep passing after the fix (both should
    report the same graceful-degradation value, close to 0.0). It locks the
    symmetry contract so a fix that only handles one side does not pass.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    poses_r = _toe_assist_pose("rknee")
    poses_l = _toe_assist_pose(None)
    poses_l[6, H36Key.LKNEE] = [np.nan, np.nan]
    poses_l[7, H36Key.LKNEE] = [np.nan, np.nan]

    s_right_nan = analyzer.compute_toe_assist_proxy(poses_r, _phases(), fps=30.0)
    s_left_nan = analyzer.compute_toe_assist_proxy(poses_l, _phases(), fps=30.0)

    assert abs(s_right_nan - s_left_nan) < 0.02, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different toe-assist "
        f"scores ({s_left_nan:.3f} vs {s_right_nan:.3f}). Both poison the CoM "
        f"weighted sum identically (one NaN term) — the metric must be "
        f"symmetric in which side is occluded. A fix that only handles one "
        f"side would break this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid toe-assist landing still reports ~0.0.
# --------------------------------------------------------------------------- #


def test_all_valid_toe_assist_unchanged_repro():
    """Regression guard: an all-valid toe-assist landing must still report
    score ~0.0 (toe assist). The fix (NaN guard / NaN-aware CoM) must not
    change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    s = analyzer.compute_toe_assist_proxy(_toe_assist_pose(None), _phases(), fps=30.0)
    assert s < 0.1, (
        f"BUG (regression): all-valid toe-assist landing reported score "
        f"{s:.3f}, expected ~0.0 (toe assist). The no-NaN case must be "
        f"unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — max(0.0, min(1.0, 1.0 + peak_decel / 5.0))
# --------------------------------------------------------------------------- #


def test_toe_assist_nan_unsafe_source_repro():
    """Source check: `compute_toe_assist_proxy` computes
    `peak_decel = np.min(ay)` (NOT `np.nanmin` — propagates NaN) and
    `score = max(0.0, min(1.0, 1.0 + peak_decel / 5.0))` (Python min/max —
    NaN-unsafe, arg-order-dependent, #454: `min(1.0, nan) = 1.0`, then
    `max(0.0, 1.0) = 1.0`). Root cause locked.

    RED now: the np.min (not nanmin) line and the
    `max(0.0, min(1.0, 1.0 + peak_decel / 5.0))` line are present (PASS — root
    cause locked). After the fix: the min becomes `np.nanmin` (or a NaN guard)
    and/or the max/min becomes NaN-safe — this test FAILS, signaling the
    observable tests above should flip to GREEN.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_toe_assist_proxy)
    # The np.min (NOT nanmin) line is present — propagates NaN.
    assert "peak_decel = np.min(ay)" in src, (
        "BUG: compute_toe_assist_proxy must compute "
        "`peak_decel = np.min(ay)` (NaN-propagating, not `np.nanmin`) for this "
        "repro to be valid. If it was changed to `np.nanmin(ay)` (or a NaN "
        "mask), the NaN-poisons-min bug is fixed — update the observable tests "
        "to the GREEN contract."
    )
    assert "np.nanmin" not in src, (
        "BUG: compute_toe_assist_proxy now uses `np.nanmin` — the "
        "NaN-poisons-min bug is fixed; update the observable tests to the "
        "GREEN contract."
    )
    # The Python max/min clamp line is present — NaN-unsafe, arg-order.
    assert "max(0.0, min(1.0, 1.0 + peak_decel / 5.0))" in src, (
        "BUG: compute_toe_assist_proxy must compute "
        "`max(0.0, min(1.0, 1.0 + peak_decel / 5.0))` (Python min/max — "
        "NaN-unsafe, arg-order-dependent, #454: min(1.0, nan) = 1.0, then "
        "max(0.0, 1.0) = 1.0) for this repro to be valid. If it was changed to "
        "a NaN-safe form (e.g. `np.nan_to_num`, `np.clip` with a NaN guard), "
        "the arg-order-NaN bug is fixed — update the observable tests to the "
        "GREEN contract."
    )
    assert "np.isfinite" not in src and "np.isnan" not in src, (
        "BUG: a NaN guard (`np.isfinite` / `np.isnan`) appeared in "
        "compute_toe_assist_proxy — the NaN-inflate bug is fixed; update the "
        "observable tests to the GREEN contract."
    )

    # And the CoM trajectory is a plain weighted sum (no NaN masking) —
    # proving a NaN keypoint poisons the CoM. Same root cause as BM/BN/BP.
    com_src = inspect.getsource(calculate_com_trajectory)
    assert "np.isnan" not in com_src and "np.isfinite" not in com_src and \
        "nanmean" not in com_src and "nansum" not in com_src, (
        "BUG: calculate_com_trajectory now has a NaN-aware path "
        "(np.isnan / np.isfinite / nanmean / nansum) — the CoM NaN-propagation "
        "bug is fixed at the source; update the observable tests to the GREEN "
        "contract. (This would also fix every CoM-based metric — smoothness "
        "BM, hard_landing BN, relative_jump_height BP, peak_com — at once.)"
    )