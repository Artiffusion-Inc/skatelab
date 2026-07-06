"""RED repro — `BiomechanicsAnalyzer.compute_symmetry` computes per-pair
left-right asymmetry as `distances = np.linalg.norm(mirrored_left -
right_joints, axis=1)`, appends `np.mean(distances)` to `asymmetries`, then
returns `max(0, 1 - avg_asymmetry)` where `avg_asymmetry = np.mean(
asymmetries)`. When ANY keypoint in ANY pair is NaN (occlusion), `distances`
is NaN, `np.mean(distances) = nan` (NumPy propagates NaN), `asymmetries`
contains nan, `avg_asymmetry = np.mean([..., nan, ...]) = nan`, `1 - nan =
nan`, and Python `max(0, 1 - nan) = 0` (NaN-unsafe and arg-order-dependent,
#454: `max(0, nan) = 0` because `0 > nan` is False). So a PERFECTLY
symmetric body with ONE occluded joint is reported as the WORST symmetry
(0.0), not as "no data" — a false diagnosis (tranche BL).

`compute_symmetry` (ml/src/analysis/metrics.py:1417-1457):

    joint_pairs = [
        (H36Key.LSHOULDER, H36Key.RSHOULDER),
        (H36Key.LELBOW, H36Key.RELBOW),
        (H36Key.LHIP, H36Key.RHIP),
        (H36Key.LKNEE, H36Key.RKNEE),
    ]
    asymmetries: list[float] = []
    for left_idx, right_idx in joint_pairs:
        left_joints = element_poses[:, left_idx]
        right_joints = element_poses[:, right_idx]
        mirrored_left = left_joints.copy()
        mirrored_left[:, 0] = -left_joints[:, 0]
        distances = np.linalg.norm(mirrored_left - right_joints, axis=1)
        asymmetries.append(float(np.mean(distances)))   # nan if either joint NaN
    avg_asymmetry = float(np.mean(asymmetries))         # nan if any pair nan
    return float(max(0, 1 - avg_asymmetry))             # max(0, nan) = 0

When `RKNEE` is NaN: `right_joints[:, :] = nan`,
`mirrored_left - right_joints = nan`, `np.linalg.norm(nan, axis=1) = nan`,
`np.mean(nan) = nan` → `asymmetries = [a_shoulder, b_elbow, c_hip, nan]` →
`np.mean([..., nan]) = nan` → `1 - nan = nan` → `max(0, nan) = 0`.

Reproduced (10 frames, waltz_jump; perfectly symmetric body — left joints
mirror right across Y-axis → symmetry should be 1.0):

    all-valid body                   → symmetry = 1.0  (correct: perfect mirror)
    one-NaN-knee (RKNEE occluded)    → symmetry = 0.0  (BUG: occlusion → worst)
    one-NaN-elbow (RELBOW occluded)  → symmetry = 0.0  (BUG: same, any pair)

Consequences (prod impact — symmetry feeds the overall score, is_good gate,
GOE, recommender, gamification, the same composite chain as BJ):
  1. `analyze()` (metrics.py:652-656) emits `symmetry` with `value=0.0`; the
     `is_good` gate (e.g. `(0.7, 1.0)`) → 0.0 not in range → `is_good=False`.
     A symmetric skater with one occluded joint reads as "worst body
     symmetry" — a false bad metric.
  2. `_compute_overall_score` (pipeline.py:608-629) counts `is_good` over
     metrics; the false `is_good=False` loses a `good_count` point → overall
     deflated → gamification XP (`award_session_xp int(overall)`) and skill
     unlocks (`check_skill_unlocks`) penalized for an occlusion, not for
     performance. Cross-layer with #437/#852-class.
  3. Knee/elbow/hip occlusion is COMMON — small keypoints the tracker loses
     on fast motion. The metric confuses occlusion with asymmetry.
  4. Existing tests miss it: `test_compute_symmetry` (test_metrics.py:236)
     and the tranche-BC test `test_symmetry_yaxis_mirror_tilt_repro` feed
     all-valid keypoints. No test feeds a NaN joint to a single pair while
     the others are valid. The `max(0, nan) = 0` arg-order trap (#454) is not
     exercised on this method.

The fix (NOT applied — repro only): make the metric NaN-aware. Either:
  - mask NaN per pair before the mean: `distances = distances[np.isfinite(
    distances)]` and skip the pair (or use `np.nanmean`) when all-NaN; or
  - replace Python `max(0, 1 - avg_asymmetry)` with `np.nan_to_num(1 -
    avg_asymmetry, nan=1.0)` / `np.fmax(0.0, 1 - avg_asymmetry)` and a NaN
    guard on `avg_asymmetry` (`np.nanmean` over pairs, or skip NaN pairs).
  - `np.nanmean` over `asymmetries` alone is NOT enough if the LAST pair is
    NaN — `np.nanmean([nan, b, c, d]) = mean([b, c, d])` (skips nan), which is
    correct; but `np.mean([nan, b, c, d]) = nan` (current). The per-pair
    `np.mean(distances)` is the source of nan — switch to `np.nanmean(
    distances)` AND `np.nanmean(asymmetries)` (or mask per pair).

The correct contract: an occluded joint must NOT read as worst symmetry (0.0).
The metric must skip the NaN pair and report symmetry from the valid pairs
(graceful degradation), close to the all-valid case (1.0 for a perfectly
symmetric body), not 0.0.

RED now: the observable assertions below describe the CORRECT behavior — a
perfectly symmetric body with one occluded joint must NOT report worst
symmetry (0.0); it must degrade gracefully (close to 1.0). They FAIL because
`max(0, 1 - nan) = 0`. After the fix: NaN pairs are skipped and the symmetry
stays near 1.0. The source-check test confirms the `np.mean(distances)` (not
nanmean) + `np.mean(asymmetries)` (not nanmean) + `max(0, 1 -
avg_asymmetry)` lines are present (root cause locked).

Pure-Python (no GPU, no DB): `compute_symmetry` is a pure-data method over a
poses array + phase markers.
"""

