"""RED repro — `BiomechanicsAnalyzer.compute_approach_direction_change`
computes the 2D CoM trajectory over the approach phase, then sums the
absolute frame-to-frame change in the CoM heading angle:

    com = calculate_com_trajectory_2d(approach_poses)
    vx = np.gradient(com[:, 0]) * fps
    angles = np.degrees(np.arctan2(vx, np.ones_like(vx)))
    return float(np.sum(np.abs(np.diff(angles))))

`calculate_com_trajectory_2d` (geometry.py:388-435) is a weighted sum of
ALL 17 keypoint (x, y) coordinates. Any NaN keypoint on an approach frame →
`com[frame] = [nan, nan]` → `np.gradient(com[:, 0])` has NaN →
`np.arctan2(nan, 1.0) = nan` → `np.diff([..., nan, ...]) = nan` →
`np.sum(np.abs(nan)) = nan`. The metric returns `nan` (NaN-leak, not a
clamped false-best/worst).

The NaN then propagates to the GOE grader (metrics.py:1559-1561):

    approach_change = self.compute_approach_direction_change(poses, phases, fps)
    approach_score = min(1.0, approach_change / 90.0)
    goe = height_score * 0.20 + ... + approach_score * 0.10 + ...
    return float(goe * 10.0)

`approach_change = nan` → `nan / 90.0 = nan` → Python `min(1.0, nan) = 1.0`
(NaN-unsafe and arg-order-dependent, #454: `min(1.0, nan) = 1.0` because
`1.0 < nan` is False, the FIRST arg wins; `min(nan, 1.0) = nan`). So
`approach_score = 1.0` (BEST) for an approach with one occluded keypoint →
the GOE composite is inflated by `0.10 * 1.0 = 0.10` (1.0 on the 0-10 GOE
scale) — a false-good GOE for an occlusion, not for a clean approach (tranche BR).

Two failure modes, same root cause (CoM weighted sum + NaN propagation):
  1. `compute_approach_direction_change` returns `nan` (NaN-leak into the
     `approach_direction_change` MetricResult value at metrics.py:348 —
     `is_good=False` is hardcoded, `reference_range=(0,0)`, so the `is_good`
     gate is unaffected; but the `value=nan` breaks downstream: the GOE
     composite, JSON serialization (NaN is not valid JSON), the recommender,
     and frontend display).
  2. The GOE grader's `approach_score = min(1.0, nan / 90.0) = 1.0` (#454
     arg-order trap) → false BEST approach_score → GOE inflated +1.0. Same
     #454 trap as BN/BP/BQ (`compute_hard_landing` / `compute_relative_jump_height`
     / `compute_toe_assist_proxy`), same root cause `calculate_com_trajectory*`
     plain weighted sum.

Reproduced (12 frames, fps=30, waltz_jump; takeoff=4; curving approach —
`x += 0.001 * f^2` so the heading changes across frames → nonzero valid
direction change):

    all-valid curving approach            → direction_change ≈ 0.43° (finite, correct)
    NaN RKNEE on approach frames 0..4     → direction_change = nan  (BUG: NaN-leak)
    NaN RWRIST on approach frames 0..4   → direction_change = nan  (BUG: any keypoint)
    GOE: all-valid approach_change / 90.0 → approach_score ≈ 0.0048 (small, correct)
    GOE: nan approach_change / 90.0       → approach_score = 1.0    (BUG: false BEST, #454)

Consequences (prod impact — approach_direction_change + GOE composite):
  1. `analyze()` (metrics.py:345-352) emits `approach_direction_change` with
     `value=nan`. NaN is not valid JSON — `json.dumps` with default settings
     emits `NaN` (invalid per RFC 8259; `allow_nan=True` is the default but
     produces non-standard JSON that strict parsers reject). Frontend /
     API consumers may fail to parse, or render `nan`/`null`/error.
  2. The GOE grader (metrics.py:1559-1561) computes `approach_score =
     min(1.0, nan / 90.0) = 1.0` → GOE inflated by 0.10 * 1.0 * 10 = 1.0 on
     the 0-10 scale. A single occluded keypoint on the approach inflates the
     overall GOE — a false-good grade that masks a real approach-curve
     problem. Same GOE-inflation vector as BP (height_score `min(1.0, nan)`).
  3. The CoM-weighted-sum means the bug triggers on NaN in ANY of the 17
     keypoints on ANY approach frame — wide blast radius, same as BM/BN/BP/BQ.
  4. Existing tests miss it: `test_compute_approach_direction_change*`
     feed all-valid keypoints. No test feeds a NaN keypoint through the
     2D CoM into the direction-change sum. The `min(1.0, nan) = 1.0` arg-
     order trap (#454) is not exercised on the GOE `approach_score` line.

The fix (NOT applied — repro only): make the metric NaN-aware. Either:
  - mask NaN before the sum: `finite = np.isfinite(angles)` and
    `return float(np.sum(np.abs(np.diff(angles[finite]))))`, or skip if any
    approach CoM is NaN; or
  - use `np.nansum(np.abs(np.diff(angles)))` (NaN-safe sum); and
  - guard the GOE `approach_score` line: `if not np.isfinite(approach_change):
    approach_score = 0.0` (or neutral), or use `np.nan_to_num(approach_change /
    90.0, nan=0.0)` then `min(1.0, ...)`.
  - The deeper fix is in `calculate_com_trajectory_2d` (NaN-aware CoM — mask
    NaN keypoints, renormalize masses over valid keypoints per frame), which
    fixes every CoM-based metric (smoothness BM, hard_landing BN,
    relative_jump_height BP, toe_assist BQ, approach_direction_change BR,
    peak_com) at once.

The correct contract: a NaN keypoint on an approach frame must NOT leak NaN
into the `approach_direction_change` value, and must NOT inflate the GOE
`approach_score` to 1.0. The metric must skip the NaN frames (`np.nansum` /
NaN mask / sentinel) and the GOE line must guard the NaN.

RED now: the observable assertions below describe the CORRECT behavior — an
approach with one occluded keypoint must return a finite direction change
(close to the all-valid value, or a neutral sentinel), NOT `nan`; and the
GOE `approach_score` must NOT be 1.0 (best) for a NaN approach. They FAIL
because `np.sum(np.abs(np.diff([..., nan, ...]))) = nan` and
`min(1.0, nan / 90.0) = 1.0`. After the fix: the NaN is handled and the
value is finite, the GOE score is not inflated. The source-check test
confirms the unguarded `np.sum(np.abs(np.diff(angles)))` line and the
`min(1.0, approach_change / 90.0)` GOE line are present (root cause locked).

Pure-Python (no GPU, no DB): `compute_approach_direction_change`,
`compute_goe_score`, and `calculate_com_trajectory_2d` are pure-data
functions over a poses array.
"""

