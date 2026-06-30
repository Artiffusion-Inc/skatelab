"""RED repro — NaN centroid disables the anti-steal AND-gate (sibling of #451).

Bug: TrackValidator.is_stolen (_track_validator.py:25-47) computes the
centroid half of the AND-gate as:

  :25  cur_cx = float(np.nanmean(current_pose[:, 0]))
  :26  cur_cy = float(np.nanmean(current_pose[:, 1]))
  :29  jump = np.sqrt((cur_cx - prev_cx)**2 + (cur_cy - prev_cy)**2)
  :47  return jump > 0.15 and skeletal_anomaly

#451 fixed the SKELETAL half: `not np.isfinite(ratio_change) or
ratio_change > 0.25` treats a NaN ratio as an anomaly (conservative). But
the CENTROID half was NOT fixed: when current_pose has ALL joints NaN (a
heavily-occluded frame / detector glitch), `np.nanmean` returns NaN (with a
RuntimeWarning), `jump = NaN`, and `NaN > 0.15` is False in Python. So:

  return (NaN > 0.15) and (skeletal_anomaly=True)
       = False and True
       = False

An entirely-untrustworthy (all-NaN) frame is judged "not stolen" and written
verbatim into all_poses — the opposite of conservative. The ratio half says
"anomaly" (can't confirm identity) but the centroid half short-circuits the
AND-gate on NaN.

This is reachable now that #469 made the guard LIVE (the guard was dead code
before #469). The compound: #451 + #469 unlocked the guard, exposing this
NaN-centroid sibling.

Fix direction (do NOT apply here): treat a non-finite `jump` as exceeding
the threshold (conservative) — `not np.isfinite(jump) or jump > 0.15` —
mirroring the ratio half's NaN guard. Then both halves flag the untrustworthy
frame and the AND-gate fires.

This test MUST fail (RED) against the current code. Repro, not a fix.
"""

import numpy as np

from src.pose_estimation._track_validator import TrackValidator
from src.tracking.skeletal_identity import compute_2d_skeletal_ratios


def _normal_pose() -> np.ndarray:
    pose = np.zeros((17, 3), np.float32)
    pose[:, 2] = 0.9
    pose[0] = [0.50, 0.55, 0.9]  # hip
    pose[1] = [0.50, 0.35, 0.9]  # neck
    pose[2] = [0.40, 0.30, 0.9]
    pose[3] = [0.60, 0.30, 0.9]
    pose[6] = [0.45, 0.60, 0.9]
    pose[7] = [0.55, 0.60, 0.9]
    pose[8] = [0.46, 0.80, 0.9]
    pose[9] = [0.54, 0.80, 0.9]
    return pose.astype(np.float32)


def test_is_stolen_nan_centroid_current_pose_is_conservative():
    """An all-NaN current_pose (heavily occluded) must NOT be judged
    'not stolen' — identity is unverifiable, so the AND-gate must flag it
    (conservative), mirroring the ratio half's NaN treatment (#451).
    """
    validator = TrackValidator()
    last = _normal_pose()
    last_ratios = compute_2d_skeletal_ratios(last)

    # All-NaN current pose: detector returned nothing usable for this frame.
    nan_pose = np.full((17, 3), np.nan, dtype=np.float32)

    # Sanity: the ratio half IS conservative on NaN (#451) — ratios are NaN,
    # so skeletal_anomaly must be True. Confirm so the test cannot pass for
    # the wrong reason.
    nan_ratios = compute_2d_skeletal_ratios(nan_pose)
    ratio_change = float(np.linalg.norm(nan_ratios - last_ratios))
    assert not np.isfinite(ratio_change), (
        "test fixture broken: NaN pose must yield a non-finite ratio_change "
        "so the skeletal half flags it (#451)."
    )

    stolen = validator.is_stolen(nan_pose, last, last_ratios)

    assert stolen is True, (
        "BUG: all-NaN current_pose → np.nanmean→NaN → jump=NaN → "
        "`NaN > 0.15`=False short-circuits the AND-gate (centroid half), so "
        "is_stolen returns False even though the ratio half flags an anomaly "
        "(#451). An entirely-untrustworthy frame is written verbatim into "
        "all_poses instead of being blanked. #451 guarded the skeletal half "
        "but NOT the centroid half. The guard is now LIVE (#469), so this "
        "NaN-centroid sibling is reachable. Fix: treat non-finite jump as "
        "exceeding the threshold (conservative), mirroring the ratio half."
    )