import inspect

import numpy as np

from src.analysis.element_defs import ELEMENT_DEFS
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _symmetric_pose(nan_joint: str | None = None, n: int = 10) -> np.ndarray:
    """A 10-frame pose sequence with a PERFECTLY symmetric body — every left
    joint is the mirror of the right across the Y-axis (x_left = -x_right,
    y_left = y_right). Symmetry should be 1.0.

    When `nan_joint` is set, that joint is NaN on every frame — the occlusion
    case. Only ONE pair is poisoned; the other three stay valid.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.0]
        poses[f, H36Key.RSHOULDER] = [0.2, 0.0]
        poses[f, H36Key.LELBOW] = [-0.3, 0.1]
        poses[f, H36Key.RELBOW] = [0.3, 0.1]
        poses[f, H36Key.LHIP] = [-0.1, 0.5]
        poses[f, H36Key.RHIP] = [0.1, 0.5]
        poses[f, H36Key.LKNEE] = [-0.1, 0.9]
        poses[f, H36Key.RKNEE] = [0.1, 0.9]
    if nan_joint == "rknee":
        for f in range(n):
            poses[f, H36Key.RKNEE] = [np.nan, np.nan]
    elif nan_joint == "relbow":
        for f in range(n):
            poses[f, H36Key.RELBOW] = [np.nan, np.nan]
    elif nan_joint == "lhip":
        for f in range(n):
            poses[f, H36Key.LHIP] = [np.nan, np.nan]
    return poses


def _phases(n: int = 10):
    return ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=4, landing=7, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: a perfectly symmetric body with one occluded joint must NOT
# report the WORST symmetry (0.0); it must degrade gracefully (close to 1.0).
# --------------------------------------------------------------------------- #


def test_nan_knee_does_not_report_worst_symmetry_repro():
    """CORRECT behavior: a perfectly symmetric body (left joints mirror right
    across Y-axis → symmetry should be ~1.0) with ONE occluded knee keypoint
    must not be reported as the WORST symmetry (0.0). The metric must degrade
    gracefully — skip the NaN pair (`np.nanmean` / NaN mask) and report
    symmetry from the three valid pairs, close to 1.0. It must NOT return 0.0
    (a false "totally asymmetric body" diagnosis).

    RED now: `RKNEE` NaN → `right_joints = nan` for the knee pair →
    `np.linalg.norm(mirrored_left - nan, axis=1) = nan` →
    `np.mean(nan) = nan` → `asymmetries = [a, b, c, nan]` →
    `np.mean([a, b, c, nan]) = nan` → `1 - nan = nan` → Python `max(0, nan) =
    0` (NaN-unsafe arg-order, #454). A symmetric body reads as WORST symmetry
    (0.0). After the fix: the NaN pair is skipped and symmetry stays ~1.0.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    # Baseline: all-valid symmetric body → symmetry should be ~1.0.
    s_valid = analyzer.compute_symmetry(_symmetric_pose(None), _phases())
    assert abs(s_valid - 1.0) < 0.05, (
        f"test fixture broken: all-valid symmetric body reported symmetry "
        f"{s_valid:.3f}, expected ~1.0. The fixture needs a perfect Y-axis "
        f"mirror (x_left = -x_right, y_left = y_right) so the all-valid "
        f"baseline is ~1.0 — otherwise the NaN-vs-valid contrast is meaningless."
    )

    # One occluded knee — same symmetric body, one NaN joint.
    s_nan = analyzer.compute_symmetry(_symmetric_pose("rknee"), _phases())

    # CORRECT contract: the occluded-joint symmetry must NOT be 0.0 (worst).
    # It must be close to the all-valid symmetry (graceful NaN-skip), or at
    # worst a NaN/degraded sentinel — NOT a false "totally asymmetric" 0.0.
    assert s_nan > 0.5, (
        f"BUG: compute_symmetry returned {s_nan:.3f} for a perfectly symmetric "
        f"body (all-valid symmetry = {s_valid:.3f}) with one occluded knee "
        f"keypoint (RKNEE NaN). The NaN-poisoned knee pair makes `distances = "
        f"np.linalg.norm(mirrored_left - nan, axis=1) = nan`, so "
        f"`asymmetries` contains a nan, `np.mean(asymmetries) = nan`, "
        f"`1 - nan = nan`, and Python `max(0, 1 - nan) = 0` (arg-order "
        f"NaN-unsafe, #454: max(0, nan) = 0). A symmetric body reads as the "
        f"WORST symmetry (0.0) — a false 'totally asymmetric' diagnosis when "
        f"the truth is 'no data for that pair'. The metric confuses occlusion "
        f"with asymmetry. (Sanity: all-valid symmetry = {s_valid:.3f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: same bug for any occluded pair — NaN elbow (a different pair).
# The crash/zero must be symmetric across pairs, not just the knee.
# --------------------------------------------------------------------------- #


def test_nan_elbow_does_not_report_worst_symmetry_repro():
    """CORRECT behavior: a perfectly symmetric body with one occluded ELBOW
    (a different pair than the knee) must also not report worst symmetry. The
    bug must be symmetric across the four pairs — occluding any one joint must
    not zero the whole metric.

    RED now: `RELBOW` NaN poisons the elbow pair the same way →
    `max(0, 1 - nan) = 0`. After the fix: graceful degradation on any pair.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    s_nan = analyzer.compute_symmetry(_symmetric_pose("relbow"), _phases())

    assert s_nan > 0.5, (
        f"BUG: compute_symmetry returned {s_nan:.3f} for a perfectly symmetric "
        f"body with one occluded elbow keypoint (RELBOW NaN). The NaN poisons "
        f"the elbow pair the same way as the knee pair — `asymmetries` gets a "
        f"nan, `np.mean(asymmetries) = nan`, `max(0, 1 - nan) = 0`. The bug is "
        f"symmetric across the four joint pairs — occluding any one joint "
        f"zeros the whole metric. A fix that only guards the knee pair would "
        f"leave the elbow/shoulder/hip pairs broken."
    )


# --------------------------------------------------------------------------- #
# Observable 3: occluding the LEFT joint vs the RIGHT joint of a pair must
# give the same symmetry (symmetric in which side is occluded).
# --------------------------------------------------------------------------- #


def test_nan_joint_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding the LEFT joint of a pair vs the RIGHT joint
    must give the same symmetry — both poison the same pair's distance norm.
    The metric must be symmetric in which side is occluded.

    RED now: both give `max(0, 1 - nan) = 0` (symmetric today, both worst).
    This is a regression guard that PASSES today (both 0.0) and must keep
    passing after the fix (both should report the same graceful-degradation
    value, close to 1.0). It locks the symmetry contract so a fix that only
    handles one side does not pass.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    # Occlude RIGHT knee vs LEFT knee — both poison the knee pair.
    poses_r = _symmetric_pose("rknee")
    poses_l = _symmetric_pose(None)
    for f in range(poses_l.shape[0]):
        poses_l[f, H36Key.LKNEE] = [np.nan, np.nan]

    s_right_nan = analyzer.compute_symmetry(poses_r, _phases())
    s_left_nan = analyzer.compute_symmetry(poses_l, _phases())

    assert abs(s_right_nan - s_left_nan) < 0.02, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different symmetries "
        f"({s_left_nan:.3f} vs {s_right_nan:.3f}). Both poison the same knee "
        f"pair's distance norm identically — the metric must be symmetric in "
        f"which side of the pair is occluded. A fix that only handles one side "
        f"would break this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid symmetric body still reports ~1.0.
# --------------------------------------------------------------------------- #


def test_all_valid_symmetry_unchanged_repro():
    """Regression guard: an all-valid symmetric body must still report
    symmetry ~1.0. The fix (nanmean / NaN mask) must not change the no-NaN
    case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    s = analyzer.compute_symmetry(_symmetric_pose(None), _phases())
    assert abs(s - 1.0) < 0.05, (
        f"BUG (regression): all-valid symmetric body reported symmetry "
        f"{s:.3f}, expected ~1.0. The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — np.mean (not nanmean) + Python max(0, ...).
# --------------------------------------------------------------------------- #


def test_symmetry_nan_unsafe_source_repro():
    """GREEN source check (#869 fix): `compute_symmetry` no longer uses the
    NaN-propagating `np.mean(distances)` / `np.mean(asymmetries)` or the
    NaN-unsafe arg-order `max(0, 1 - avg_asymmetry)`. A NaN-safe per-pair
    `np.nanmean`, a finite-pair aggregate filter, and a `np.clip` clamp
    replaced them."""
    src = inspect.getsource(BiomechanicsAnalyzer.compute_symmetry)
    # The NaN-propagating per-pair np.mean is GONE.
    assert "asymmetries.append(float(np.mean(distances)))" not in src, (
        "#869 RED: the NaN-propagating `np.mean(distances)` per-pair line is "
        "back — one occluded joint NaN-poisons the pair. Use np.nanmean."
    )
    # A NaN-safe per-pair mean is present.
    assert "np.nanmean(distances)" in src, (
        "#869 RED: compute_symmetry must use np.nanmean(distances) per pair "
        "— skip NaN frames in a pair instead of letting one occluded joint "
        "poison the whole pair."
    )
    # The NaN-propagating aggregate np.mean(asymmetries) is GONE.
    assert "avg_asymmetry = float(np.mean(asymmetries))" not in src, (
        "#869 RED: the NaN-propagating `np.mean(asymmetries)` aggregate is "
        "back — one NaN pair poisons the whole metric. Filter finite pairs."
    )
    # The NaN-unsafe arg-order clamp is GONE, replaced by np.clip.
    assert "max(0, 1 - avg_asymmetry)" not in src, (
        "#869 RED: the NaN-unsafe `max(0, 1 - avg_asymmetry)` clamp is back — "
        "max(0, nan)=0 (arg-order #454) grades a symmetric body with one "
        "occluded joint as worst. Use np.clip."
    )
    assert "np.clip" in src, (
        "#869 RED: use np.clip(1.0 - avg_asymmetry, 0.0, 1.0) — NaN-safe clamp "
        "after the finite-pair filter, unlike Python max which is arg-order "
        "NaN-unsafe (#454)."
    )