import inspect

import numpy as np

from src.analysis.element_defs import ELEMENT_DEFS
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key
from src.utils.geometry import calculate_com_trajectory_2d


def _approach_pose(nan_keypoint: str | None = None, n: int = 12) -> np.ndarray:
    """A 12-frame pose sequence with a CURVING approach — `x += 0.001 * f^2`
    so the CoM x-coordinate accelerates across approach frames (0..takeoff=4),
    the heading angle changes frame-to-frame, and the all-valid direction
    change is nonzero (finite, ~0.43°).

    When `nan_keypoint` is set, that keypoint is NaN on the approach frames
    (0..4) — the occlusion case. `calculate_com_trajectory_2d` is a weighted
    sum over all 17 keypoints, so one NaN keypoint makes the CoM NaN for
    those frames → `np.gradient(com[:,0])` has NaN → `np.arctan2(nan,1)=nan`
    → `np.diff([...,nan,...])=nan` → `np.sum(np.abs(nan))=nan`.
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
    # Curving approach: a quadratic x-drift alone is pure translation (all
    # keypoints shift by the same dx) and does NOT change the heading —
    # arctan2(vy, vx) stays at 0° because vy=0. Add a linear y-drift so the
    # vertical CoM velocity is nonzero and the heading arctan2(vy, vx) actually
    # changes across approach frames (vx grows quadratically, vy stays
    # constant -> heading angle decreases). This makes the all-valid baseline
    # finite and nonzero, which the NaN-vs-valid contrast relies on.
    for f in range(n):
        poses[f, :, 0] += 0.001 * (f**2)
        poses[f, :, 1] += 0.0005 * f
    if nan_keypoint:
        kp = {"rknee": H36Key.RKNEE, "rwrist": H36Key.RWRIST, "lfoot": H36Key.LFOOT}[nan_keypoint]
        # NaN on all approach frames (0..takeoff=4).
        for f in range(0, 5):
            poses[f, kp] = [np.nan, np.nan]
    return poses


def _phases(n: int = 12):
    return ElementPhase(name="waltz_jump", start=0, takeoff=4, peak=6, landing=8, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: an approach with one occluded keypoint must return a FINITE
# direction change (graceful degradation), NOT nan.
# --------------------------------------------------------------------------- #


def test_nan_knee_approach_direction_change_is_finite_repro():
    """CORRECT behavior: an approach with ONE occluded knee keypoint on the
    approach frames must return a FINITE direction change — skip the NaN
    frames (`np.nansum` / NaN mask) and report the change from the valid
    frames, close to the all-valid value, or a neutral sentinel. It must
    NOT return `nan` (a NaN-leak that breaks JSON serialization, the GOE
    composite, the recommender, and frontend display).

    RED now: `RKNEE` NaN on approach frames 0..4 →
    `calculate_com_trajectory_2d` is a weighted sum over all 17 keypoints, so
    the CoM of those frames is NaN → `np.gradient(com[:,0])` has NaN →
    `np.arctan2(nan, 1.0) = nan` → `np.diff([..., nan, ...]) = nan` →
    `np.sum(np.abs(nan)) = nan`. The metric returns `nan`. After the fix: the
    NaN frames are skipped and the value is finite.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    # Baseline: all-valid curving approach → finite nonzero direction change.
    v_valid = analyzer.compute_approach_direction_change(_approach_pose(None), _phases(), fps=30.0)
    assert np.isfinite(v_valid) and v_valid > 0.0, (
        f"test fixture broken: all-valid curving approach reported direction "
        f"change {v_valid}, expected finite > 0. The fixture needs a curving "
        f"x-drift (`x += 0.001 * f^2`) so the heading changes across approach "
        f"frames and the all-valid baseline is nonzero finite — otherwise the "
        f"NaN-vs-valid contrast is meaningless."
    )

    # One occluded knee on approach frames — same curving approach, one NaN.
    v_nan = analyzer.compute_approach_direction_change(_approach_pose("rknee"), _phases(), fps=30.0)

    # CORRECT contract: the occluded-keypoint value must be FINITE (graceful
    # NaN-skip), NOT nan — a NaN-leak breaks JSON, GOE, recommender, frontend.
    assert np.isfinite(v_nan), (
        f"BUG: compute_approach_direction_change returned {v_nan} (nan) for a "
        f"curving approach (all-valid = {v_valid:.4f}°) with a NaN RKNEE on the "
        f"approach frames (occlusion). `calculate_com_trajectory_2d` is a "
        f"weighted sum over ALL 17 keypoints, so one NaN keypoint makes the "
        f"CoM NaN for those frames; `np.gradient(com[:,0])` is NaN; "
        f"`np.arctan2(nan, 1.0) = nan`; `np.diff([..., nan, ...]) = nan`; "
        f"`np.sum(np.abs(nan)) = nan`. The metric returns nan — a NaN-leak "
        f"into the `approach_direction_change` MetricResult value "
        f"(metrics.py:348). NaN is not valid JSON (RFC 8259), breaks strict "
        f"parsers, the recommender, and frontend display. It also propagates "
        f"to the GOE composite — see test_goe_approach_score_nan_not_best_repro. "
        f"(Sanity: all-valid = {v_valid:.4f}°.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint (CoM weighted sum),
# not just the knee — a NaN wrist also leaks nan.
# --------------------------------------------------------------------------- #


def test_nan_wrist_approach_direction_change_is_finite_repro():
    """CORRECT behavior: an approach with one occluded WRIST on the approach
    frames must also return a finite value. The CoM weighted sum includes the
    arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist poisons the CoM
    the same way as a NaN knee. The bug has a wide blast radius — ANY of the
    17 keypoints, same as BM/BN/BP/BQ.

    RED now: `RWRIST` NaN → CoM NaN → gradient NaN → arctan2 NaN → diff NaN →
    sum NaN. After the fix: graceful degradation on any occluded keypoint.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    v_nan = analyzer.compute_approach_direction_change(
        _approach_pose("rwrist"), _phases(), fps=30.0
    )

    assert np.isfinite(v_nan), (
        f"BUG: compute_approach_direction_change returned {v_nan} (nan) for a "
        f"curving approach with a NaN RWRIST on the approach frames. The CoM "
        f"weighted sum includes the arms (r_forearm = (RELBOW + RWRIST) / 2), "
        f"so a NaN wrist poisons the CoM the same way as a NaN knee. The bug "
        f"has a wide blast radius — ANY of the 17 keypoints, not just the "
        f"knee. A fix that only guards the knee (or only the legs) would leave "
        f"the arm/head keypoints broken. The root-cause fix is NaN-aware CoM "
        f"(`calculate_com_trajectory_2d`) or `np.nansum` on the angle diffs."
    )


# --------------------------------------------------------------------------- #
# Observable 3: the GOE `approach_score = min(1.0, approach_change / 90.0)`
# must NOT read a NaN approach_change as the BEST score (1.0) — the #454
# arg-order trap. Same GOE-inflation vector as BP (height_score).
# --------------------------------------------------------------------------- #


def test_goe_approach_score_nan_not_best_repro():
    """CORRECT behavior: the GOE grader computes
    `approach_score = min(1.0, approach_change / 90.0)`. A NaN `approach_change`
    (from one occluded approach keypoint) must NOT read as the BEST
    `approach_score = 1.0` — Python `min(1.0, nan) = 1.0` (#454 arg-order:
    `min(1.0, nan) = 1.0` because `1.0 < nan` is False, first arg wins). The
    GOE must degrade gracefully (neutral approach_score, e.g. 0.0 or skip)
    and NOT inflate by `0.10 * 1.0 * 10 = 1.0` on the 0-10 GOE scale.

    RED now: `RKNEE` NaN on approach → `approach_change = nan` →
    `nan / 90.0 = nan` → `min(1.0, nan) = 1.0` → `approach_score = 1.0` →
    GOE inflated. After the fix: the GOE line guards the NaN (or the metric
    returns finite) and `approach_score` is not 1.0 for an occlusion.

    This is the SAME #454 arg-order trap as BP (`height_score = min(1.0,
    rel_height / 1.0)` → `min(1.0, nan) = 1.0`) and BN/BQ — the GOE composite
    reads NaN as the BEST sub-score. Same root cause: CoM weighted sum +
    unguarded Python `min(1.0, nan)`.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    phases = _phases()

    # Baseline: all-valid GOE is finite.
    goe_valid = analyzer.compute_goe_score(_approach_pose(None), phases, fps=30.0)
    assert np.isfinite(goe_valid), (
        f"test fixture broken: all-valid GOE = {goe_valid}, expected finite."
    )

    # NaN approach keypoint → approach_change = nan → approach_score = 1.0
    # (false BEST) → GOE inflated by ~1.0.
    goe_nan = analyzer.compute_goe_score(_approach_pose("rknee"), phases, fps=30.0)

    # CORRECT contract: the GOE for a NaN approach must NOT be inflated by the
    # false-best approach_score. The all-valid GOE is the ceiling for a clean
    # approach; a NaN approach must not exceed it by the 1.0 inflation.
    # Allow a small tolerance for the other sub-scores' finite contributions.
    assert goe_nan < goe_valid + 1.0, (
        f"BUG: GOE for a NaN approach (one occluded RKNEE) = {goe_nan:.3f}, "
        f"all-valid GOE = {goe_valid:.3f}. `compute_approach_direction_change` "
        f"returns nan (NaN-leak); the GOE grader computes `approach_score = "
        f"min(1.0, nan / 90.0) = 1.0` (Python min NaN-unsafe arg-order, #454: "
        f"min(1.0, nan) = 1.0 because 1.0 < nan is False, first arg wins) → "
        f"approach_score = 1.0 (BEST) for an occlusion → GOE inflated by "
        f"0.10 * 1.0 * 10 = 1.0. A single occluded approach keypoint reads as "
        f"a perfect approach curve — a false-good GOE that masks a real "
        f"approach problem. Same #454 arg-order trap as BP (height_score "
        f"min(1.0, nan) = 1.0) and BN/BQ. (Sanity: all-valid GOE = "
        f"{goe_valid:.3f}, NaN GOE = {goe_nan:.3f}, delta = "
        f"{goe_nan - goe_valid:+.3f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 4: occluding LKNEE vs RKNEE must give the same direction change
