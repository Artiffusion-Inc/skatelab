"""RED repro — `BiomechanicsAnalyzer.compute_landing_com_velocity` computes the
CoM vertical velocity at the landing frame via a backward difference:

    com_trajectory = calculate_com_trajectory(poses)
    velocity = -(com_trajectory[phases.landing] - com_trajectory[phases.landing - 1]) * fps
    return float(velocity)

`calculate_com_trajectory` (geometry.py:287-335) is a weighted sum of ALL 17
keypoint Y-coordinates. A NaN keypoint on the landing frame (or landing-1)
makes the CoM NaN for that frame → `com_trajectory[landing] = nan` (or
`com_trajectory[landing-1] = nan`) → `nan - x = nan` (or `x - nan = nan`) →
`-(nan) * fps = nan` → method returns `nan` (NaN-leak, not a clamped
false-best/worst — tranche BT).

`compute_landing_com_velocity` (ml/src/analysis/metrics.py:906-925):

    if phases.landing <= 0 or phases.landing >= len(poses):
        return 0.0
    com_trajectory = calculate_com_trajectory(poses)
    velocity = -(com_trajectory[phases.landing] - com_trajectory[phases.landing - 1]) * fps
    return float(velocity)

`analyze()` (metrics.py:285-294) emits `landing_com_velocity` with
`value=landing_vel` — `is_good=False` hardcoded, `reference_range=(0,0)`, so
the `is_good` gate is unaffected; but `value=nan` breaks downstream:
  1. **JSON serialization**: NaN is not valid JSON (RFC 8259). `json.dumps`
     with default `allow_nan=True` emits `NaN` (non-standard, strict parsers
     reject). Frontend / API consumers may fail to parse, or render
     `nan`/`null`/error.
  2. **Recommender / fall detector**: `landing_com_velocity` (negative = hard
     landing) is used for landing-quality text and fall detection. `nan > x`
     / `nan < x` are always False → wrong branch → wrong recommendation /
     missed fall.
  3. **Frontend display**: charts/reports render `nan` or crash.

Note: `compute_landing_com_velocity` is NOT in the GOE composite
(`compute_goe_score` uses `compute_hard_landing`, a sibling — covered by
tranche BN, issue #876). So this is a NaN-leak into a user-facing metric, not
a GOE inflation. But it is the SAME root cause: `calculate_com_trajectory`
plain weighted sum + no NaN guard on the velocity / return.

Reproduced (12 frames, fps=30, waltz_jump; landing=7; hard landing — CoM
drops sharply at frame 7 (all keypoints shift down +0.1) → velocity ≈ -3.9
norm/s, negative = hard):

    all-valid hard landing              → velocity = -3.9  (finite, correct)
    NaN RKNEE on landing+landing-1      → velocity = nan   (BUG: NaN-leak)
    NaN RWRIST on landing+landing-1   → velocity = nan   (BUG: any keypoint)

Consequences (prod impact — landing_com_velocity is user-facing, displayed
in reports, feeds the fall detector):
  1. `analyze()` (metrics.py:285-294) emits `landing_com_velocity` value=nan.
     NaN is not valid JSON — breaks strict parsers, frontend, recommender.
  2. The CoM-weighted-sum means the bug triggers on NaN in ANY of the 17
     keypoints on the landing frame (or landing-1) — wide blast radius, same
     as BM/BN/BP/BQ/BR/BS.
  3. Existing tests miss it: `test_landing_com_velocity_detects_hard_landing`
     (test_metrics.py:600) and `test_compute_landing_com_velocity*` feed
     all-valid keypoints. No test feeds a NaN keypoint through the CoM into
     the backward difference. The unguarded
     `-(com_trajectory[landing] - com_trajectory[landing - 1]) * fps` line is
     not exercised on NaN.

The fix (NOT applied — repro only): make the metric NaN-aware. Either:
  - guard the velocity: `v = -(com_trajectory[landing] - com_trajectory[landing - 1]) * fps`;
    `if not np.isfinite(v): return 0.0` (neutral sentinel); or
  - use `np.nan_to_num` on the CoM slice before the diff; or
  - guard the return: `if not np.isfinite(velocity): return 0.0`.
  - The deeper fix is in `calculate_com_trajectory` (NaN-aware CoM — mask NaN
    keypoints, renormalize masses over valid keypoints per frame), which
    fixes every CoM-based metric (smoothness BM, hard_landing BN,
    relative_jump_height BP, toe_assist BQ, approach_direction_change BR,
    jump_height_com BS, landing_com_velocity BT, peak_com) at once.

The correct contract: a NaN keypoint on the landing frame (or landing-1) must
NOT leak NaN into the `landing_com_velocity` value. The metric must skip the
NaN frame (NaN guard / sentinel) and return a finite velocity (or 0.0 "no
data"), NOT nan.

RED now: the observable assertions below describe the CORRECT behavior — a
hard landing with one occluded keypoint must return a FINITE velocity (close
to the all-valid value, or 0.0 / a neutral sentinel), NOT `nan`. They FAIL
because `nan - x = nan` then `-(nan) * fps = nan`. After the fix: the NaN is
handled and the value is finite. The source-check test confirms the
unguarded `-(com_trajectory[phases.landing] - com_trajectory[phases.landing - 1]) * fps`
line and `return float(velocity)` are present (root cause locked).

Pure-Python (no GPU, no DB): `compute_landing_com_velocity` and
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
    keypoints shift downward by +0.1 (Y increases downward in normalized
    coords), so the CoM drops sharply at the landing frame → backward
    difference `-(com[7] - com[6]) * fps` ≈ -3.9 norm/s (negative = hard).

    When `nan_keypoint` is set, that keypoint is NaN on frames 6 and 7
    (landing-1 and landing) — the occlusion case. The CoM of those frames is
    NaN → `nan - x = nan` → `-(nan) * fps = nan` → method returns nan.
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
        poses[f, :, 1] += 0.1
    if nan_keypoint:
        kp = {"rknee": H36Key.RKNEE, "rwrist": H36Key.RWRIST, "lfoot": H36Key.LFOOT}[nan_keypoint]
        # NaN on landing frame AND landing-1 (both feed the backward diff).
        poses[6, kp] = [np.nan, np.nan]
        poses[7, kp] = [np.nan, np.nan]
    return poses


def _phases(n: int = 12):
    return ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=4, landing=7, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: a hard landing with one occluded keypoint must return a FINITE
# CoM velocity (graceful degradation), NOT nan.
# --------------------------------------------------------------------------- #


def test_nan_knee_landing_com_velocity_is_finite_repro():
    """CORRECT behavior: a hard landing with ONE occluded knee keypoint on the
    landing+landing-1 frames must return a FINITE CoM velocity — guard the NaN
    (skip / sentinel) and report a finite value (close to the all-valid value,
    or 0.0 / a neutral sentinel). It must NOT return `nan` (a NaN-leak that
    breaks JSON serialization, the recommender / fall detector, and frontend
    display of `landing_com_velocity`).

    RED now: `RKNEE` NaN on frames 6 and 7 → `calculate_com_trajectory` is a
    weighted sum over all 17 keypoints, so the CoM of those frames is NaN →
    `com_trajectory[landing] = nan` (or `com_trajectory[landing-1] = nan`) →
    `nan - x = nan` (or `x - nan = nan`) → `-(nan) * fps = nan` → method
    returns `nan`. After the fix: the NaN is guarded and the value is finite.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    # Baseline: all-valid hard landing → finite nonzero velocity (negative).
    v_valid = analyzer.compute_landing_com_velocity(_hard_landing_pose(None), _phases(), fps=30.0)
    assert np.isfinite(v_valid) and v_valid < 0.0, (
        f"test fixture broken: all-valid hard landing reported velocity "
        f"{v_valid}, expected finite < 0 (hard = negative downward). The "
        f"fixture needs a sharp CoM drop at the landing frame (all keypoints "
        f"shift down at frame 7) so the all-valid baseline is finite negative "
        f"— otherwise the NaN-vs-valid contrast is meaningless."
    )

    # One occluded knee on landing+landing-1 — same hard landing, one NaN.
    v_nan = analyzer.compute_landing_com_velocity(_hard_landing_pose("rknee"), _phases(), fps=30.0)

    # CORRECT contract: the occluded-keypoint velocity must be FINITE (NaN
    # guard / 0.0 sentinel), NOT nan — a NaN-leak breaks JSON, recommender /
    # fall detector, frontend display of `landing_com_velocity`.
    assert np.isfinite(v_nan), (
        f"BUG: compute_landing_com_velocity returned {v_nan} (nan) for a hard "
        f"landing (all-valid velocity = {v_valid:.3f} norm/s) with a NaN RKNEE "
        f"on the landing+landing-1 frames (occlusion). "
        f"`calculate_com_trajectory` is a weighted sum over ALL 17 keypoints, "
        f"so one NaN keypoint makes the CoM NaN for those frames; "
        f"`com_trajectory[landing] = nan` (or `com_trajectory[landing-1] = "
        f"nan`); `nan - x = nan`; `-(nan) * fps = nan`. The method returns nan "
        f"— a NaN-leak into the `landing_com_velocity` MetricResult value "
        f"(metrics.py:285-294). NaN is not valid JSON (RFC 8259), breaks "
        f"strict parsers, the recommender / fall detector (nan < x is always "
        f"False → missed fall / wrong branch), and frontend display. "
        f"(Sanity: all-valid velocity = {v_valid:.3f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint (CoM weighted sum),
# not just the knee — a NaN wrist also leaks nan.
# --------------------------------------------------------------------------- #


def test_nan_wrist_landing_com_velocity_is_finite_repro():
    """CORRECT behavior: a hard landing with one occluded WRIST on the
    landing+landing-1 frames must also return a finite velocity. The CoM
    weighted sum includes the arms (r_forearm = (RELBOW + RWRIST) / 2), so a
    NaN wrist poisons the CoM the same way as a NaN knee. The bug has a wide
    blast radius — ANY of the 17 keypoints, same as BM/BN/BP/BQ/BR/BS.

    RED now: `RWRIST` NaN → CoM NaN → `nan - x = nan` → `-(nan)*fps = nan`.
    After the fix: graceful degradation on any occluded keypoint.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    v_nan = analyzer.compute_landing_com_velocity(_hard_landing_pose("rwrist"), _phases(), fps=30.0)

    assert np.isfinite(v_nan), (
        f"BUG: compute_landing_com_velocity returned {v_nan} (nan) for a hard "
        f"landing with a NaN RWRIST on the landing+landing-1 frames. The CoM "
        f"weighted sum includes the arms (r_forearm = (RELBOW + RWRIST) / 2), "
        f"so a NaN wrist poisons the CoM the same way as a NaN knee. The bug "
        f"has a wide blast radius — ANY of the 17 keypoints, not just the "
        f"knee. A fix that only guards the knee (or only the legs) would leave "
        f"the arm/head keypoints broken. The root-cause fix is NaN-aware CoM "
        f"(`calculate_com_trajectory`) or a NaN guard on the velocity."
    )


# --------------------------------------------------------------------------- #
# Observable 3: occluding LKNEE vs RKNEE must give the same velocity —
# symmetric in which side is occluded.
# --------------------------------------------------------------------------- #


def test_nan_knee_landing_com_velocity_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE on the landing frames must
    give the same CoM velocity — both poison the CoM weighted sum identically
    (one NaN term). The metric must be symmetric in which side is occluded.

    RED now: both give `nan` (symmetric today, both NaN-leak). This is a
    regression guard that PASSES today only after the fix (both finite and
    equal). It locks the symmetry contract so a fix that only handles one
    side does not pass.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    poses_r = _hard_landing_pose("rknee")
    poses_l = _hard_landing_pose(None)
    poses_l[6, H36Key.LKNEE] = [np.nan, np.nan]
    poses_l[7, H36Key.LKNEE] = [np.nan, np.nan]

    v_right_nan = analyzer.compute_landing_com_velocity(poses_r, _phases(), fps=30.0)
    v_left_nan = analyzer.compute_landing_com_velocity(poses_l, _phases(), fps=30.0)

    # Both must be finite (the fix) AND equal — symmetric in which side.
    assert np.isfinite(v_right_nan) and np.isfinite(v_left_nan), (
        f"BUG (symmetry): occluding LKNEE/RKNEE gives non-finite CoM velocities "
        f"({v_left_nan} vs {v_right_nan}). Both must be finite (NaN guard) "
        f"before the symmetry contract can be checked."
    )
    assert abs(v_right_nan - v_left_nan) < 1e-3, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different CoM "
        f"velocities ({v_left_nan:.4f} vs {v_right_nan:.4f}). Both poison the "
        f"CoM weighted sum identically (one NaN term) — the metric must be "
        f"symmetric in which side is occluded. A fix that only handles one "
        f"side would break this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid hard landing still reports finite negative.
# --------------------------------------------------------------------------- #


def test_all_valid_landing_com_velocity_unchanged_repro():
    """Regression guard: an all-valid hard landing must still report a finite,
    negative CoM velocity (negative = hard). The fix (NaN guard / NaN-aware
    CoM) must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    v = analyzer.compute_landing_com_velocity(_hard_landing_pose(None), _phases(), fps=30.0)
    assert np.isfinite(v) and v < 0.0, (
        f"BUG (regression): all-valid hard landing reported velocity {v}, "
        f"expected finite < 0 (hard = negative). The no-NaN case must be "
        f"unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — unguarded backward diff + no NaN guard.
# --------------------------------------------------------------------------- #


def test_landing_com_velocity_nan_unsafe_source_repro():
    """GREEN contract source check: the NaN-leak bug is fixed in BOTH places.

    `compute_landing_com_velocity` guards the return against a non-finite
    velocity, and `calculate_com_trajectory` masks NaN keypoints so a single
    occluded joint cannot poison the CoM (the source-level fix that also
    repairs smoothness BM / hard_landing BN / relative_jump_height BP /
    toe_assist BQ / approach_direction_change BR / jump_height_com BS).
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_landing_com_velocity)
    # The backward-diff line is present (the metric still uses the CoM delta).
    assert (
        "velocity = -(com_trajectory[phases.landing] - com_trajectory[phases.landing - 1]) * fps"
        in src
    ), (
        "BUG: compute_landing_com_velocity must still compute the backward "
        "difference on the CoM trajectory."
    )
    # The return guards a non-finite velocity — NaN must never leak.
    assert "if not np.isfinite(velocity)" in src and "return 0.0" in src, (
        "BUG: compute_landing_com_velocity must guard the return against a "
        "non-finite velocity (NaN-leak fix, #880)."
    )
    assert "return float(velocity)" in src, (
        "BUG: compute_landing_com_velocity must still return the finite "
        "velocity as a float for the all-valid path."
    )

    # And the CoM trajectory is NaN-aware — masking NaN keypoints so an
    # occluded joint cannot poison the CoM. Same root cause as BM/BN/BP/BQ/BR/BS.
    com_src = inspect.getsource(calculate_com_trajectory)
    assert "np.isfinite" in com_src, (
        "BUG: calculate_com_trajectory must mask NaN keypoints "
        "(np.isfinite) so a single occluded joint cannot NaN-poison the CoM "
        "and leak into landing_com_velocity."
    )
