"""RED repro — `BiomechanicsAnalyzer.compute_arm_position` all-NaN returns
NaN (issue #1274). Contract: when every frame is occluded, the metric must
return a neutral finite score (0.5) so the recommender/GOE has a
deterministic "unknown" midpoint, not NaN that propagates and not 0.0 that
silently classifies occluded arms as worst.

#1274: `compute_arm_position` (ml/src/analysis/metrics.py) used np.mean
then `max(0, 1 - avg_dist)`. Any NaN wrist/shoulder (occlusion is the
NORMAL case in figure skating) -> mean NaN -> max(0, 1 - NaN) = 0.0
(Python max NaN-arg-order trap, #454) — silent false-bad 0.0 that
misclassifies occluded arms as "arms not compact".

Partial fix #902 introduced np.nanmean + isfinite-guard returning NaN.
#1274 tightens the contract: all-occluded -> neutral 0.5 (deterministic
midpoint), NaN must not propagate downstream to the recommender/GOE.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key

N = 10  # 10 frames is enough to exercise flight + non-flight


def _poses_arms_out() -> np.ndarray:
    """Arms extended: wrists far from shoulders (mid-range score expected)."""
    poses = np.zeros((N, 17, 2), dtype=np.float32)
    for f in range(N):
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.1]
        poses[f, H36Key.RSHOULDER] = [0.2, 0.1]
        poses[f, H36Key.LWRIST] = [-0.25, 0.4]
        poses[f, H36Key.RWRIST] = [0.25, 0.4]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: a NaN wrist on the flight frames must NOT silently score 0.0
# (the false-bad "arms not compact" clamp-floor). Post-fix contract: a finite
# neutral score 0.5 (no false-bad, no NaN-leak into recommender/GOE).
# --------------------------------------------------------------------------- #


def test_nan_wrist_arm_position_returns_neutral_0_5_repro():
    """CORRECT behavior: `compute_arm_position` with a NaN LWRIST on EVERY
    frame (full occlusion) must return a finite neutral score 0.5 — the
    "unknown" midpoint. Must NOT return 0.0 (the false-bad clamp-floor:
    `max(0, 1 - NaN) = 0.0` reports occluded skater as "arms not compact
    = worst") and must NOT return NaN (which propagates into the
    recommender/GOE proxy).

    Pre-#1274: NaN LWRIST -> `np.linalg.norm(nan - shoulder)` = NaN ->
    `np.nanmean(...)` = NaN -> the #902 guard returns `float('nan')` ->
    downstream recommender/GOE sees NaN and skips/propagates, leaving the
    metric value unresolved.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    poses = np.full((N, 17, 2), np.nan, dtype=np.float32)
    # Only wrist+shoulder keypoints matter; fill non-arm keypoints with 0
    # so the function is well-formed and only the arm-NaN branch triggers.
    for f in range(N):
        poses[f, H36Key.LSHOULDER] = [np.nan, np.nan]
        poses[f, H36Key.RSHOULDER] = [np.nan, np.nan]
        poses[f, H36Key.LWRIST] = [np.nan, np.nan]
        poses[f, H36Key.RWRIST] = [np.nan, np.nan]

    score = an.compute_arm_position(poses)

    # Must NOT silently floor to 0.0 (false-bad "arms not compact").
    assert score != 0.0, (
        f"BUG: compute_arm_position returned {score} for full arm NaN. The "
        f"Python `max(0, 1 - NaN) = 0.0` trap silently classifies occluded "
        f"arms as WORST. Post-#1274 contract: finite neutral 0.5."
    )
    # Post-#1274: finite neutral 0.5 (no NaN-leak).
    assert np.isfinite(score), (
        f"BUG: compute_arm_position returned non-finite {score} for full "
        f"arm NaN; #1274 contract is finite neutral 0.5 so the "
        f"recommender/GOE does not receive NaN."
    )
    assert score == 0.5, (
        f"BUG: compute_arm_position returned {score} for full arm NaN; "
        f"#1274 contract is neutral 0.5 (deterministic 'unknown' midpoint)."
    )


# --------------------------------------------------------------------------- #
# Observable 2: all-NaN (every wrist+shoulder occluded) must return neutral
# 0.5, not NaN and not 0.0.
# --------------------------------------------------------------------------- #