# — symmetric in which side is occluded.
# --------------------------------------------------------------------------- #


def test_nan_knee_approach_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE on the approach frames must
    give the same direction change — both poison the CoM weighted sum
    identically. The metric must be symmetric in which side is occluded.

    RED now: both give `nan` (symmetric today, both NaN-leak). This is a
    regression guard that PASSES today (both nan, `np.isfinite(nan)` is False
    so `abs(nan - nan) = nan` which is NOT < 0.02 → this would FAIL today as
    a non-finite diff; but the contract is "both finite and equal"). After
    the fix: both should report the same finite graceful-degradation value.
    It locks the symmetry contract so a fix that only handles one side does
    not pass.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    poses_r = _approach_pose("rknee")
    poses_l = _approach_pose(None)
    for f in range(0, 5):
        poses_l[f, H36Key.LKNEE] = [np.nan, np.nan]

    v_right_nan = analyzer.compute_approach_direction_change(poses_r, _phases(), fps=30.0)
    v_left_nan = analyzer.compute_approach_direction_change(poses_l, _phases(), fps=30.0)

    # Both must be finite (the fix) AND equal — symmetric in which side.
    assert np.isfinite(v_right_nan) and np.isfinite(v_left_nan), (
        f"BUG (symmetry): occluding LKNEE/RKNEE gives non-finite direction "
        f"changes ({v_left_nan} vs {v_right_nan}). Both must be finite (graceful "
        f"NaN-skip) before the symmetry contract can be checked."
    )
    assert abs(v_right_nan - v_left_nan) < 0.02, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different direction "
        f"changes ({v_left_nan:.4f} vs {v_right_nan:.4f}). Both poison the CoM "
        f"weighted sum identically (one NaN term) — the metric must be "
        f"symmetric in which side is occluded. A fix that only handles one "
        f"side would break this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid curving approach still reports a finite,
