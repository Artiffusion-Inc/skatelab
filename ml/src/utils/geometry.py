"""Geometric utilities for pose analysis."""

import numpy as np
from numba import njit  # type: ignore
from numpy.typing import NDArray

from ..types import FrameKeypoints, H36Key, NormalizedPose, NormalizedPose3D, TimeSeries


# Numba-jitted core functions (for performance)
@njit(cache=True, fastmath=True)  # type: ignore[reportUntypedFunctionDecorator]
def angle_3pt_rad(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Calculate angle ABC in radians (jitted).

    Args:
        a: Point A (x, y).
        b: Vertex B (x, y).
        c: Point C (x, y).

    Returns:
        Angle in radians [0, π].
    """
    ba = a - b
    bc = c - b

    cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    # Manual clamp instead of np.clip for scalar
    cosine_angle = max(-1.0, min(1.0, cosine_angle))
    angle = np.arccos(cosine_angle)

    return angle


@njit(cache=True, fastmath=True)  # type: ignore[reportUntypedFunctionDecorator]
def _distance_numba(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate Euclidean distance (jitted).

    Args:
        a: Point A (x, y).
        b: Point B (x, y).

    Returns:
        Distance.
    """
    return float(np.sqrt(np.sum((a - b) ** 2)))


def angle_3pt(a: NDArray[np.float64], b: NDArray[np.float64], c: NDArray[np.float64]) -> float:
    """Calculate angle ABC in degrees.

    Uses Numba-jitted core for performance.

    Args:
        a: Point A coordinates (x, y).
        b: Vertex point B coordinates (x, y).
        c: Point C coordinates (x, y).

    Returns:
        Angle in degrees [0, 180].
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    c = np.asarray(c, dtype=np.float64)

    # #863: the @njit(fastmath=True) core divides by ``norm*norm + 1e-8``. Under
    # fastmath NaN does not propagate through the division — a NaN vertex (e.g.
    # an occluded knee keypoint) raises ZeroDivisionError instead of returning
    # NaN, which crashes analyze() and kills the whole session. Guard before
    # the jitted core: propagate NaN so callers can skip/mask the leg.
    if not (np.all(np.isfinite(a)) and np.all(np.isfinite(b)) and np.all(np.isfinite(c))):
        return float("nan")

    angle_rad = angle_3pt_rad(a, b, c)
    return float(np.degrees(angle_rad))


def distance(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """Euclidean distance between two points.

    Uses Numba-jitted core for performance.

    Args:
        a: Point A coordinates (x, y).
        b: Point B coordinates (x, y).

    Returns:
        Distance in same units as input.
    """
    return _distance_numba(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))


@njit(cache=True, fastmath=True)  # type: ignore[reportUntypedFunctionDecorator]
def angle_3pt_batch(abc_triplets: np.ndarray) -> np.ndarray:
    """Calculate angles for multiple A-B-C triplets (jitted).

    Args:
        abc_triplets: (N, 3, 2) array of A-B-C triplets.

    Returns:
        (N,) array of angles in degrees.
    """
    n = abc_triplets.shape[0]
    angles = np.empty(n, dtype=np.float64)
    rad2deg = 180.0 / np.pi

    for i in range(n):
        a = abc_triplets[i, 0]
        b = abc_triplets[i, 1]
        c = abc_triplets[i, 2]
        angles[i] = angle_3pt_rad(a, b, c) * rad2deg

    return angles


def segment_angle(start: NDArray[np.float64], end: NDArray[np.float64]) -> float:
    """Calculate angle of a segment relative to horizontal.

    Args:
        start: Start point coordinates (x, y).
        end: End point coordinates (x, y).

    Returns:
        Angle in degrees [-180, 180], where 0° = horizontal right,
        90° = vertical up, -90° = vertical down.
    """
    start = np.asarray(start)
    end = np.asarray(end)

    # Vector from start to end
    dx = end[0] - start[0]
    dy = end[1] - start[1]

    # Angle in radians, then convert to degrees
    angle_rad = np.arctan2(dy, dx)
    angle_deg = float(np.degrees(angle_rad))

    return angle_deg


def normalize_poses(
    raw: FrameKeypoints,
    spine_indices: tuple[int, int] = (H36Key.LSHOULDER, H36Key.LHIP),
    target_spine_length: float = 0.4,
) -> NormalizedPose:
    """Normalize poses via root-centering and scale normalization.

    Vectorized — processes all frames at once using NumPy broadcasting.

    Args:
        raw: Raw keypoints (num_frames, 17, 3) with x, y, confidence.
        spine_indices: (shoulder_idx, hip_idx) for spine length calculation.
        target_spine_length: Target spine length after normalization.

    Returns:
        NormalizedPose (num_frames, 17, 2) with centered, scaled coordinates.
    """
    if raw.shape[1] != 17:
        raise ValueError(f"Expected 17 keypoints (H3.6M format), got {raw.shape[1]}")

    # Mid-hip point (N, 2). #1039: NaN in either hip (LHIP is a default
    # spine_index) propagated through `(LHIP + RHIP) / 2` into the root shift,
    # NaN-poisoning all 17 joints at centering. NaN-aware mean: average the
    # finite hips only; both-NaN → 0 (no shift, identity). All-finite case is
    # byte-identical to `(LHIP + RHIP) / 2`.
    lhip = raw[:, H36Key.LHIP, :2]
    rhip = raw[:, H36Key.RHIP, :2]
    lhip_f = np.where(np.isfinite(lhip), lhip, 0.0)
    rhip_f = np.where(np.isfinite(rhip), rhip, 0.0)
    n_finite = np.isfinite(lhip).all(axis=1).astype(np.float32) + np.isfinite(rhip).all(
        axis=1
    ).astype(np.float32)
    mid_hip_raw = np.where(
        (n_finite > 0)[:, np.newaxis],
        (lhip_f + rhip_f) / np.where(n_finite[:, np.newaxis] > 0, n_finite[:, np.newaxis], 1.0),
        0.0,
    )

    # 1. Root-centering: shift mid-hip to origin (N, 17, 2)
    centered = raw[:, :, :2] - mid_hip_raw[:, np.newaxis, :]

    # 2. Scale normalization
    shoulder_idx, hip_idx = spine_indices
    spine_vector = centered[:, shoulder_idx] - centered[:, hip_idx]  # (N, 2)
    spine_length = np.linalg.norm(spine_vector, axis=1)  # (N,)

    # #1039: NaN-blind `spine_length < 1e-6` guard lets NaN through (`NaN < 1e-6`
    # = False → picks `target/NaN` = NaN) → scale=NaN → whole (17,2) frame NaN.
    # One occluded LSHOULDER/LHIP (default spine_indices) poisoned the entire
    # 2D pose. Build a safe spine_length: NaN/degenerate → 1.0 so scale is
    # finite (identity for NaN-spine frames — the NaN joint stays NaN, the 16
    # finite joints are NOT multiplied by NaN). All-valid case is
    # byte-identical: isfinite & >=1e-6 selects the real spine_length.
    valid = np.isfinite(spine_length) & (spine_length >= 1e-6)
    spine_length_safe = np.where(valid, spine_length, 1.0)
    scale = target_spine_length / spine_length_safe  # (N,)

    normalized = centered * scale[:, np.newaxis, np.newaxis]  # (N, 17, 2)

    return normalized.astype(np.float32)


def smooth_signal(signal: TimeSeries, window: int = 5) -> TimeSeries:
    """Apply moving average smoothing to signal.

    Args:
        signal: Input signal (num_frames,).
        window: Window size for moving average (must be odd).

    Returns:
        Smoothed signal (num_frames,).
    """
    if window < 1:
        return signal

    if window % 2 == 0:
        window += 1

    if len(signal) < window:
        return signal.copy()

    # Use numpy convolution for efficient moving average
    kernel = np.ones(window) / window
    smoothed = np.convolve(signal, kernel, mode="same")

    return smoothed.astype(np.float32)


def get_mid_hip(poses: NormalizedPose) -> NDArray[np.float32]:
    """Calculate mid-hip point for each frame.

    Args:
        poses: NormalizedPose (num_frames, 17, 2).

    Returns:
        Mid-hip coordinates (num_frames, 2).
    """
    return ((poses[:, H36Key.LHIP, :] + poses[:, H36Key.RHIP, :]) / 2).astype(np.float32)


def get_mid_shoulder(poses: NormalizedPose) -> NDArray[np.float32]:
    """Calculate mid-shoulder point for each frame.

    Args:
        poses: NormalizedPose (num_frames, 17, 2).

    Returns:
        Mid-shoulder coordinates (num_frames, 2).
    """
    return ((poses[:, H36Key.LSHOULDER, :] + poses[:, H36Key.RSHOULDER, :]) / 2).astype(np.float32)


def calculate_center_of_mass(poses: NormalizedPose, frame_idx: int) -> float:
    """Calculate Center of Mass (CoM) Y-coordinate for a single frame.

    Uses anthropometric segment mass ratios from Dempster (1955) and
    Zatsiorsky (2002). The CoM is the weighted average of body segment
    positions: CoM = (1/M) * sum(m_i * p_i)

    This provides a physics-accurate measure of jump height, independent
    of landing pose. The hip-only method has 60% error for low jumps due
    to bent-knee landings artificially increasing flight time.

    Args:
        poses: NormalizedPose (num_frames, 17, 2).
        frame_idx: Frame index to calculate CoM for.

    Returns:
        CoM Y-coordinate in normalized units (lower = higher position).

    Segment mass ratios (relative to total body mass):
        - Head: 0.081
        - Torso: 0.497
        - Upper arms: 0.050 each
        - Forearms+hands: 0.030 each
        - Thighs: 0.100 each
        - Shins+feet: 0.161 each
    """
    pose = poses[frame_idx]

    # Head (HEAD keypoint in H3.6M format)
    head = pose[H36Key.HEAD]
    head_mass = 0.081

    # Torso (mid-shoulder to mid-hip midpoint)
    torso = (
        pose[H36Key.LSHOULDER] + pose[H36Key.RSHOULDER] + pose[H36Key.LHIP] + pose[H36Key.RHIP]
    ) / 4
    torso_mass = 0.497

    # Arms (elbow-wrist midpoint for upper arm, wrist for forearm)
    l_upper_arm = (pose[H36Key.LSHOULDER] + pose[H36Key.LELBOW]) / 2
    r_upper_arm = (pose[H36Key.RSHOULDER] + pose[H36Key.RELBOW]) / 2
    l_forearm = (pose[H36Key.LELBOW] + pose[H36Key.LWRIST]) / 2
    r_forearm = (pose[H36Key.RELBOW] + pose[H36Key.RWRIST]) / 2
    arm_mass_each = 0.050

    # Thighs (hip-knee midpoint)
    l_thigh = (pose[H36Key.LHIP] + pose[H36Key.LKNEE]) / 2
    r_thigh = (pose[H36Key.RHIP] + pose[H36Key.RKNEE]) / 2
    thigh_mass_each = 0.100

    # Shins+feet (knee-foot midpoint)
    l_leg = (pose[H36Key.LKNEE] + pose[H36Key.LFOOT]) / 2
    r_leg = (pose[H36Key.RKNEE] + pose[H36Key.RFOOT]) / 2
    leg_mass_each = 0.161

    # Weighted sum of Y-coordinates only (for height)
    com_y = (
        head_mass * head[1]
        + torso_mass * torso[1]
        + arm_mass_each * (l_upper_arm[1] + r_upper_arm[1] + l_forearm[1] + r_forearm[1])
        + thigh_mass_each * (l_thigh[1] + r_thigh[1])
        + leg_mass_each * (l_leg[1] + r_leg[1])
    )

    return float(com_y)


def calculate_com_trajectory(poses: NormalizedPose) -> NDArray[np.float32]:
    """Calculate Center of Mass trajectory for entire pose sequence.

    Vectorized implementation — computes all frames at once using NumPy
    broadcasting instead of per-frame Python loop.

    Args:
        poses: NormalizedPose (num_frames, 17, 2).

    Returns:
        CoM Y-coordinates (num_frames,) in normalized units.
    """
    # Segment mass ratios (Dempster 1955)
    head_mass = 0.081
    torso_mass = 0.497
    arm_mass = 0.050  # per arm (upper arm + forearm + hand)
    thigh_mass = 0.100  # per thigh
    leg_mass = 0.161  # per leg (shin + foot)

    # Vectorized segment positions: (N, 2)
    head = poses[:, H36Key.HEAD]

    torso = (
        poses[:, H36Key.LSHOULDER]
        + poses[:, H36Key.RSHOULDER]
        + poses[:, H36Key.LHIP]
        + poses[:, H36Key.RHIP]
    ) / 4

    l_upper_arm = (poses[:, H36Key.LSHOULDER] + poses[:, H36Key.LELBOW]) / 2
    r_upper_arm = (poses[:, H36Key.RSHOULDER] + poses[:, H36Key.RELBOW]) / 2
    l_forearm = (poses[:, H36Key.LELBOW] + poses[:, H36Key.LWRIST]) / 2
    r_forearm = (poses[:, H36Key.RELBOW] + poses[:, H36Key.RWRIST]) / 2

    l_thigh = (poses[:, H36Key.LHIP] + poses[:, H36Key.LKNEE]) / 2
    r_thigh = (poses[:, H36Key.RHIP] + poses[:, H36Key.RKNEE]) / 2
    l_leg = (poses[:, H36Key.LKNEE] + poses[:, H36Key.LFOOT]) / 2
    r_leg = (poses[:, H36Key.RKNEE] + poses[:, H36Key.RFOOT]) / 2

    # Weighted sum of Y-coordinates: (N,).
    # #871: NaN-aware CoM — an occluded keypoint must NOT poison the CoM and
    # flip hard_landing to a false best score. Mask each segment's contribution
    # to 0 when NaN (its mass is simply absent for that frame). All-valid case
    # is byte-identical: np.where(isfinite, term, 0) == term when finite. No
    # renormalization — Dempster masses sum to 1.3 (not 1.0), so renormalizing
    # would rescale every all-valid frame and regress the no-NaN contract.
    def _w(mass: float, y: NDArray[np.floating]) -> NDArray[np.floating]:
        term = mass * y
        return np.where(np.isfinite(y), term, 0.0)

    com_y = (
        _w(head_mass, head[:, 1])
        + _w(torso_mass, torso[:, 1])
        + _w(arm_mass, l_upper_arm[:, 1])
        + _w(arm_mass, r_upper_arm[:, 1])
        + _w(arm_mass, l_forearm[:, 1])
        + _w(arm_mass, r_forearm[:, 1])
        + _w(thigh_mass, l_thigh[:, 1])
        + _w(thigh_mass, r_thigh[:, 1])
        + _w(leg_mass, l_leg[:, 1])
        + _w(leg_mass, r_leg[:, 1])
    )

    return com_y.astype(np.float32)


def calculate_com_trajectory_3d(poses: NormalizedPose3D) -> NDArray[np.float32]:
    """Calculate Center of Mass Z-coordinate trajectory from 3D poses.

    In 3D, the Z-axis represents height above the ground (ice surface).
    This gives true vertical displacement — far more accurate than
    inferring height from 2D Y-coordinates (image space).

    Args:
        poses: NormalizedPose3D (num_frames, 17, 3).

    Returns:
        CoM Z-coordinates (num_frames,) — higher values mean higher off ice.
    """
    head_mass = 0.081
    torso_mass = 0.497
    arm_mass = 0.050
    thigh_mass = 0.100
    leg_mass = 0.161

    head = poses[:, H36Key.HEAD]

    torso = (
        poses[:, H36Key.LSHOULDER]
        + poses[:, H36Key.RSHOULDER]
        + poses[:, H36Key.LHIP]
        + poses[:, H36Key.RHIP]
    ) / 4

    l_upper_arm = (poses[:, H36Key.LSHOULDER] + poses[:, H36Key.LELBOW]) / 2
    r_upper_arm = (poses[:, H36Key.RSHOULDER] + poses[:, H36Key.RELBOW]) / 2
    l_forearm = (poses[:, H36Key.LELBOW] + poses[:, H36Key.LWRIST]) / 2
    r_forearm = (poses[:, H36Key.RELBOW] + poses[:, H36Key.RWRIST]) / 2

    l_thigh = (poses[:, H36Key.LHIP] + poses[:, H36Key.LKNEE]) / 2
    r_thigh = (poses[:, H36Key.RHIP] + poses[:, H36Key.RKNEE]) / 2
    l_leg = (poses[:, H36Key.LKNEE] + poses[:, H36Key.LFOOT]) / 2
    r_leg = (poses[:, H36Key.RKNEE] + poses[:, H36Key.RFOOT]) / 2

    # #994: NaN-aware CoM — mirror the 2D #871 mask. The 3D trajectory
    # previously propagated an occluded joint's NaN straight into com_z (no
    # `_w` guard), so ONE NaN frame → NaN CoM → `np.std(excursion)=NaN` in
    # `_detect_jump_phases_parabolic` → the `threshold < 1e-6` guard is
    # `NaN < 1e-6`=False (bypassed) → `elevated = x < NaN`=all False → silent
    # fallback to the velocity-based detector, losing parabolic precision for
    # the WHOLE video on one occluded frame. Mask each segment's contribution
    # to 0 when NaN (its mass is simply absent for that frame). All-valid case
    # is byte-identical: np.where(isfinite, term, 0) == term when finite. No
    # renormalization — same contract as the 2D path.
    def _w(mass: float, y: NDArray[np.floating]) -> NDArray[np.floating]:
        term = mass * y
        return np.where(np.isfinite(y), term, 0.0)

    # Weighted sum of Z-coordinates (index 2 = height axis)
    com_z = (
        _w(head_mass, head[:, 2])
        + _w(torso_mass, torso[:, 2])
        + _w(arm_mass, l_upper_arm[:, 2])
        + _w(arm_mass, r_upper_arm[:, 2])
        + _w(arm_mass, l_forearm[:, 2])
        + _w(arm_mass, r_forearm[:, 2])
        + _w(thigh_mass, l_thigh[:, 2])
        + _w(thigh_mass, r_thigh[:, 2])
        + _w(leg_mass, l_leg[:, 2])
        + _w(leg_mass, r_leg[:, 2])
    )

    return com_z.astype(np.float32)


def calculate_com_trajectory_2d(poses: NormalizedPose) -> NDArray[np.float32]:
    """Calculate 2D Center of Mass trajectory for entire pose sequence.

    Vectorized implementation — computes (x, y) CoM for all frames at once.

    Args:
        poses: NormalizedPose (num_frames, 17, 2).

    Returns:
        CoM (x, y) coordinates (num_frames, 2) in normalized units.
    """
    # Segment mass ratios (Dempster 1955)
    head_mass = 0.081
    torso_mass = 0.497
    arm_mass = 0.050  # per arm (upper arm + forearm + hand)
    thigh_mass = 0.100  # per thigh
    leg_mass = 0.161  # per leg (shin + foot)

    # Vectorized segment positions: (N, 2)
    head = poses[:, H36Key.HEAD]

    torso = (
        poses[:, H36Key.LSHOULDER]
        + poses[:, H36Key.RSHOULDER]
        + poses[:, H36Key.LHIP]
        + poses[:, H36Key.RHIP]
    ) / 4

    l_upper_arm = (poses[:, H36Key.LSHOULDER] + poses[:, H36Key.LELBOW]) / 2
    r_upper_arm = (poses[:, H36Key.RSHOULDER] + poses[:, H36Key.RELBOW]) / 2
    l_forearm = (poses[:, H36Key.LELBOW] + poses[:, H36Key.LWRIST]) / 2
    r_forearm = (poses[:, H36Key.RELBOW] + poses[:, H36Key.RWRIST]) / 2

    l_thigh = (poses[:, H36Key.LHIP] + poses[:, H36Key.LKNEE]) / 2
    r_thigh = (poses[:, H36Key.RHIP] + poses[:, H36Key.RKNEE]) / 2
    l_leg = (poses[:, H36Key.LKNEE] + poses[:, H36Key.LFOOT]) / 2
    r_leg = (poses[:, H36Key.RKNEE] + poses[:, H36Key.RFOOT]) / 2

    # Weighted sum of (x, y) coordinates: (N, 2).
    # #878: NaN-aware CoM — same contract as calculate_com_trajectory (#871).
    # An occluded keypoint must NOT poison the CoM and leak nan into
    # approach_direction_change (which then inflates the GOE via
    # min(1.0, nan)=1.0, #454). Mask each segment's contribution to 0 when NaN
    # (its mass is simply absent for that frame). All-valid case is
    # byte-identical. No renormalization — Dempster masses sum to 1.3.
    def _w2(mass: float, seg: NDArray[np.floating]) -> NDArray[np.floating]:
        term = mass * seg
        return np.where(np.isfinite(seg), term, 0.0)

    com = (
        _w2(head_mass, head)
        + _w2(torso_mass, torso)
        + _w2(arm_mass, l_upper_arm)
        + _w2(arm_mass, r_upper_arm)
        + _w2(arm_mass, l_forearm)
        + _w2(arm_mass, r_forearm)
        + _w2(thigh_mass, l_thigh)
        + _w2(thigh_mass, r_thigh)
        + _w2(leg_mass, l_leg)
        + _w2(leg_mass, r_leg)
    )

    return com.astype(np.float32)
