"""RED repro tests for two confirmed ML edge-case bugs.

Bug A — single NaN-keypoint silently disables anti-steal AND-gate.
  Source: ml/src/tracking/skeletal_identity.py:160-180
          `compute_2d_skeletal_ratios` propagates a NaN xy coordinate in any
          ratio-relevant joint (LSHOULDER/RSHOULDER/LHIP/RHIP/HIP_CENTER/NECK/
          LKNEE/RKNEE) through `np.linalg.norm(diff)` for that bone into the
          returned ratio vector. The validator
          (ml/src/pose_estimation/_track_validator.py:35-37) then computes
          `ratio_change = float(np.linalg.norm(curr_ratios - last_target_ratios))`
          = NaN, and `skeletal_anomaly = NaN > 0.25` is `False` in Python, so the
          AND-gate (`jump > 0.15 AND skeletal_anomaly`) passes — `is_stolen`
          returns False even on a clear large-jump steal. The exact
          occlusion-swap frame the validator exists to catch is missed.
  Reachability: pose NaN is the canonical "occluded keypoint" representation
          (TrackedExtraction.poses uses NaN for missing frames — see
          ml/src/types.py:~853). Anti-steal runs per-frame on the raw pose, so a
          single occluded knee at the swap frame is sufficient.

Bug B — DTW compute_distance returns silent 0.0 on empty reference.
  Source: ml/src/alignment/motion_dtw.py:442-475 `compute_distance(user, empty)`
          -> `align_with_keyframes` skips all phases (the `len == 0` guard at
          :144) -> `total_distance = sum([]) / max(0, 1) = 0.0` — a value
          indistinguishable from a perfect match.
  Sibling: :477-506 `compute_distance_3d(user, empty)` crashes with an
          unguarded `ValueError: cannot reshape array of size 0` mid-compute.
  Reachability: degenerate phase slice where end == start yields a zero-length
          reference segment (see pipeline.py phase slicing). The 2D path
          silently returns 0.0 (corrupts overall_score / GOE composite — same
          silent-perfect-subscore class as #432/#434); the 3D path aborts the
          whole process_video_task arq job on one bad reference slice.

These tests are intentionally RED against current code. They assert the
*correct* behavior; current code violates it. Do NOT weaken the assertions.
"""

import numpy as np
import pytest

from src.alignment.motion_dtw import MotionDTWAligner
from src.pose_estimation._track_validator import TrackValidator
from src.tracking.skeletal_identity import compute_2d_skeletal_ratios
from src.types import H36Key

# ---------------------------------------------------------------------------
# Bug A — NaN-keypoint disables anti-steal AND-gate
# ---------------------------------------------------------------------------


def _distinct_pose() -> np.ndarray:
    """A non-degenerate H3.6M pose with distinct, ratio-non-zero joints.

    All ratio-relevant joints (LSHOULDER/RSHOULDER/LHIP/RHIP/HIP_CENTER/NECK/
    LKNEE/RKNEE) are given distinct coordinates so the skeletal-ratio vector is
    non-trivial (not all zeros). Confidence channel = 0.9 (well above the 0.3
    biometric_distance gate).
    """
    pose = np.zeros((17, 3), np.float32)
    pose[:, 2] = 0.9
    pose[H36Key.HIP_CENTER] = [0.50, 0.55, 0.9]
    pose[H36Key.NECK] = [0.50, 0.35, 0.9]
    pose[H36Key.LSHOULDER] = [0.40, 0.30, 0.9]
    pose[H36Key.RSHOULDER] = [0.60, 0.30, 0.9]
    pose[H36Key.LHIP] = [0.45, 0.60, 0.9]
    pose[H36Key.RHIP] = [0.55, 0.60, 0.9]
    pose[H36Key.LKNEE] = [0.46, 0.80, 0.9]
    pose[H36Key.RKNEE] = [0.54, 0.80, 0.9]
    return pose