def test_all_nan_arm_position_returns_neutral_0_5_repro():
    """CORRECT behavior: when ALL wrist+shoulder keypoints are NaN (full
    occlusion across the whole sequence), `compute_arm_position` must
    return a finite neutral 0.5 — the "no data" midpoint. Must NOT
    return NaN (NaN-leak into recommender/GOE) and must NOT return 0.0
    (false-bad clamp-floor).
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    poses = np.full((N, 17, 2), np.nan, dtype=np.float32)

    score = an.compute_arm_position(poses)

    assert np.isfinite(score), (
        f"BUG: compute_arm_position returned non-finite {score} for a fully "
        f"occluded arm sequence; #1274 contract is finite neutral 0.5 (no "
        f"NaN-leak into recommender/GOE)."
    )
    assert score == 0.5, (
        f"BUG: compute_arm_position returned {score} for a fully-occluded "
        f"arm sequence; #1274 contract is neutral 0.5 (deterministic "
        f"'no data' midpoint)."
    )


# --------------------------------------------------------------------------- #
# Observable 3: NaN in any of the four keypoints (LWRIST, RWRIST, LSHOULDER,
# RSHOULDER) -> neutral 0.5. Wide blast radius — guard must cover all four.
# --------------------------------------------------------------------------- #


def test_nan_any_arm_keypoint_returns_neutral_0_5_repro():
    """CORRECT behavior: a NaN in ALL frames for any of the four arm keypoints
    (LWRIST, RWRIST, LSHOULDER, RSHOULDER) must return finite neutral 0.5.
    `np.linalg.norm(wrist - shoulder)` poisons on NaN in EITHER endpoint, so
    any occluded arm keypoint triggers the bug.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    for kp in (H36Key.LWRIST, H36Key.RWRIST, H36Key.LSHOULDER, H36Key.RSHOULDER):
        poses = np.zeros((N, 17, 2), dtype=np.float32)
        for f in range(N):
            poses[f, H36Key.LSHOULDER] = [-0.2, 0.1]
            poses[f, H36Key.RSHOULDER] = [0.2, 0.1]
            poses[f, H36Key.LWRIST] = [-0.25, 0.4]
            poses[f, H36Key.RWRIST] = [0.25, 0.4]
            poses[f, kp] = [np.nan, np.nan]  # all frames NaN for this kp
        score = an.compute_arm_position(poses)
        assert np.isfinite(score) and score == 0.5, (
            f"BUG: compute_arm_position returned {score} for an all-NaN "
            f"keypoint ({kp.name}); #1274 contract is finite neutral 0.5 "
            f"for any fully-occluded arm keypoint "
            f"(LWRIST/RWRIST/LSHOULDER/RSHOULDER)."
        )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid arms-extended still produces a finite mid-range
# score; all-valid arms-tight produces a high (near-1.0) score. The fix must
# not change the no-NaN case.
# --------------------------------------------------------------------------- #


def test_all_valid_arm_position_unchanged_repro():
    """Regression guard: all-valid poses must still produce a finite
    arm-position score (mid-range for arms-extended, near-1.0 for arms-tight).
    The #1274 fix (neutral 0.5 on NaN) must not change the no-NaN case.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))

    # Arms-extended -> finite mid-range.
    out = an.compute_arm_position(_poses_arms_out())
    assert np.isfinite(out) and 0.1 < out < 0.95, (
        f"BUG (regression): all-valid arms-extended arm score {out} is "
        f"non-finite or out of mid-range; expected ~0.70. The no-NaN case "
        f"must be unchanged by the #1274 fix."
    )

    # Arms-tight (wrists near shoulders) -> near-1.0.
    poses_tight = _poses_arms_out()
    poses_tight[:, H36Key.LWRIST] = [-0.21, 0.11]
    poses_tight[:, H36Key.RWRIST] = [0.21, 0.11]
    tight = an.compute_arm_position(poses_tight)
    assert np.isfinite(tight) and tight > out, (
        f"BUG (regression): all-valid arms-tight arm score {tight} is "
        f"non-finite or not greater than arms-extended {out}; expected "
        f"near-1.0. The no-NaN case must be unchanged by the #1274 fix."
    )


# --------------------------------------------------------------------------- #
# Source check: the #1274 contract — neutral 0.5 on all-NaN, finite output.
# --------------------------------------------------------------------------- #


def test_arm_position_neutral_0_5_source_repro():
    """Source check: `compute_arm_position` returns 0.5 (neutral) on
    all-NaN input. Locks the #1274 contract that NaN-occluded arms
    receive a deterministic midpoint so the recommender/GOE has a
    finite value to consume (no NaN-leak, no false-bad 0.0).
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_arm_position)
    # The isfinite guard is still present (#902) — keeps the no-data path
    # out of the clamp.
    assert "np.isfinite" in src, (
        "BUG: compute_arm_position must keep the `np.isfinite(avg_dist)` "
        "guard (#902) so a fully-occluded sequence is detected before "
        "the clamp. The #1274 fix tightens the guard's return value, it "
        "does not remove the guard."
    )
    # #1274: the all-NaN branch returns 0.5 (neutral midpoint), not
    # `float('nan')` (#902) and not 0.0 (false-bad clamp-floor).
    assert "0.5" in src, (
        "BUG: compute_arm_position must return 0.5 (neutral) on all-NaN "
        "input (#1274 contract: deterministic midpoint so the "
        "recommender/GOE has a finite value to consume)."
    )
