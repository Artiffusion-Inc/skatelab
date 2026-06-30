"""RED repro — PoseSmoother NaN crash (fastmath 1/NaN ZeroDivisionError) + PoseTracker NaN-cost crash.

Two confirmed bugs (source-verified, RED against current code):

BUG #1 (HIGH) — PoseSmoother.smooth() crashes on a single NaN keypoint:
    ml/src/utils/smoothing.py:21-33
        @njit(cache=True, fastmath=True)
        def _smoothing_factor_numba(te, cutoff):
            r = 2.0*np.pi*cutoff*te
            return r / (r + 1.0)
    fastmath rewrites `r/(r+1.0)` into `1.0/(1.0 + 1.0/r)`. When `cutoff` or
    `te` is NaN → `1.0/r` is `1.0/NaN` → numba raises `ZeroDivisionError`
    (NOT silent NaN propagation — confirmed empirically; numba's fastmath
    divide-by-zero/NaN path raises).
    NaN reaches `cutoff` at smoothing.py:89 `cutoff = min_cutoff + beta * abs(dx_filtered)`
    when `dx_filtered` is NaN, which happens when the input series `x` contains
    any NaN: `x_prev = x[0]` (smoothing.py:76) seeds NaN if the first sample is
    NaN, and `dx = (x[i] - x_prev) / dt` (smoothing.py:82) propagates NaN
    forward. ONE NaN anywhere in the series → dx NaN → dx_filtered NaN →
    cutoff NaN → `_smoothing_factor_numba(dt, NaN)` raises.
    `PoseSmoother.smooth()` (smoothing.py:375) / `smooth_3d()` (smoothing.py:412)
    call `smooth_trajectory_2d_numba` / `_one_euro_filter_sequence_numba` per
    joint per coord → ONE NaN in one keypoint one frame crashes the entire
    smooth call → entire video processing fails.
    Pipeline reaches it with NaN: `GapFiller.interpolate_low_confidence` leaves
    an all-NaN joint (n_valid==0 → `continue`) → smooth crashes on that joint.

BUG #2 (MEDIUM) — PoseTracker.update() crashes on NaN mid-hip pose:
    ml/src/detection/pose_tracker.py:331
        iou_dist = float(np.linalg.norm(predictions[i] - detection))
    where `detection` is the mid-hip (x,y) from `_get_mid_hips`
    (pose_tracker.py:287-301): `mid_hip = (LHIP + RHIP) / 2`. If both LHIP and
    RHIP are NaN (hip occlusion) → mid_hip NaN → `np.linalg.norm(... - NaN)` =
    NaN → `cost_matrix[i,j] = 0.4*NaN + 0.6*bio_dist` = NaN →
    pose_tracker.py:344 `linear_sum_assignment(cost_matrix)` raises
    `ValueError: matrix contains invalid numeric entries`.
    Secondary NaN source: `_biometric_distance` (pose_tracker.py:407-437) uses
    scipy `cosine` distance → NaN when biometric vectors contain NaN bone
    lengths (NaN hips → NaN femur/torso) → NaN bio_dist → NaN cost → same crash.

Tests stay RED until production code is fixed. Do NOT fix production code.
"""

import numpy as np
import pytest

from src.detection.pose_tracker import PoseTracker
from src.types import H36Key
from src.utils.smoothing import PoseSmoother

# ---------------------------------------------------------------------------
# BUG #1 — PoseSmoother.smooth(): single NaN keypoint → ZeroDivisionError
# ---------------------------------------------------------------------------