def test_nan_keypoint_disables_anti_steal_and_gate():
    """RED: a single NaN xy in a ratio-relevant joint must NOT suppress is_stolen.

    Setup: prev pose is a normal skater. Curr pose is the SAME pose shifted by
    +0.5 in both x and y (a centroid jump of ~0.707, far above the 0.15
    threshold) BUT with one occluded keypoint — LKNEE x = NaN. This is the
    textbook occlusion-swap frame: the centroid jumped (a different person was
    suddenly locked on) and one knee was momentarily occluded.

    Current code: NaN flows into compute_2d_skeletal_ratios -> the femur-L ratio
    entry becomes NaN -> ratio_change = ||... NaN ...|| = NaN ->
    skeletal_anomaly = (NaN > 0.25) = False -> AND-gate passes -> is_stolen=False.
    The steal is missed.

    Correct behavior: is_stolen must return True (a 0.707 centroid jump IS a
    steal; the validator exists to catch exactly this frame). NaN in one joint
    must not silently zero the anomaly half of the AND-gate.
    """
    pose_prev = _distinct_pose()
    prev_ratios = compute_2d_skeletal_ratios(pose_prev)

    pose_curr = pose_prev.copy()
    pose_curr[:, :2] += 0.5  # BIG centroid jump (~0.707 >> 0.15 threshold)
    pose_curr[H36Key.LKNEE, 0] = np.nan  # one occluded ratio-relevant joint

    # Sanity: confirm the jump really exceeds the threshold independently of
    # the (NaN-corrupted) skeletal path, so a future fix that changes the
    # skeletal handling cannot make this test pass for the wrong reason.
    cur_cx = float(np.nanmean(pose_curr[:, 0]))
    cur_cy = float(np.nanmean(pose_curr[:, 1]))
    prev_cx = float(np.nanmean(pose_prev[:, 0]))
    prev_cy = float(np.nanmean(pose_prev[:, 1]))
    jump = float(np.sqrt((cur_cx - prev_cx) ** 2 + (cur_cy - prev_cy) ** 2))
    assert jump > TrackValidator.CENTROID_JUMP_THRESHOLD, (
        f"test fixture broken: jump {jump:.3f} must exceed "
        f"{TrackValidator.CENTROID_JUMP_THRESHOLD} for the steal to be clear"
    )

    # Confirm the bug mechanism: a NaN appears in the ratio vector.
    curr_ratios = compute_2d_skeletal_ratios(pose_curr)
    assert np.isnan(curr_ratios).any(), (
        "test fixture broken: no NaN in curr_ratios — the occlusion did not "
        "propagate into the ratio vector as the bug requires"
    )

    validator = TrackValidator()
    stolen = validator.is_stolen(pose_curr, pose_prev, prev_ratios)

    assert stolen is True, (
        "BUG A: anti-steal AND-gate silently disabled by a single NaN keypoint — "
        f"ratio_change=NaN -> skeletal_anomaly=(NaN>0.25)=False -> is_stolen=False "
        f"on a clear steal (centroid jump={jump:.3f} >> "
        f"{TrackValidator.CENTROID_JUMP_THRESHOLD}). The exact occlusion-swap "
        f"frame the validator exists to catch is missed. curr_ratios={curr_ratios}"
    )


# ---------------------------------------------------------------------------
# Bug B — DTW compute_distance returns silent 0.0 on empty reference
# ---------------------------------------------------------------------------


def test_compute_distance_empty_reference_is_not_silent_zero():
    """RED: compute_distance must NOT silently return 0.0 on an empty reference.

    An empty reference (zero frames) is a degenerate / missing-reference input.
    Returning 0.0 is indistinguishable from a perfect match and silently
    corrupts the downstream overall_score / GOE composite (same silent-perfect
    -subscore class as #432/#434). The contract: either raise a clean
    ValueError OR return a non-zero sentinel (math.inf). It must not be 0.0.

    Current code returns 0.0 (align_with_keyframes skips all phases via the
    len==0 guard at motion_dtw.py:144, then sum([])/max(0,1) == 0.0).
    """
    aligner = MotionDTWAligner()
    rng = np.random.default_rng(42)
    user = rng.standard_normal((20, 17, 2)).astype(np.float32) * 5.0
    empty_ref = np.zeros((0, 17, 2), np.float32)

    dist = aligner.compute_distance(user, empty_ref)

    assert dist != 0.0, (
        "BUG B: compute_distance(user, empty_ref) returns silent 0.0 — "
        "indistinguishable from a perfect match. Corrupts downstream "
        "overall_score/GOE composite (same class as #432/#434). Must raise a "
        "clean ValueError or return math.inf on empty input, not 0.0."
    )
