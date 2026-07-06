"""RED repro — `BiomechanicsAnalyzer.compute_landing_smoothness` computes the
post-landing CoM velocity std, then `smoothness = max(0.0, 1.0 - std_velocity
/ 0.2)`. The CoM trajectory (`calculate_com_trajectory`) is a weighted sum of
ALL keypoint Y-coordinates; a NaN keypoint on ANY post-landing frame makes
the CoM NaN for that frame, the finite-difference velocities NaN,
`np.std(velocities) = nan` (NumPy propagates NaN), `1.0 - nan/0.2 = nan`, and
Python `max(0.0, nan) = 0.0` (NaN-unsafe and arg-order-dependent, #454:
`max(0.0, nan) = 0.0` because `0.0 > nan` is False). So a PERFECTLY smooth
landing (constant CoM, zero velocity std, smoothness should be 1.0) with ONE
occluded keypoint on a post-landing frame is reported as the WORST smoothness
(0.0), not as "no data" — a false diagnosis (tranche BM).

`compute_landing_smoothness` (ml/src/analysis/metrics.py:935-978):

    com_trajectory = calculate_com_trajectory(poses)
    post_com = com_trajectory[post_landing_start:post_landing_end]
    velocities = -(post_com[1:] - post_com[:-1]) * fps
    std_velocity = float(np.std(velocities))
    smoothness = max(0.0, 1.0 - std_velocity / 0.2)
    return float(smoothness)

`calculate_com_trajectory` (geometry.py:287-335) — weighted sum of all 17
keypoint Y-coordinates:

    com_y = (
        head_mass * head[:, 1]
        + torso_mass * torso[:, 1]
        + arm_mass * (l_upper_arm[:, 1] + r_upper_arm[:, 1] + ...)
        + thigh_mass * (l_thigh[:, 1] + r_thigh[:, 1])
        + leg_mass * (l_leg[:, 1] + r_leg[:, 1])
    )

Any NaN keypoint → `com_y[frame] = nan` (NaN propagates through + and *).
Then `post_com` has nan, `post_com[1:] - post_com[:-1]` has nan,
`np.std([..., nan, ...]) = nan`, `1.0 - nan/0.2 = nan`, `max(0.0, nan) = 0.0`.

Reproduced (12 frames, fps=30, waltz_jump; landing=7; post-landing window =
0.5s = 15 frames clipped to 8..11; perfectly STILL body — all frames
identical → CoM constant → velocities ~0 → std ~0 → smoothness = 1.0):

    all-valid still body                       → smoothness = 1.0  (correct)
    one-NaN-knee (RKNEE) on post-landing       → smoothness = 0.0  (BUG)

Consequences (prod impact — landing_smoothness feeds the landing-quality
composite, is_good gate, GOE, recommender, gamification, same chain as
BJ/BK/BL but via a different metric):
  1. `analyze()` (metrics.py:297-300) emits `landing_smoothness` with
     `value=0.0`; the `is_good` gate → 0.0 not in range → `is_good=False`.
     A smooth landing with one occluded keypoint reads as "totally
     unsmooth / wobbly landing" — a false bad metric.
  2. `compute_landing_quality_score` (metrics.py:1557) weights
     `landing_smooth * <weight>` — the 0.0 contributes nothing, deflating the
     composite landing-quality score for an occlusion, not for a wobble.
  3. `_compute_overall_score` (pipeline.py:608-629) counts `is_good`; the
     false `is_good=False` loses a `good_count` point → overall deflated →
     gamification XP (`award_session_xp int(overall)`) and skill unlocks
     penalized for an occlusion, not for performance. Cross-layer with
     #437/#852-class.
  4. The CoM-weighted-sum means the bug triggers on NaN in ANY of the 17
     keypoints (head, shoulders, elbows, wrists, hips, knees, feet) — not
     just the knee. A single occluded wrist on a post-landing frame zeroes
     the smoothness. This is a wide blast radius.
  5. Existing tests miss it: `test_compute_landing_smoothness_*`
     (test_metrics.py:676) and the tranche-F bounds-guard test
     (test_ml_audit_tranche_f_repro.py:102) feed all-valid keypoints. No
     test feeds a NaN keypoint through the CoM trajectory into the smoothness
     std. The `max(0.0, nan) = 0.0` arg-order trap (#454) is not exercised on
     this method.

The fix (NOT applied — repro only): make the metric NaN-aware. Either:
  - mask NaN before the std: `velocities = velocities[np.isfinite(velocities)]`
    and skip if empty; or
  - use `np.nanstd(velocities)` (NaN-safe std over the finite frames); and
  - replace Python `max(0.0, 1.0 - std_velocity / 0.2)` with
    `np.nan_to_num(1.0 - std_velocity / 0.2, nan=1.0)` /
    `np.fmax(0.0, 1.0 - std_velocity / 0.2)` + a NaN guard on `std_velocity`.
  - The deeper fix is in `calculate_com_trajectory`: NaN-aware CoM (mask NaN
    keypoints and renormalize masses over the valid keypoints per frame), so
    the CoM itself does not propagate NaN. That fixes every CoM-based metric
    (smoothness, hard_landing, relative_jump_height, peak_com) at once — the
    same root-cause approach as fixing `angle_3pt_rad` for the knee-angle
    callers (BH/BK/BI).

The correct contract: an occluded keypoint on a post-landing frame must NOT
read as worst smoothness (0.0). The metric must skip the NaN frame
(`np.nanstd` or NaN-mask) and report smoothness from the valid frames, close
to the all-valid case (1.0 for a still body), not 0.0.

RED now: the observable assertions below describe the CORRECT behavior — a
perfectly smooth landing with one occluded keypoint must NOT report worst
smoothness (0.0); it must degrade gracefully (close to 1.0). They FAIL
because `max(0.0, 1.0 - nan/0.2) = 0.0`. After the fix: the NaN frame is
skipped and the smoothness stays near 1.0. The source-check test confirms
the `np.std(velocities)` (not nanstd) + `max(0.0, 1.0 - std_velocity / 0.2)`
lines are present (root cause locked).

Pure-Python (no GPU, no DB): `compute_landing_smoothness` and
`calculate_com_trajectory` are pure-data functions over a poses array.
"""