def test_bug1_pose_smoother_nan_keypoint_crashes():
    """RED: a single NaN in one keypoint one frame crashes PoseSmoother.smooth().

    Root cause: smoothing.py:21-33 `_smoothing_factor_numba` is decorated
    `@njit(cache=True, fastmath=True)`. fastmath rewrites `r/(r+1.0)` into
    `1.0/(1.0 + 1.0/r)`; when `cutoff` is NaN (reached via dx_filtered NaN when
    the input series has any NaN), `1.0/NaN` raises `ZeroDivisionError` under
    numba — NOT silent NaN propagation. A single NaN keypoint (e.g. a joint
    never detected across the video — GapFiller.interpolate_low_confidence
    leaves all-NaN joints when n_valid==0) crashes the ENTIRE smooth() call,
    taking down the whole video processing run.
    """
    poses = np.zeros((10, 17, 2), dtype=np.float32)
    poses[:, 0, 0] = np.linspace(0.0, 1.0, 10, dtype=np.float32)
    # Single NaN in one keypoint, one frame.
    poses[5, 0, 0] = np.nan
    poses[5, 0, 1] = np.nan

    raised = False
    exc: BaseException | None = None
    try:
        PoseSmoother(freq=30.0).smooth(poses)
    except (ZeroDivisionError, FloatingPointError) as e:
        raised = True
        exc = e

    assert not raised, (
        f"BUG #1: PoseSmoother.smooth() crashed on a single NaN keypoint: "
        f"{type(exc).__name__}: {exc}. One-Euro `_smoothing_factor_numba` "
        f"(smoothing.py:21-33) is @njit(fastmath=True); fastmath rewrites "
        f"r/(r+1)→1/(1+1/r); 1/NaN raises ZeroDivisionError under numba. "
        f"A single NaN (e.g. a keypoint never detected — GapFiller leaves "
        f"all-NaN joints) crashes the entire video processing."
    )


# ---------------------------------------------------------------------------
# BUG #2 — PoseTracker.update(): NaN mid-hip → ValueError from linear_sum_assignment
# ---------------------------------------------------------------------------


def test_bug2_pose_tracker_nan_midhip_crashes():
    """RED: a NaN mid-hip pose (LHIP+RHIP NaN) crashes PoseTracker.update().

    Root cause: pose_tracker.py:331 `iou_dist = float(np.linalg.norm(
    predictions[i] - detection))` where `detection` is the mid-hip (x,y)
    from `_get_mid_hips` (pose_tracker.py:287-301). NaN mid-hip (both LHIP and
    RHIP NaN — hip occlusion) → `np.linalg.norm(... - NaN)` = NaN →
    `cost_matrix[i,j] = 0.4*NaN + 0.6*bio_dist` = NaN → pose_tracker.py:344
    `linear_sum_assignment(cost_matrix)` raises `ValueError: matrix contains
    invalid numeric entries`. Secondary: `_biometric_distance` scipy `cosine`
    on NaN bone lengths → NaN bio_dist → NaN cost → same crash.
    PoseTracker is the legacy/custom tracking backend
    (tracking_backend="custom"); default pipeline reroutes to deepsort/sports2d
    but the custom path IS reachable. A hip-occluded detection crashes the
    tracker.
    """
    tracker = PoseTracker(max_disappeared=5, min_hits=2, fps=30.0)

    # Seed two tracks with valid poses so _associate builds a real cost matrix.
    poses = np.ones((2, 17, 2), dtype=np.float32)
    poses[0, :, 0] = np.linspace(0.4, 0.4, 17, dtype=np.float32)
    poses[1, :, 0] = np.linspace(0.6, 0.6, 17, dtype=np.float32)
    tracker.update(poses)

    # Next frame: NaN the mid-hip joints (LHIP=4, RHIP=1 in H3.6M) of pose 0.
    poses2 = poses.copy()
    poses2[0, H36Key.LHIP, :] = np.nan
    poses2[0, H36Key.RHIP, :] = np.nan

    raised = False
    exc: BaseException | None = None
    try:
        tracker.update(poses2)
    except ValueError as e:
        raised = True
        exc = e

    assert not raised, (
        f"BUG #2: PoseTracker.update() crashed on NaN mid-hip pose: "
        f"{type(exc).__name__}: {exc}. NaN mid-hip (LHIP+RHIP NaN, occlusion) "
        f"→ np.linalg.norm(predictions[i]-NaN)=NaN (pose_tracker.py:331) → "
        f"cost_matrix NaN → scipy linear_sum_assignment raises ValueError "
        f"(pose_tracker.py:344). A hip-occluded detection crashes the legacy "
        f"tracker."
    )
