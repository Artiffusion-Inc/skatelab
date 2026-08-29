"""RED repro — `BiomechanicsAnalyzer.compute_hard_landing` computes the CoM
vertical velocity at the landing frame, then `score = max(0.0, min(1.0, 1.0 -
vy_y / 2.0))`. The CoM trajectory (`calculate_com_trajectory`) is a weighted
sum of ALL keypoint Y-coordinates; a NaN keypoint on the landing frame (or
landing-1) makes the CoM NaN, `vy_y = (nan - ...) * fps = nan`, `1.0 - nan/2.0
= nan`, and Python `min(1.0, nan) = 1.0` (NaN-unsafe and arg-order-dependent,
#454: `min(1.0, nan) = 1.0` because `1.0 < nan` is False, the FIRST operand
wins; `min(nan, 1.0) = nan`). So a HARD landing (vy_y high → score should be
0.0) with ONE occluded keypoint on the landing frame is reported as the BEST
score (1.0 = perfectly soft landing), not as "no data" — a false diagnosis
(tranche BN).

This is the INVERSE of BJ/BL/BM: those metrics read NaN as the WORST score
(`max(0.0, nan) = 0.0`); `compute_hard_landing` reads NaN as the BEST score
(`max(0.0, min(1.0, nan)) = max(0.0, 1.0) = 1.0`). The arg-order trap (#454)
goes both ways — `min(1.0, nan) = 1.0` (first arg wins) but `min(nan, 1.0) =
nan`; `max(0.0, nan) = 0.0` (first arg wins) but `max(nan, 0.0) = nan`. The
hard-landing code writes the literal `max(0.0, min(1.0, 1.0 - vy_y / 2.0))`,
which fixes the NaN to 1.0, not 0.0.

`compute_hard_landing` (ml/src/analysis/metrics.py:980-1011):

    com_trajectory = calculate_com_trajectory(poses)
    vy_y = (com_trajectory[phases.landing] - com_trajectory[phases.landing - 1]) * fps
    score = max(0.0, min(1.0, 1.0 - vy_y / 2.0))
    return float(score)

`calculate_com_trajectory` (geometry.py:287-335) — weighted sum of all 17
keypoint Y-coordinates. Any NaN keypoint → `com_y[frame] = nan`.

When a keypoint is NaN on the landing frame (or landing-1):
  - `com_trajectory[landing] = nan` (or `com_trajectory[landing-1] = nan`)
  - `vy_y = (nan - x) * fps = nan`
  - `1.0 - nan / 2.0 = nan`
  - `min(1.0, nan) = 1.0`  ← Python min is NaN-unsafe and arg-order-dependent
                              (#454): `min(1.0, nan) = 1.0` (first arg, because
                              `1.0 < nan` is False); `min(nan, 1.0) = nan`.
  - `max(0.0, 1.0) = 1.0`  ← score = 1.0 (BEST = perfectly soft landing)

Reproduced (12 frames, fps=30, waltz_jump; landing=7; HARD landing — CoM
drops sharply at frame 7 (all keypoints shift down +0.15 at frame 7) → vy_y
~4 norm/s → score = 0.0 hard):

    all-valid hard landing                       → score = 0.0  (correct: hard)
    NaN knee on landing+landing-1 frames        → score = 1.0  (BUG: hard read
                                                                 as soft/best)

Consequences (prod impact — hard_landing feeds the landing-quality composite,
the GOE fall detector, and gamification):
  1. `analyze()` (metrics.py:309-313) emits `hard_landing` with `value=1.0`;
     the `is_good` gate (e.g. `(0.5, 1.0)`) → 1.0 in range → `is_good=True`.
     A HARD landing with one occluded keypoint reads as "perfectly soft
     landing" — a false good metric. The opposite polarity of BJ/BL/BM.
  2. `compute_landing_quality_score` (metrics.py:1550-1552) averages
     `hard_landing` with smoothness/stability/toe_assist (`(landing_smooth +
     landing_stab + hard_landing + toe_assist) / 4.0`); a false 1.0 inflates
     the composite for a hard landing, masking a real hard impact.
  3. The GOE grader's fall detector (`test_hard_impact_low_smoothness_is_fall`,
     test_goe_grader.py:102) uses `hard_landing` to detect falls: high
     hard_landing → no fall, low hard_landing + low smoothness → fall. A NaN
     keypoint flips a real hard-impact fall to "soft landing, no fall" — a
     missed fall diagnosis. The fall detector is fed bad data.
  4. The CoM-weighted-sum means the bug triggers on NaN in ANY of the 17
     keypoints on the landing frame (or landing-1) — wide blast radius, same
     as BM (`compute_landing_smoothness`).
  5. Existing tests miss it: `test_compute_hard_landing` (test_metrics.py:865)
     and `test_landing_com_velocity_detects_hard_landing` (test_metrics.py:600)
     feed all-valid keypoints. No test feeds a NaN keypoint through the CoM
     into the hard-landing score. The `min(1.0, nan) = 1.0` arg-order trap
     (#454) is not exercised on this method.

The fix (NOT applied — repro only): make the metric NaN-aware. Either:
  - mask NaN before the score: `if not np.isfinite(vy_y): return <sentinel>`
    (e.g. return 0.5 "no data", or NaN, or skip); or
  - use `np.nan_to_num(vy_y, nan=0.0)` (NaN → neutral, not best); and
  - replace `max(0.0, min(1.0, 1.0 - vy_y / 2.0))` with `np.nan_to_num(1.0 -
    vy_y / 2.0, nan=<neutral>)` and clip with `np.clip` (NaN-aware).
  - The deeper fix is in `calculate_com_trajectory` (NaN-aware CoM — mask NaN
    keypoints, renormalize masses over valid keypoints per frame), which fixes
    every CoM-based metric (smoothness BM, hard_landing BN, relative_jump_height,
    peak_com) at once — same root-cause approach as fixing `angle_3pt_rad`.

The correct contract: a NaN keypoint on the landing frame must NOT read as
the BEST hard-landing score (1.0). The metric must skip the NaN frame (or
return a neutral/degraded sentinel) and NOT inflate the landing-quality
composite or mask a real fall.

RED now: the observable assertions below describe the CORRECT behavior — a
hard landing with one occluded keypoint must NOT report the best score (1.0);
it must degrade gracefully (close to the all-valid hard score 0.0, or a
neutral sentinel). They FAIL because `min(1.0, nan) = 1.0` then `max(0.0, 1.0)
= 1.0`. After the fix: the NaN is handled and the score does not inflate to
1.0. The source-check test confirms the `max(0.0, min(1.0, 1.0 - vy_y /
2.0))` line is present (root cause locked).

Pure-Python (no GPU, no DB): `compute_hard_landing` and
`calculate_com_trajectory` are pure-data functions over a poses array.
"""