import inspect

import numpy as np

from src.analysis.element_defs import ELEMENT_DEFS
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key
from src.utils.geometry import calculate_com_trajectory


def _still_pose(nan_keypoint: str | None = None, n: int = 12) -> np.ndarray:
    """A 12-frame pose sequence with a PERFECTLY STILL body — every frame
    identical. CoM is constant across frames → finite-difference velocities
    ~0 → std ~0 → smoothness should be 1.0.

    When `nan_keypoint` is set, that keypoint is NaN on the post-landing
    frames (8..11) — the occlusion case. One keypoint NaN poisons the CoM of
    those frames; the velocity across a NaN-frame boundary is NaN.
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
    if nan_keypoint:
        kp = {"rknee": H36Key.RKNEE, "rwrist": H36Key.RWRIST, "lfoot": H36Key.LFOOT}[nan_keypoint]
        for f in range(8, n):
            poses[f, kp] = [np.nan, np.nan]
    return poses


def _phases(n: int = 12):
    return ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=4, landing=7, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: a perfectly smooth landing with one occluded keypoint must NOT
# report the WORST smoothness (0.0); it must degrade gracefully (close to 1.0).
# --------------------------------------------------------------------------- #


def test_nan_post_landing_knee_does_not_report_worst_smoothness_repro():
    """CORRECT behavior: a perfectly smooth landing (constant CoM, zero
    velocity std, smoothness should be ~1.0) with ONE occluded knee keypoint
    on a post-landing frame must not be reported as the WORST smoothness
    (0.0). The metric must degrade gracefully — skip the NaN frame
    (`np.nanstd` / NaN mask) and report smoothness from the valid frames,
    close to 1.0. It must NOT return 0.0 (a false "totally wobbly landing"
    diagnosis).

    RED now: `RKNEE` NaN on post-landing frames → CoM of those frames is NaN
    (`calculate_com_trajectory` is a weighted sum over all keypoints; one NaN
    poisons the sum) → `post_com` has NaN → `velocities = -(post_com[1:] -
    post_com[:-1]) * fps` has NaN → `np.std(velocities) = nan` → `1.0 - nan/0.2
    = nan` → Python `max(0.0, nan) = 0.0` (arg-order NaN-unsafe, #454). A
    smooth landing reads as WORST smoothness (0.0). After the fix: the NaN
    frame is skipped and smoothness stays ~1.0.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    # Baseline: all-valid still body → smoothness should be ~1.0.
    s_valid = analyzer.compute_landing_smoothness(_still_pose(None), _phases(), fps=30.0)
    assert s_valid > 0.9, (
        f"test fixture broken: all-valid still body reported smoothness "
        f"{s_valid:.3f}, expected ~1.0. The fixture needs identical frames "
        f"(constant CoM → velocities ~0 → std ~0) so the all-valid baseline is "
        f"~1.0 — otherwise the NaN-vs-valid contrast is meaningless."
    )

    # One occluded knee on post-landing — same still body, one NaN keypoint.
    s_nan = analyzer.compute_landing_smoothness(_still_pose("rknee"), _phases(), fps=30.0)

    # CORRECT contract: the occluded-keypoint smoothness must NOT be 0.0
    # (worst). It must be close to the all-valid smoothness (graceful NaN-
    # skip), or at worst a NaN/degraded sentinel — NOT a false "totally
    # wobbly landing" 0.0.
    assert s_nan > 0.3, (
        f"BUG: compute_landing_smoothness returned {s_nan:.3f} for a perfectly "
        f"smooth landing (all-valid smoothness = {s_valid:.3f}) with a NaN "
        f"RKNEE on the post-landing frames (occlusion). `calculate_com_"
        f"trajectory` is a weighted sum over ALL 17 keypoints, so one NaN "
        f"keypoint makes the CoM NaN for those frames; the finite-difference "
        f"velocities are NaN; `np.std(velocities) = nan`; `1.0 - nan/0.2 = "
        f"nan`; and Python `max(0.0, nan) = 0.0` (arg-order NaN-unsafe, #454: "
        f"max(0.0, nan) = 0.0). A smooth landing reads as the WORST smoothness "
        f"(0.0) — a false 'totally wobbly landing' diagnosis when the truth is "
        f"'no data for that frame'. The metric confuses occlusion with a "
        f"wobble. (Sanity: all-valid smoothness = {s_valid:.3f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint (CoM weighted sum),
# not just the knee — a NaN wrist (small, easily lost by the tracker) also
# zeroes the smoothness. Wide blast radius.
# --------------------------------------------------------------------------- #


def test_nan_wrist_post_landing_does_not_report_worst_smoothness_repro():
    """CORRECT behavior: a perfectly smooth landing with one occluded WRIST
    on a post-landing frame must also not report worst smoothness. The CoM
    weighted sum includes the arms (upper arm + forearm, both built from
    shoulders/elbows/wrists), so a NaN wrist poisons the CoM the same way as
    a NaN knee. The bug has a wide blast radius — ANY of the 17 keypoints.

    RED now: `RWRIST` NaN → `r_forearm = (RELBOW + RWRIST) / 2 = nan` →
    `com_y = nan` for those frames → `np.std(velocities) = nan` →
    `max(0.0, nan) = 0.0`. After the fix: graceful degradation on any
    occluded keypoint.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    s_nan = analyzer.compute_landing_smoothness(_still_pose("rwrist"), _phases(), fps=30.0)

    assert s_nan > 0.3, (
        f"BUG: compute_landing_smoothness returned {s_nan:.3f} for a perfectly "
        f"smooth landing with a NaN RWRIST on the post-landing frames. The CoM "
        f"weighted sum includes the arms (r_forearm = (RELBOW + RWRIST) / 2), "
        f"so a NaN wrist poisons the CoM the same way as a NaN knee. The bug "
        f"has a wide blast radius — ANY of the 17 keypoints, not just the "
        f"knee. A fix that only guards the knee (or only the legs) would leave "
        f"the arm/head keypoints broken. The root-cause fix is NaN-aware CoM "
        f"(`calculate_com_trajectory`) or `np.nanstd` on the velocities."
    )


# --------------------------------------------------------------------------- #
# Observable 3: occluding LKNEE vs RKNEE must give the same smoothness —
# symmetric in which side is occluded.
# --------------------------------------------------------------------------- #


def test_nan_knee_smoothness_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE on the post-landing frames
    must give the same smoothness — both poison the CoM (one term in the
    weighted sum) identically. The metric must be symmetric in which side is
    occluded.

    RED now: both give `max(0.0, nan) = 0.0` (symmetric today, both worst).
    This is a regression guard that PASSES today (both 0.0) and must keep
    passing after the fix (both should report the same graceful-degradation
    value, close to 1.0). It locks the symmetry contract so a fix that only
    handles one side does not pass.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    poses_r = _still_pose("rknee")
    poses_l = _still_pose(None)
    for f in range(8, poses_l.shape[0]):
        poses_l[f, H36Key.LKNEE] = [np.nan, np.nan]

    s_right_nan = analyzer.compute_landing_smoothness(poses_r, _phases(), fps=30.0)
    s_left_nan = analyzer.compute_landing_smoothness(poses_l, _phases(), fps=30.0)

    assert abs(s_right_nan - s_left_nan) < 0.02, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different smoothness "
        f"({s_left_nan:.3f} vs {s_right_nan:.3f}). Both poison the CoM "
        f"weighted sum identically (one NaN term) — the metric must be "
        f"symmetric in which side is occluded. A fix that only handles one "
        f"side would break this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid still body still reports ~1.0 smoothness.
# --------------------------------------------------------------------------- #


def test_all_valid_smoothness_unchanged_repro():
    """Regression guard: an all-valid still body must still report smoothness
    ~1.0. The fix (nanstd / NaN mask) must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    s = analyzer.compute_landing_smoothness(_still_pose(None), _phases(), fps=30.0)
    assert s > 0.9, (
        f"BUG (regression): all-valid still body reported smoothness "
        f"{s:.3f}, expected ~1.0. The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — np.std (not nanstd) + Python max(0.0, ...)
# --------------------------------------------------------------------------- #


def test_landing_smoothness_nan_unsafe_source_repro():
    """GREEN source check (#870 fix): `compute_landing_smoothness` no longer
    uses the NaN-propagating `np.std(velocities)` or the NaN-unsafe arg-order
    `max(0.0, 1.0 - std_velocity / 0.2)`. A NaN-mask on velocities + a NaN-safe
    clamp replaced them; and `calculate_com_trajectory` is NaN-aware (#871),
    so one occluded keypoint no longer poisons the CoM."""
    src = inspect.getsource(BiomechanicsAnalyzer.compute_landing_smoothness)
    # The NaN-propagating np.std(velocities) line is GONE.
    assert "std_velocity = float(np.std(velocities))" not in src, (
        "#870 RED: the NaN-propagating `np.std(velocities)` line is back — "
        "a NaN velocity makes the whole-window std NaN. Mask finite velocities "
        "first (np.isfinite) and std over the finite subset."
    )
    # A NaN mask on velocities is present.
    assert "np.isfinite(velocities)" in src, (
        "#870 RED: compute_landing_smoothness must mask NaN velocities with "
        "np.isfinite before std — a fully-occluded post-landing frame yields "
        "NaN velocities; std over NaN = NaN, then max(0.0, nan)=0.0 falsely "
        "grades a smooth landing as worst (#454)."
    )
    # The NaN-unsafe arg-order clamp is GONE, replaced by np.clip.
    assert "max(0.0, 1.0 - std_velocity / 0.2)" not in src, (
        "#870 RED: the NaN-unsafe `max(0.0, 1.0 - std_velocity / 0.2)` clamp "
        "is back — max(0.0, nan)=0.0 (arg-order #454). Use np.clip (NaN-safe "
        "after the isfinite guard)."
    )
    assert "np.clip" in src, (
        "#870 RED: use np.clip(1.0 - std_velocity / 0.2, 0.0, 1.0) — NaN-safe "
        "clamp, unlike Python max which is arg-order NaN-unsafe (#454)."
    )

    # calculate_com_trajectory is NaN-aware (#871) — a NaN keypoint is masked,
    # not propagated. Fixes every CoM-based metric at the source.
    com_src = inspect.getsource(calculate_com_trajectory)
    assert "np.isfinite" in com_src, (
        "#870 RED: calculate_com_trajectory must be NaN-aware (#871) — mask "
        "NaN segment contributions so one occluded keypoint does not poison "
        "the CoM. This fixes every CoM-based metric (smoothness, hard_landing, "
        "relative_jump_height, peak_com) at once."
    )