# nonzero direction change.
# --------------------------------------------------------------------------- #


def test_all_valid_approach_direction_change_unchanged_repro():
    """Regression guard: an all-valid curving approach must still report a
    finite, nonzero direction change. The fix (NaN mask / nansum / NaN-aware
    CoM) must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    v = analyzer.compute_approach_direction_change(_approach_pose(None), _phases(), fps=30.0)
    assert np.isfinite(v) and v > 0.0, (
        f"BUG (regression): all-valid curving approach reported direction "
        f"change {v}, expected finite > 0. The no-NaN case must be unchanged "
        f"by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — np.sum(np.abs(np.diff(angles))) (no NaN
# guard) + GOE min(1.0, approach_change / 90.0).
# --------------------------------------------------------------------------- #


def test_approach_direction_change_nan_unsafe_source_repro():
    """Source check (GREEN contract): the #878 fix is in place.

    Root cause was two-layer:
      1. `compute_approach_direction_change` computed
         `np.sum(np.abs(np.diff(angles)))` (NOT `np.nansum` -- propagates NaN
         from one occluded approach-frame keypoint) with no finite guard, so
         the metric returned nan -- breaking JSON serialization (RFC 8259),
         the GOE composite, the recommender, and frontend display.
      2. `compute_goe_score` computed
         `approach_score = min(1.0, approach_change / 90.0)` (Python min --
         NaN-unsafe, arg-order-dependent, #454: `min(1.0, nan) = 1.0`), so a
         nan approach_change inflated the GOE approach_score to BEST on
         occlusion.
      3. `calculate_com_trajectory_2d` was a plain weighted sum over all 17
         keypoints -- one NaN keypoint poisoned the CoM. Same deep root cause
         as BM/BN/BP/BQ.

    Fix: np.nansum + finite guard (return 0.0 neutral "no direction change"
    when every frame is NaN) in the metric; np.nan_to_num guard before the
    Python min in the GOE line; NaN-aware 2D CoM (mask NaN keypoints to 0, same
    contract as the 1D `calculate_com_trajectory` #871 fix).
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_approach_direction_change)
    assert "np.nansum(np.abs(np.diff(angles)))" in src, (
        "BUG: compute_approach_direction_change must use np.nansum(np.abs(np.diff("
        "angles))) (#878) -- np.sum propagates NaN from one occluded approach-frame "
        "keypoint into the metric value."
    )
    assert "np.sum(np.abs(np.diff(angles)))" not in src, (
        "BUG: compute_approach_direction_change still uses np.sum(np.abs(np.diff("
        "angles))) (NaN-propagating) -- must be np.nansum (#878)."
    )
    assert "np.isfinite(total)" in src, (
        "BUG: compute_approach_direction_change must guard the total with "
        "np.isfinite and return 0.0 (neutral) when every frame is NaN (#878) -- "
        "not nan, which would inflate the GOE approach_score via min(1.0,nan)=1.0."
    )

    goe_src = inspect.getsource(BiomechanicsAnalyzer.compute_goe_score)
    assert "np.nan_to_num(approach_change / 90.0, nan=0.0)" in goe_src, (
        "BUG: compute_goe_score must guard approach_change/90.0 with np.nan_to_num "
        "before the Python min (#878) -- min(1.0, nan) = 1.0 (#454 arg-order) "
        "inflates the GOE approach_score to BEST on occlusion."
    )
    assert "approach_score = min(1.0, approach_change / 90.0)" not in goe_src, (
        "BUG: compute_goe_score still uses the bare Python min(1.0, "
        "approach_change / 90.0) form -- NaN-unsafe arg-order (#454). Must "
        "guard with np.nan_to_num (#878)."
    )

    # The 2D CoM trajectory is NaN-aware -- masks NaN keypoints so a few
    # occluded joints do not poison the CoM. Same deep root-cause fix as the
    # 1D calculate_com_trajectory (#871), applied to the (x, y) trajectory.
    com_src = inspect.getsource(calculate_com_trajectory_2d)
    assert "np.isfinite" in com_src, (
        "BUG: calculate_com_trajectory_2d must mask NaN keypoints (#878) -- the "
        "deep root-cause fix shared across every 2D-CoM-based metric (approach "
        "direction change BR)."
    )