import inspect

import numpy as np

from src.analysis.element_defs import ELEMENT_DEFS
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key
from src.utils.geometry import calculate_com_trajectory


def _hard_landing_pose(nan_keypoint: str | None = None, n: int = 12) -> np.ndarray:
    """A 12-frame pose sequence with a HARD landing — at frame 7 (landing) ALL
    keypoints shift downward by +0.15 (Y increases downward in normalized
    coords), so the CoM drops sharply at the landing frame → vy_y ~4 norm/s
    → hard_landing score should be 0.0 (hard).

    When `nan_keypoint` is set, that keypoint is NaN on frames 6 and 7
    (landing-1 and landing) — the occlusion case. The CoM of those frames is
    NaN → `vy_y = nan` → `min(1.0, nan) = 1.0` → score = 1.0 (best, BUG).
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
    # Hard landing: shift ALL keypoints down at frame 7+.
    for f in range(7, n):
        poses[f, :, 1] += 0.15
    if nan_keypoint:
        kp = {"rknee": H36Key.RKNEE, "rwrist": H36Key.RWRIST, "lfoot": H36Key.LFOOT}[nan_keypoint]
        # NaN on landing frame AND landing-1 (both feed the backward difference).
        poses[6, kp] = [np.nan, np.nan]
        poses[7, kp] = [np.nan, np.nan]
    return poses


def _phases(n: int = 12):
    return ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=4, landing=7, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: a hard landing with one occluded keypoint must NOT report the
# BEST score (1.0); it must degrade gracefully (close to the all-valid hard
# score 0.0, or a neutral sentinel).
# --------------------------------------------------------------------------- #


def test_nan_knee_hard_landing_does_not_report_best_score_repro():
    """CORRECT behavior: a HARD landing (CoM drops sharply at the landing
    frame → vy_y high → score should be 0.0 hard) with ONE occluded knee
    keypoint on the landing frame must not be reported as the BEST score
    (1.0 = perfectly soft landing). The metric must degrade gracefully —
    return a neutral/degraded sentinel, or skip the NaN frame — and NOT
    inflate to 1.0. It must NOT return 1.0 (a false "perfectly soft landing"
    diagnosis that masks a real hard impact / fall).

    RED now: `RKNEE` NaN on frames 6 and 7 → `calculate_com_trajectory` is a
    weighted sum over all 17 keypoints, so the CoM of those frames is NaN →
    `vy_y = (nan - nan) * fps = nan` → `1.0 - nan/2.0 = nan` → Python
    `min(1.0, nan) = 1.0` (NaN-unsafe arg-order, #454: `min(1.0, nan) = 1.0`
    because `1.0 < nan` is False, first arg wins) → `max(0.0, 1.0) = 1.0`. A
    hard landing reads as the BEST score (1.0). After the fix: the NaN is
    handled and the score does not inflate to 1.0.

    This is the INVERSE polarity of BJ/BL/BM — those read NaN as worst (0.0);
    hard_landing reads NaN as best (1.0). Same #454 arg-order trap, opposite
    direction, because the code uses `min(1.0, nan) = 1.0` (first arg wins) not
    `max(0.0, nan) = 0.0`.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    # Baseline: all-valid hard landing → score should be ~0.0 (hard).
    s_valid = analyzer.compute_hard_landing(_hard_landing_pose(None), _phases(), fps=30.0)
    assert s_valid < 0.1, (
        f"test fixture broken: all-valid hard landing reported score "
        f"{s_valid:.3f}, expected ~0.0 (hard). The fixture needs a sharp CoM "
        f"drop at the landing frame (all keypoints shift down at frame 7) so "
        f"vy_y is high and the all-valid baseline is ~0.0 — otherwise the "
        f"NaN-vs-valid contrast is meaningless."
    )

    # One occluded knee on landing+landing-1 — same hard landing, one NaN.
    s_nan = analyzer.compute_hard_landing(_hard_landing_pose("rknee"), _phases(), fps=30.0)

    # CORRECT contract: the occluded-keypoint score must NOT be 1.0 (best).
    # It must be close to the all-valid hard score (graceful degradation) or a
    # neutral sentinel — NOT a false "perfectly soft landing" 1.0 that masks
    # a real hard impact / fall.
    assert s_nan < 0.7, (
        f"BUG: compute_hard_landing returned {s_nan:.3f} for a HARD landing "
        f"(all-valid score = {s_valid:.3f}, expected ~0.0) with a NaN RKNEE "
        f"on the landing+landing-1 frames (occlusion). `calculate_com_"
        f"trajectory` is a weighted sum over ALL 17 keypoints, so one NaN "
        f"keypoint makes the CoM NaN for those frames; `vy_y = (nan - nan) * "
        f"fps = nan`; `1.0 - nan/2.0 = nan`; Python `min(1.0, nan) = 1.0` "
        f"(arg-order NaN-unsafe, #454: min(1.0, nan) = 1.0 because 1.0 < nan "
        f"is False, first arg wins); `max(0.0, 1.0) = 1.0`. A hard landing "
        f"reads as the BEST score (1.0) — a false 'perfectly soft landing' "
        f"diagnosis when the truth is 'no data for that frame'. The metric "
        f"confuses occlusion with a soft landing, masking a real hard impact "
        f"and the GOE fall detector. This is the INVERSE polarity of "
        f"BJ/BL/BM (NaN → worst 0.0): here NaN → best 1.0, same #454 arg-order "
        f"trap. (Sanity: all-valid score = {s_valid:.3f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint (CoM weighted sum),
# not just the knee — a NaN wrist also inflates the score to 1.0.
# --------------------------------------------------------------------------- #


def test_nan_wrist_hard_landing_does_not_report_best_score_repro():
    """CORRECT behavior: a hard landing with one occluded WRIST on the landing
    frame must also not report the best score. The CoM weighted sum includes
    the arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist poisons the CoM
    the same way as a NaN knee. The bug has a wide blast radius — ANY of the
    17 keypoints, same as BM (compute_landing_smoothness).

    RED now: `RWRIST` NaN → CoM NaN → `vy_y = nan` → `min(1.0, nan) = 1.0` →
    `max(0.0, 1.0) = 1.0`. After the fix: graceful degradation on any occluded
    keypoint.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    s_nan = analyzer.compute_hard_landing(_hard_landing_pose("rwrist"), _phases(), fps=30.0)

    assert s_nan < 0.7, (
        f"BUG: compute_hard_landing returned {s_nan:.3f} for a HARD landing "
        f"with a NaN RWRIST on the landing+landing-1 frames. The CoM weighted "
        f"sum includes the arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN "
        f"wrist poisons the CoM the same way as a NaN knee. The bug has a wide "
        f"blast radius — ANY of the 17 keypoints, not just the knee. A fix "
        f"that only guards the knee (or only the legs) would leave the "
        f"arm/head keypoints broken. The root-cause fix is NaN-aware CoM "
        f"(`calculate_com_trajectory`) or a NaN guard on `vy_y`."
    )


# --------------------------------------------------------------------------- #
# Observable 3: occluding LKNEE vs RKNEE must give the same hard-landing score
# — symmetric in which side is occluded.
# --------------------------------------------------------------------------- #


def test_nan_knee_hard_landing_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE on the landing frames must
    give the same hard-landing score — both poison the CoM weighted sum
    identically. The metric must be symmetric in which side is occluded.

    RED now: both give `min(1.0, nan) = 1.0` → `max(0.0, 1.0) = 1.0`
    (symmetric today, both best/BUGGY). This is a regression guard that
    PASSES today (both 1.0) and must keep passing after the fix (both should
    report the same graceful-degradation value, close to 0.0). It locks the
    symmetry contract so a fix that only handles one side does not pass.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    poses_r = _hard_landing_pose("rknee")
    poses_l = _hard_landing_pose(None)
    poses_l[6, H36Key.LKNEE] = [np.nan, np.nan]
    poses_l[7, H36Key.LKNEE] = [np.nan, np.nan]

    s_right_nan = analyzer.compute_hard_landing(poses_r, _phases(), fps=30.0)
    s_left_nan = analyzer.compute_hard_landing(poses_l, _phases(), fps=30.0)

    assert abs(s_right_nan - s_left_nan) < 0.02, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different hard-landing "
        f"scores ({s_left_nan:.3f} vs {s_right_nan:.3f}). Both poison the CoM "
        f"weighted sum identically (one NaN term) — the metric must be "
        f"symmetric in which side is occluded. A fix that only handles one "
        f"side would break this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid hard landing still reports ~0.0.
# --------------------------------------------------------------------------- #


def test_all_valid_hard_landing_unchanged_repro():
    """Regression guard: an all-valid hard landing must still report score
    ~0.0 (hard). The fix (NaN guard / NaN-aware CoM) must not change the
    no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    s = analyzer.compute_hard_landing(_hard_landing_pose(None), _phases(), fps=30.0)
    assert s < 0.1, (
        f"BUG (regression): all-valid hard landing reported score {s:.3f}, "
        f"expected ~0.0 (hard). The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — max(0.0, min(1.0, 1.0 - vy_y / 2.0))
# --------------------------------------------------------------------------- #


def test_hard_landing_nan_unsafe_source_repro():
    """GREEN source check (#871 fix): `compute_hard_landing` no longer uses the
    NaN-unsafe arg-order trap `max(0.0, min(1.0, 1.0 - vy_y / 2.0))` — a NaN
    guard (`np.isfinite`) on `vy_y` and a NaN-safe clamp (`np.clip`) replaced
    it. And `calculate_com_trajectory` is NaN-aware — a NaN keypoint is masked
    out of the CoM weighted sum instead of poisoning every CoM-based metric.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_hard_landing)
    # The NaN-unsafe arg-order clamp is GONE.
    assert "max(0.0, min(1.0, 1.0 - vy_y / 2.0))" not in src, (
        "#871 RED: the NaN-unsafe `max(0.0, min(1.0, 1.0 - vy_y / 2.0))` clamp "
        "is back — min(1.0, nan)=1.0 then max(0.0,1.0)=1.0 masks a hard impact "
        "as a false soft landing. Use a NaN guard + np.clip."
    )
    # A NaN guard on vy_y is present.
    assert "np.isfinite(vy_y)" in src, (
        "#871 RED: compute_hard_landing must guard vy_y with np.isfinite — if "
        "both landing frames are fully occluded the NaN-aware CoM still yields "
        "NaN vy_y; return a neutral sentinel instead of the arg-order trap."
    )
    # The clamp is NaN-safe (np.clip, not Python min/max).
    assert "np.clip(1.0 - vy_y / 2.0, 0.0, 1.0)" in src, (
        "#871 RED: use np.clip(1.0 - vy_y / 2.0, 0.0, 1.0) — np.clip is "
        "NaN-safe only after the isfinite guard, unlike Python min/max which "
        "is arg-order NaN-unsafe (#454)."
    )

    # calculate_com_trajectory is now NaN-aware — a NaN keypoint is masked,
    # not propagated. Fixes every CoM-based metric (BM, BN, peak_com) at once.
    com_src = inspect.getsource(calculate_com_trajectory)
    assert "np.isfinite" in com_src, (
        "#871 RED: calculate_com_trajectory must be NaN-aware — mask NaN "
        "segment contributions to 0 (np.isfinite) so one occluded keypoint "
        "does not poison the CoM. All-valid stays byte-identical."
    )
