"""Biomechanics metrics computation for figure skating.

This module provides metrics for analyzing skating technique,
including joint angles, airtime, rotation speed, and edge quality.
"""

import math
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numba import njit  # type: ignore
from numpy.typing import NDArray

from ..types import (
    ElementPhase,
    H36Key,
    MetricResult,
    NormalizedPose,
    TimeSeries,
)
from ..utils.geometry import (
    angle_3pt,
    angle_3pt_batch,
    angle_3pt_rad,
    calculate_com_trajectory,
    calculate_com_trajectory_2d,
)
from .element_defs import is_spin
from .jump_classifier import classify_jump
from .spin_classifier import classify_spin, detect_spin

if TYPE_CHECKING:
    from .element_defs import ElementDef


@njit(cache=True, fastmath=True)  # type: ignore[reportUntypedFunctionDecorator]
def _compute_knee_angle_series_numba(
    poses: np.ndarray,
    hip_idx: int,
    knee_idx: int,
    foot_idx: int,
) -> np.ndarray:
    """Compute knee angle series (jitted).

    Args:
        poses: (num_frames, 17, 2) pose array.
        hip_idx: Hip keypoint index (will be converted to int).
        knee_idx: Knee keypoint index (will be converted to int).
        foot_idx: Foot keypoint index (will be converted to int).

    Returns:
        (num_frames,) knee angles in degrees.
    """
    num_frames = poses.shape[0]
    angles = np.zeros(num_frames, dtype=np.float32)
    rad2deg = 180.0 / np.pi

    for i in range(num_frames):
        pose = poses[i]
        hip = pose[hip_idx]
        knee = pose[knee_idx]
        foot = pose[foot_idx]

        angle_rad = angle_3pt_rad(hip, knee, foot)
        angles[i] = angle_rad * rad2deg

    return angles


@njit(cache=True, fastmath=True)  # type: ignore[reportUntypedFunctionDecorator]
def _compute_trunk_lean_series_numba(poses: np.ndarray) -> np.ndarray:
    """Compute trunk lean angle series (jitted).

    Args:
        poses: (num_frames, 17, 2) pose array.

    Returns:
        (num_frames,) trunk lean angles in degrees.
    """
    num_frames = poses.shape[0]
    leans = np.zeros(num_frames, dtype=np.float32)
    rad2deg = 180.0 / np.pi

    # H36Key indices (hardcoded for Numba compatibility)
    # LHIP=4, RHIP=8, LSHOULDER=11, RSHOULDER=14
    l_hip = 4
    r_hip = 1
    l_shoulder = 11
    r_shoulder = 14

    for i in range(num_frames):
        pose = poses[i]
        # Mid-hip to mid-shoulder vector
        mid_hip = (pose[l_hip] + pose[r_hip]) * 0.5
        mid_shoulder = (pose[l_shoulder] + pose[r_shoulder]) * 0.5

        spine_vector = mid_shoulder - mid_hip

        # Angle from vertical (0, -1) - upward in normalized coords
        # atan2(x, -y) gives angle from vertical
        lean = np.arctan2(spine_vector[0], -spine_vector[1])
        leans[i] = lean * rad2deg

    return leans


class BiomechanicsAnalyzer:
    """Compute biomechanics metrics for skating technique analysis."""

    def __init__(self, element_def: "ElementDef") -> None:
        """Initialize analyzer with element definition.

        Args:
            element_def: ElementDef with ideal metric ranges.
        """
        self._element_def = element_def

    def analyze(
        self,
        poses: NormalizedPose | NDArray[np.float32],
        phases: ElementPhase,
        fps: float,
        com_trajectory: NDArray[np.float32] | None = None,
    ) -> list[MetricResult]:
        """Compute all relevant metrics for the element.

        Args:
            poses: Normalized pose sequence (num_frames, 17, 2) or (num_frames, 17, 3).
            phases: Element phase boundaries.
            fps: Video frame rate.
            com_trajectory: Pre-computed CoM trajectory (optional, for caching).

        Returns:
            List of MetricResult with computed values and goodness assessment.
        """
        results: list[MetricResult] = []
        is_3d = poses.shape[2] == 3

        # For Numba-jitted functions that expect 2D, use xy projection
        poses_2d = poses[:, :, :2] if is_3d else poses

        # Compute metrics based on element type
        if self._element_def.rotations > 0:
            # Jump metrics — pass 3D poses for yaw cross-check when available
            poses_3d = poses if is_3d else None
            results.extend(
                self._analyze_jump(
                    poses_2d, phases, fps, com_trajectory=com_trajectory, poses_3d=poses_3d
                )
            )
        elif is_spin(self._element_def.name):
            # Spin metrics
            results.extend(self._analyze_spin(poses_2d, phases, fps))
        else:
            # Step/edge metrics
            results.extend(self._analyze_step(poses_2d, phases, fps))

        # Common metrics for all elements
        results.extend(self._analyze_common(poses_2d, phases, fps))

        # Mark goodness based on ideal ranges
        for result in results:
            if result.name in self._element_def.ideal_metrics:
                min_good, max_good = self._element_def.ideal_metrics[result.name]
                result.is_good = min_good <= result.value <= max_good
                object.__setattr__(result, "reference_range", (min_good, max_good))
            else:
                # #856: this metric has no ideal range for the element (the
                # element_def does not bond it — e.g. max_height for
                # toe_loop/flip, which use relative_jump_height instead). The
                # sentinel (0, 0) means "undefined", and is_good=False would
                # lie to downstream (multi_score subscores, GOE) that a normal
                # value is a defect. No data to judge → neutral (True).
                result.is_good = True

        return results

    def _analyze_jump(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
        com_trajectory: NDArray[np.float32] | None = None,
        poses_3d: NDArray[np.float32] | None = None,
    ) -> list[MetricResult]:
        """Analyze jump-specific metrics.

        Args:
            poses: 2D poses (num_frames, 17, 2).
            phases: Element phase boundaries.
            fps: Frame rate.
            com_trajectory: Pre-computed CoM trajectory (optional).
            poses_3d: Original 3D poses (num_frames, 17, 3) for yaw cross-check.
        """
        results: list[MetricResult] = []

        # Airtime
        airtime = self.compute_airtime(phases, fps)
        results.append(
            MetricResult(
                name="airtime",
                value=airtime,
                unit="s",
                is_good=False,  # Will be updated based on ideal range
                reference_range=(0, 0),
            )
        )

        # Jump height (CoM-based for physics accuracy)
        height = self.compute_jump_height_com(poses, phases, com_trajectory=com_trajectory)
        results.append(
            MetricResult(
                name="max_height",
                value=height,
                unit="norm",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Landing quality
        landing_quality = self.compute_landing_quality(poses, phases)
        results.append(
            MetricResult(
                name="landing_knee_angle",
                value=landing_quality,
                unit="deg",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Arm position
        arm_score = self.compute_arm_position(poses)
        results.append(
            MetricResult(
                name="arm_position_score",
                value=arm_score,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Rotation speed
        rot_speed = self.compute_rotation_speed(poses, phases, fps)
        results.append(
            MetricResult(
                name="rotation_speed",
                value=rot_speed,
                unit="deg/s",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Landing quality (OOFSkate approach: camera-independent)
        landing_stab = self.compute_landing_knee_stability(poses, phases)
        results.append(
            MetricResult(
                name="landing_knee_stability",
                value=landing_stab,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        landing_trunk = self.compute_landing_trunk_recovery(poses, phases)
        results.append(
            MetricResult(
                name="landing_trunk_recovery",
                value=landing_trunk,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        rel_height = self.compute_relative_jump_height(poses, phases, com_trajectory=com_trajectory)
        results.append(
            MetricResult(
                name="relative_jump_height",
                value=rel_height,
                unit="ratio",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Landing CoM velocity (negative = hard landing)
        landing_vel = self.compute_landing_com_velocity(poses, phases, fps)
        results.append(
            MetricResult(
                name="landing_com_velocity",
                value=landing_vel,
                unit="norm/s",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Landing smoothness (post-landing CoM stability)
        landing_smooth = self.compute_landing_smoothness(poses, phases, fps)
        results.append(
            MetricResult(
                name="landing_smoothness",
                value=landing_smooth,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Hard landing detection (CoM vertical velocity at impact)
        hard_landing = self.compute_hard_landing(poses, phases, fps)
        results.append(
            MetricResult(
                name="hard_landing",
                value=hard_landing,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Toe assist proxy (clean edge detection)
        toe_assist = self.compute_toe_assist_proxy(poses, phases, fps)
        results.append(
            MetricResult(
                name="toe_assist_proxy",
                value=toe_assist,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Approach torso lean
        approach_lean = self.compute_approach_torso_lean(poses, phases)
        results.append(
            MetricResult(
                name="approach_torso_lean",
                value=approach_lean,
                unit="deg",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Approach direction change
        approach_curve = self.compute_approach_direction_change(poses, phases, fps)
        results.append(
            MetricResult(
                name="approach_direction_change",
                value=approach_curve,
                unit="deg",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # GOE Proxy Score
        goe = self.compute_goe_score(poses, phases, fps)
        results.append(
            MetricResult(
                name="goe_score",
                value=goe,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Total rotation & rotation count (with yaw cross-check)
        total_rotation_deg, rotation_count = self.compute_total_rotation_from_poses(
            poses, phases, fps
        )

        # Cross-check with yaw delta method (requires 3D poses)
        rotation_discrepancy = False
        if poses_3d is not None and poses_3d.shape[-1] == 3:
            # #554: inclusive-end slice to match flight height at 797/1515.
            # np.arange(takeoff, landing) drops the landing frame — rotation
            # count ~1 frame short, off by ~1-2° on a triple (crosses the
            # 0.25-revolution GOE threshold).
            flight_indices = np.arange(phases.takeoff, phases.landing + 1)
            yaw_total, yaw_count, clamped = self.compute_rotation_yaw_delta(
                poses_3d, flight_indices, fps
            )
            discrepancy = abs(rotation_count - yaw_count)
            rotation_discrepancy = discrepancy > 0.5
            # Prefer yaw method if discrepancy detected and fewer clamped frames (more reliable guard)
            if rotation_discrepancy and clamped.sum() < 3:
                rotation_count = yaw_count
                total_rotation_deg = abs(yaw_total)

        results.append(
            MetricResult(
                name="total_rotation_deg",
                value=total_rotation_deg,
                unit="deg",
                is_good=False,
                reference_range=(0, 0),
            )
        )
        results.append(
            MetricResult(
                name="rotation_count",
                value=rotation_count,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )
        results.append(
            MetricResult(
                name="rotation_discrepancy",
                value=rotation_discrepancy,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Under-rotation (target based on element definition)
        target_rotations = self._element_def.rotations
        under_rotation_deg = compute_under_rotation(total_rotation_deg, target_rotations)
        results.append(
            MetricResult(
                name="under_rotation_deg",
                value=under_rotation_deg,
                unit="deg",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Jump type classification
        has_toe_pick = bool(self._element_def.has_toe_pick)
        takeoff_direction = "forward" if self._element_def.name == "axel" else "backward"
        _jump_type_name, jump_type_confidence = classify_jump(
            rotation_count=rotation_count,
            has_toe_pick_signal=has_toe_pick,
            takeoff_direction=takeoff_direction,
        )
        results.append(
            MetricResult(
                name="jump_type",
                value=jump_type_confidence,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        return results

    def _analyze_step(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> list[MetricResult]:
        """Analyze step/edge-specific metrics.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries (used for duration calc).
            fps: Frame rate (used for duration calc).
        """
        results: list[MetricResult] = []

        # Knee angle (average during element)
        knee_angles = self.compute_knee_angle_series(poses, side="left")
        avg_knee_angle = float(np.mean(knee_angles))
        results.append(
            MetricResult(
                name="knee_angle",
                value=avg_knee_angle,
                unit="deg",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Trunk lean
        trunk_lean = self.compute_trunk_lean(poses)
        # Use average lean across element
        avg_lean = float(np.mean(trunk_lean))
        results.append(
            MetricResult(
                name="trunk_lean",
                value=avg_lean,
                unit="deg",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Edge indicator
        edge_ind = self.compute_edge_indicator(poses, side="left")
        # Measure edge change (variance)
        edge_change = float(np.std(edge_ind))
        results.append(
            MetricResult(
                name="edge_change_smoothness",
                value=edge_change,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Spread eagle angle
        se_angle = self.compute_spread_eagle_angle(poses)
        # #962: np.nanmax (NOT np.max) so a NaN frame in the series (occluded
        # RKNEE/RFOOT that slips past the #976 producer guard, or a caller-
        # supplied NaN se_angle) does not poison the peak into NaN. nanmax
        # skips NaN frames; if every frame is NaN there is no data — 0.0
        # instead of NaN, which breaks JSON serialization and the GOE
        # composite. Mirrors #903 (compute_rotation_speed) nanmax+isfinite
        # and #993 (get_spine_length) nanmean. Identity on all-finite input.
        peak_se = float(np.nanmax(se_angle)) if np.isfinite(se_angle).any() else 0.0
        if not np.isfinite(peak_se):
            peak_se = 0.0
        results.append(
            MetricResult(
                name="spread_eagle_angle",
                value=peak_se,
                unit="deg",
                is_good=peak_se >= 150,
                reference_range=(150, 180),
            )
        )

        # Ina Bauer score (only meaningful when spread eagle angle >= 150)
        ib_score = self.compute_ina_bauer_score(poses, se_angle=se_angle)
        # #962: np.nanmax + isfinite fallback — see peak_se above.
        peak_ib = float(np.nanmax(ib_score)) if np.isfinite(ib_score).any() else 0.0
        if not np.isfinite(peak_ib):
            peak_ib = 0.0
        results.append(
            MetricResult(
                name="ina_bauer_score",
                value=peak_ib,
                unit="score",
                is_good=peak_ib >= 0.7,
                reference_range=(0.7, 1.0),
            )
        )

        # Spiral indicator (foot Y difference - large = one-foot element)
        spiral_ind = self.compute_spiral_indicator(poses)
        # #962: np.nanmax + isfinite fallback — see peak_se above.
        max_spiral = float(np.nanmax(spiral_ind)) if np.isfinite(spiral_ind).any() else 0.0
        if not np.isfinite(max_spiral):
            max_spiral = 0.0
        results.append(
            MetricResult(
                name="spiral_indicator",
                value=max_spiral,
                unit="norm",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        return results

    def _analyze_spin(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> list[MetricResult]:
        """Analyze spin-specific metrics.

        Detects spin segments, classifies spin type, and computes
        angular velocity metrics.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            fps: Frame rate.

        Returns:
            List of MetricResult for spin metrics.
        """
        results: list[MetricResult] = []

        # Compute shoulder axis angular velocity for spin detection
        left_shoulder = poses[:, H36Key.LSHOULDER]
        right_shoulder = poses[:, H36Key.RSHOULDER]
        shoulder_vector = right_shoulder - left_shoulder
        angles = np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])
        unwrapped = np.unwrap(angles)
        angular_velocity = np.abs(np.gradient(unwrapped) * fps) * (180.0 / np.pi)
        # #912: NaN shoulder on a spin frame (occlusion during fast rotation)
        # -> shoulder_vector NaN -> arctan2(nan, x) = NaN -> np.unwrap(NaN) = NaN
        # -> np.gradient(NaN) = NaN -> angular_velocity carries NaN frames.
        # Bare np.max(angular_velocity[spin_mask]) propagates NaN -> spin_peak_velocity
        # = NaN, and the leaf compute_total_rotation(unwrapped, fps) does
        # abs(unwrapped[-1] - unwrapped[0]) = NaN on NaN endpoints -> total_rotation_deg
        # / rotation_count = NaN. Guard the inline unwrapped series at the trust
        # boundary (the leaf helper stays unguarded by design — #913 guards
        # upstream in compute_total_rotation_from_poses; _analyze_spin builds its
        # own unwrapped inline so the guard belongs here). Return the 0.0 sentinel
        # (neutral "no data") matching the degenerate-phases guards, instead of NaN.
        # Identity on all-finite input. ponytail: all-NaN shoulders yield 0.0
        # (biased finite, not NaN); upgrade to inf sentinel if a degenerate-spin
        # signal is needed.
        if not np.all(np.isfinite(unwrapped)):
            unwrapped = np.where(np.isfinite(unwrapped), unwrapped, 0.0)

        # Hip Y position for spin detection
        hip_y = (poses[:, H36Key.LHIP][:, 1] + poses[:, H36Key.RHIP][:, 1]) / 2.0

        # Detect spin
        is_spin, duration_s, hip_y_range, spin_mask = detect_spin(
            angular_velocity_series=angular_velocity,
            hip_y_series=hip_y,
            fps=fps,
        )

        # Spin peak velocity (maximum angular velocity DURING the spin).
        # #858: np.max over the whole sequence let a transient shoulder-vector
        # jump OUTSIDE the spin (entry arm swing, exit flail, tracking glitch)
        # — a gradient spike unrelated to the spin — become the reported peak.
        # Restrict to the detected spin frames; 0.0 when no spin is detected.
        if is_spin and np.any(spin_mask):
            # #912: np.nanmax (NOT np.max) so a NaN frame in angular_velocity
            # (occluded LSHOULDER/RSHOULDER that slips past the unwrapped guard
            # above, or a NaN injected by detect_spin's hip path) does not
            # poison the peak into NaN. nanmax skips NaN frames; if every
            # masked frame is NaN there is no data — 0.0 instead of NaN, which
            # breaks JSON serialization and the GOE composite. Mirrors #962
            # (_analyze_step) nanmax+isfinite and #903 (compute_rotation_speed).
            # Identity on all-finite input.
            peak_velocity = float(np.nanmax(angular_velocity[spin_mask]))
            if not np.isfinite(peak_velocity):
                peak_velocity = 0.0
        else:
            peak_velocity = 0.0
        results.append(
            MetricResult(
                name="spin_peak_velocity",
                value=peak_velocity,
                unit="deg/s",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Classify spin type
        mean_velocity = float(np.mean(angular_velocity)) if len(angular_velocity) > 0 else 0.0
        _spin_type_name, spin_type_confidence = classify_spin(
            duration_s=duration_s if is_spin else 0.0,
            hip_y_range=hip_y_range,
            angular_velocity_mean=mean_velocity,
        )
        results.append(
            MetricResult(
                name="spin_type",
                value=spin_type_confidence,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        # Also compute rotation metrics for spins
        total_rotation_deg, rotation_count = compute_total_rotation(unwrapped, fps)
        results.append(
            MetricResult(
                name="total_rotation_deg",
                value=total_rotation_deg,
                unit="deg",
                is_good=False,
                reference_range=(0, 0),
            )
        )
        results.append(
            MetricResult(
                name="rotation_count",
                value=rotation_count,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        return results

    def _analyze_common(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> list[MetricResult]:
        """Analyze metrics common to all elements.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            fps: Frame rate (reserved for future use).
        """
        results: list[MetricResult] = []

        # Symmetry
        symmetry = self.compute_symmetry(poses, phases)
        results.append(
            MetricResult(
                name="symmetry",
                value=symmetry,
                unit="score",
                is_good=False,
                reference_range=(0, 0),
            )
        )

        return results

    def compute_angle_series(
        self,
        poses: NormalizedPose,
        joint_a: int,
        joint_b: int,
        joint_c: int,
    ) -> TimeSeries:
        """Compute angle ABC for each frame (vectorized).

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            joint_a: Index of first joint.
            joint_b: Index of vertex joint.
            joint_c: Index of third joint.

        Returns:
            TimeSeries of angles in degrees.
        """
        a = poses[:, joint_a]  # (N, 2)
        b = poses[:, joint_b]  # (N, 2)
        c = poses[:, joint_c]  # (N, 2)

        # Build triplet array for batch processing: (N, 3, 2)
        abc_triplets = np.stack([a, b, c], axis=1)
        return angle_3pt_batch(abc_triplets).astype(np.float32)

    def compute_angular_velocity(self, angle_series: TimeSeries, fps: float) -> TimeSeries:
        """Compute angular velocity from angle series.

        Args:
            angle_series: Angles in degrees (num_frames,).
            fps: Frame rate.

        Returns:
            Angular velocity in deg/s.
        """
        # Unwrap before differentiating so a wrap-around at ±180° does not
        # produce a ~360° jump. Idempotent for already-continuous series. #422
        unwrapped = np.unwrap(np.radians(angle_series))
        gradient = np.degrees(np.gradient(unwrapped))
        return gradient * fps

    def compute_airtime(self, phases: ElementPhase, fps: float) -> float:
        """Compute flight time.

        Args:
            phases: Element phase boundaries.
            fps: Frame rate.

        Returns:
            Airtime in seconds.
        """
        return phases.airtime_sec(fps)

    def compute_jump_height(self, hip_y_series: TimeSeries, phases: ElementPhase) -> float:
        """Compute maximum jump height using hip trajectory.

        .. deprecated::
            This method has ~60% error for low jumps due to landing knee flexion.
            Use compute_jump_height_com() for physics-accurate results using
            Center of Mass trajectory.

        Args:
            hip_y_series: Hip Y coordinates (lower = higher).
            phases: Element phase boundaries.

        Returns:
            Maximum height in normalized units.

        Warning:
            Deprecated - use compute_jump_height_com() for accurate results.
            The hip-only method overestimates low jumps by up to 60% because
            skaters land with bent knees, which affects hip position but not CoM.
        """
        warnings.warn(
            "compute_jump_height() is deprecated due to 60% error for low jumps. "
            "Use compute_jump_height_com() for physics-accurate results using "
            "Center of Mass trajectory instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Get landing hip Y (reference level)
        landing_y = hip_y_series[phases.landing]

        # Get minimum hip Y (peak height)
        # #899: np.nanmin (NOT np.min) so a NaN hip Y on a flight frame
        # (occluded hip) does not poison the min into NaN. Deprecated code
        # still runs and feeds reports until removed; the deprecation does
        # not excuse a NaN-leak.
        flight_y = hip_y_series[phases.takeoff : phases.landing]
        peak_y = np.nanmin(flight_y)
        if not np.isfinite(landing_y) or not np.isfinite(peak_y):
            return 0.0

        return float(landing_y - peak_y)

    def compute_jump_height_com(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        com_trajectory: NDArray[np.float32] | None = None,
    ) -> float:
        """Compute jump height using Center of Mass trajectory.

        This method provides physics-accurate jump height independent of
        landing pose. During flight, the CoM follows a parabolic trajectory
        governed only by gravity: h(t) = h₀ + v₀t - ½gt²

        The hip-only method has ~60% error for low jumps because skaters
        land with bent knees, which artificially increases the measured
        "flight time" and therefore the computed height.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            com_trajectory: Pre-computed CoM trajectory (optional, for caching).

        Returns:
            Maximum jump height in normalized units (peak - takeoff CoM).

        Reference:
            - Dempster (1955) - Space requirements of the seated operator
            - Zatsiorsky (2002) - Kinetics of human motion
            - Gemini Research (2026) - 60% error in hip-only method
        """
        if com_trajectory is None:
            com_trajectory = calculate_com_trajectory(poses)

        # Guard against degenerate phases (phase detector failure): empty slice
        # would crash np.min. Sibling compute_relative_jump_height guards the same. #424
        if phases.takeoff >= phases.landing:
            return 0.0

        # Get CoM at takeoff (baseline)
        takeoff_com = com_trajectory[phases.takeoff]

        # Find minimum CoM during flight (maximum height).
        # Y is inverted in normalized coords, so min Y = max height.
        # #879: np.nanmin (NOT np.min) so a NaN CoM frame (fully-occluded
        # flight frame) does not poison the min into nan. The NaN-aware CoM
        # (#871) keeps CoM finite when a few keypoints are occluded, but a
        # fully-occluded flight frame still yields NaN. nanmin skips NaN
        # frames; if every flight frame is NaN there is no data -- return 0.0
        # (neutral "no height") instead of nan, which leaks into max_height
        # value and breaks JSON serialization (RFC 8259), the recommender, and
        # frontend display.
        flight_com = com_trajectory[phases.takeoff : phases.landing + 1]
        peak_com = float(np.nanmin(flight_com))
        if not np.isfinite(peak_com):
            return 0.0

        # Height = takeoff CoM - peak CoM (both inverted, so difference is positive)
        height = float(takeoff_com - peak_com)
        if not np.isfinite(height):
            return 0.0
        return height

    def compute_landing_quality(self, poses: NormalizedPose, phases: ElementPhase) -> float:
        """Compute landing knee angle.

        Uses the more-bent knee (landing leg) since the free leg
        is typically extended during landing.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.

        Returns:
            Knee angle in degrees at landing frame.
        """
        landing_frame = min(phases.landing, len(poses) - 1)

        left_hip = poses[landing_frame, H36Key.LHIP]
        left_knee = poses[landing_frame, H36Key.LKNEE]
        left_foot = poses[landing_frame, H36Key.LFOOT]
        left_angle = angle_3pt(left_hip, left_knee, left_foot)

        right_hip = poses[landing_frame, H36Key.RHIP]
        right_knee = poses[landing_frame, H36Key.RKNEE]
        right_foot = poses[landing_frame, H36Key.RFOOT]
        right_angle = angle_3pt(right_hip, right_knee, right_foot)

        # #863: angle_3pt returns NaN for an occluded (NaN) knee. Python min()
        # is asymmetric on NaN (min(nan, val) = nan, #454) and would propagate
        # NaN even when the other leg is valid. np.nanmin ignores NaN and takes
        # the valid leg's angle; both NaN → nanmin warns + returns NaN.
        return float(np.nanmin([left_angle, right_angle]))

    def compute_landing_knee_stability(self, poses: NormalizedPose, phases: ElementPhase) -> float:
        """Compute post-landing knee stability score.

        Measures how stable the knees are after landing by analyzing the
        standard deviation of knee angles during the post-landing phase.
        Camera-independent: uses internal body angles only.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.

        Returns:
            Stability score in [0.0, 1.0] where 1.0 = perfectly stable.
            Formula: np.clip(1.0 - avg_std / 15.0, 0.0, 1.0)
            Returns 1.0 if no post-landing data available.
        """
        # Check if we have post-landing data
        if phases.end <= phases.landing + 1:
            return 1.0

        # Extract post-landing frames (landing+1 to end)
        post_landing_start = phases.landing + 1
        # #556: cap at len(poses) — same pattern as compute_landing_smoothness
        # at :959. Without the cap, phases.end + 1 can be >= len(poses),
        # returning an empty array → np.mean / np.std over empty returns NaN
        # silently with a RuntimeWarning. Score becomes NaN → propagates to
        # overall score and UI.
        post_landing_end = min(phases.end + 1, len(poses))
        post_landing_poses = poses[post_landing_start:post_landing_end]

        # Compute knee angle series for left and right.
        # #868: compute_knee_angle_series emits NaN for occluded frames (NaN
        # guard in the Python wrapper — the @njit core cannot guard under
        # fastmath), so std must be NaN-safe.
        left_knee_angles = self.compute_knee_angle_series(post_landing_poses, side="left")
        right_knee_angles = self.compute_knee_angle_series(post_landing_poses, side="right")

        # Calculate standard deviation of knee angles (NaN-safe: skip occluded
        # frames). np.std propagates NaN over the whole array → avg_std NaN →
        # max(0.0, nan)=0.0 (#454 arg-order) falsely graded occlusion as worst.
        left_std = float(np.nanstd(left_knee_angles))
        right_std = float(np.nanstd(right_knee_angles))

        # Average standard deviation — only over sides with finite data.
        stds = [s for s in (left_std, right_std) if np.isfinite(s)]
        if not stds:
            return 1.0
        avg_std = sum(stds) / len(stds)

        # Convert to stability score: lower std = higher stability.
        # 15 degrees is a reasonable threshold for "unstable".
        # #868: np.clip (NaN-safe after the finite guard) instead of Python
        # max(0.0, ...) which is arg-order NaN-unsafe (#454).
        stability = float(np.clip(1.0 - avg_std / 15.0, 0.0, 1.0))

        return stability

    def compute_landing_trunk_recovery(self, poses: NormalizedPose, phases: ElementPhase) -> float:
        """Compute post-landing trunk recovery score.

        Measures how upright the trunk is during the post-landing phase.
        Camera-independent: uses spine-to-hip angle relative to vertical.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.

        Returns:
            Recovery score in [0.0, 1.0] where 1.0 = perfectly upright.
            Formula: np.clip(1.0 - avg_lean / 30.0, 0.0, 1.0)
            Returns 1.0 if no post-landing data available.
        """
        # Check if we have post-landing data
        if phases.end <= phases.landing:
            return 1.0

        # Extract post-landing frames (landing+1 to end)
        post_landing_start = phases.landing + 1
        # #556: cap at len(poses) — same pattern as compute_landing_smoothness
        # at :959. Without the cap, phases.end + 1 can be >= len(poses),
        # returning an empty array → np.mean / np.std over empty returns NaN
        # silently with a RuntimeWarning. Score becomes NaN → propagates to
        # overall score and UI.
        post_landing_end = min(phases.end + 1, len(poses))
        post_landing_poses = poses[post_landing_start:post_landing_end]

        # Compute trunk lean for post-landing frames
        trunk_lean = self.compute_trunk_lean(post_landing_poses)

        # Calculate average absolute lean during post-landing — NaN-safe.
        # #865: a NaN shoulder keypoint (occlusion — normal on landing when the
        # skater turns away) propagates through mid_shoulder → spine_vector →
        # arctan2 into trunk_lean. The plain mean of abs(trunk_lean) over a NaN
        # frame = nan, then 1.0 - nan/30.0 = nan and Python max(0.0, nan) = 0.0
        # (#454 arg-order NaN-unsafe) — an occluded shoulder reads as the WORST
        # recovery (0.0), a false "poor recovery" diagnosis when the truth is
        # "no data for that frame". Skip occluded frames via np.nanmean; if
        # every frame is occluded, return 1.0 ("no data → no penalty", not 0.0).
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            avg_lean = float(np.nanmean(np.abs(trunk_lean)))
        if not np.isfinite(avg_lean):
            return 1.0

        # Convert to recovery score: lower lean = higher recovery.
        # 30 degrees is a reasonable threshold for "poor recovery".
        # #865: np.clip (NaN-safe after the finite guard) instead of Python
        # max(0.0, ...) which is arg-order NaN-unsafe (#454).
        recovery = float(np.clip(1.0 - avg_lean / 30.0, 0.0, 1.0))

        return float(recovery)

    def compute_landing_com_velocity(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> float:
        """Compute CoM vertical velocity at landing frame.

        Negative value indicates downward motion (hard landing).
        Uses backward difference on CoM Y trajectory.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            fps: Frame rate.

        Returns:
            CoM vertical velocity in norm/s. Negative = downward.
            Returns 0.0 if landing frame is invalid or no previous frame.
        """
        if phases.landing <= 0 or phases.landing >= len(poses):
            return 0.0

        com_trajectory = calculate_com_trajectory(poses)
        # In normalized coords Y increases downward.
        # Backward difference: negate so downward = negative velocity.
        # #880: guard NaN leak — calculate_com_trajectory is NaN-aware (#871)
        # but a fully occluded frame can still produce a non-finite CoM; the
        # landing velocity must never leak NaN into AnalysisReport / JSON.
        velocity = -(com_trajectory[phases.landing] - com_trajectory[phases.landing - 1]) * fps
        if not np.isfinite(velocity):
            return 0.0
        return float(velocity)

    def compute_landing_smoothness(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> float:
        """Compute post-landing CoM velocity stability score.

        Measures how smooth the landing is by analyzing CoM velocity stability
        over a 0.5-second window after landing. Lower velocity variation = higher score.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            fps: Frame rate.

        Returns:
            Smoothness score in [0.0, 1.0] where 1.0 = perfectly stable.
            Returns 1.0 if no post-landing data available.
        """
        if phases.end <= phases.landing + 1:
            return 1.0

        # #1114: NaN/inf fps guard — `int(0.5 * NaN)` raises ValueError.
        # Corrupt video metadata (no frame rate) must not crash the
        # smoothness score; the window-size step is the first fps use.
        if not math.isfinite(fps) or fps <= 0:
            return 1.0

        post_landing_start = phases.landing + 1
        post_landing_end = min(phases.end + 1, len(poses))
        window_frames = int(0.5 * fps)
        post_landing_end = min(post_landing_start + window_frames, post_landing_end)

        if post_landing_end <= post_landing_start:
            return 1.0

        com_trajectory = calculate_com_trajectory(poses)
        post_com = com_trajectory[post_landing_start:post_landing_end]

        # Velocities in same convention as compute_landing_com_velocity
        velocities = -(post_com[1:] - post_com[:-1]) * fps

        if len(velocities) == 0:
            return 1.0

        # #870: NaN-safe std. The NaN-aware CoM (#871) keeps the CoM finite when
        # a few keypoints are occluded, but a fully-occluded post-landing frame
        # still yields NaN velocities. np.std propagates NaN (whole window NaN),
        # then Python max(0.0, nan)=0.0 (arg-order #454) falsely grades a smooth
        # landing as the worst. nanstd ignores NaN frames; if every frame is
        # NaN there is no data — return neutral 1.0 (matches the no-data early
        # returns above) instead of 0.0.
        finite = velocities[np.isfinite(velocities)]
        if len(finite) == 0:
            return 1.0
        std_velocity = float(np.std(finite))
        # 0.2 norm/s std threshold for "unstable"
        smoothness = float(np.clip(1.0 - std_velocity / 0.2, 0.0, 1.0))
        return smoothness

    def compute_hard_landing(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> float:
        """Detect hard landing via CoM vertical velocity at impact.

        Hard landing = excessive downward velocity at landing frame.
        Uses backward difference on CoM Y trajectory.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            fps: Frame rate.

        Returns:
            Score in [0.0, 1.0] where 1.0 = soft landing, 0.0 = very hard.
        """
        if phases.landing <= 0 or phases.landing >= len(poses):
            return 1.0

        com_trajectory = calculate_com_trajectory(poses)

        # CoM vertical velocity at landing (backward difference)
        # In normalized coords Y increases downward, so positive vy = downward motion
        vy_y = (com_trajectory[phases.landing] - com_trajectory[phases.landing - 1]) * fps

        # #871: NaN guard — if both landing frames are entirely occluded the
        # NaN-aware CoM still yields NaN; return neutral 1.0 (soft default,
        # matching the no-data early returns above) rather than the arg-order
        # trap min(1.0, nan)=1.0 → max(0.0,1.0)=1.0 which silently masked hard
        # impacts. np.isfinite keeps the all-valid path identical.
        if not np.isfinite(vy_y):
            return 1.0

        # Threshold: 2.0 norm/s downward = hard landing
        # 0.0 = soft
        score = float(np.clip(1.0 - vy_y / 2.0, 0.0, 1.0))
        return score

    def compute_toe_assist_proxy(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> float:
        """Detect toe assist vs clean edge landing via CoM velocity spike.

        Toe assist = sudden impact spike at landing (high deceleration).
        Clean edge = smooth deceleration over multiple frames.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            fps: Frame rate.

        Returns:
            Score in [0.0, 1.0] where 1.0 = clean edge, 0.0 = toe assist.
        """
        if phases.landing <= 0 or phases.landing >= len(poses) - 1:
            return 1.0  # Cannot assess

        com_trajectory = calculate_com_trajectory(poses)

        # Compute vertical velocity (Y increases downward, so negative = upward)
        vy_y = -(com_trajectory[1:] - com_trajectory[:-1]) * fps

        # Look at landing frame and 2 frames after
        landing_idx = phases.landing
        post_end = min(landing_idx + 3, len(vy_y))

        if post_end <= landing_idx:
            return 1.0

        # Compute acceleration (change in vy)
        start_idx = max(0, landing_idx - 1)
        ay = np.diff(vy_y[start_idx:post_end])
        if len(ay) == 0:
            return 1.0

        # Peak deceleration (most negative = hardest impact). #877: np.nanmin
        # (NOT np.min) so a NaN acceleration frame (fully-occluded CoM, no
        # keypoint visible) does not poison the min. The NaN-aware CoM (#871)
        # keeps CoM finite when a few keypoints are occluded, but a fully-
        # occluded landing frame still yields NaN vy_y -> NaN ay.
        peak_decel = float(np.nanmin(ay))
        if not np.isfinite(peak_decel):
            # No finite acceleration data — cannot assess. Return neutral
            # (clean-edge proxy), not 0.0 (toe assist) and not 1.0-via-NaN.
            return 1.0

        # Threshold: -5.0 norm/s^2 = toe assist territory
        # 0.0 = gentle deceleration
        # #877: np.clip (NaN-safe after the finite guard) instead of Python
        # max(0.0, min(1.0, ...)) which is arg-order NaN-unsafe (#454:
        # min(1.0, nan) = 1.0, then max(0.0, 1.0) = 1.0 — a hard toe-assist
        # impact with one occluded keypoint read as a perfectly clean edge).
        score = float(np.clip(1.0 + peak_decel / 5.0, 0.0, 1.0))
        return score

    def compute_approach_torso_lean(self, poses: NormalizedPose, phases: ElementPhase) -> float:
        """Compute average torso lean during the approach phase.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.

        Returns:
            Average trunk lean in degrees. Positive = forward lean.
            Returns 0.0 if no approach phase.
        """
        if phases.takeoff < phases.start or phases.takeoff >= len(poses):
            return 0.0

        approach_poses = poses[phases.start : phases.takeoff + 1]
        if len(approach_poses) == 0:
            return 0.0

        trunk_lean = self.compute_trunk_lean(approach_poses)
        return float(np.mean(trunk_lean))

    def compute_approach_direction_change(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> float:
        """Compute total direction change during the approach phase.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            fps: Frame rate.

        Returns:
            Total direction change in degrees.
            Returns 0.0 if no approach phase.
        """
        if phases.takeoff < phases.start or phases.takeoff >= len(poses):
            return 0.0

        approach_poses = poses[phases.start : phases.takeoff + 1]
        if len(approach_poses) < 2:
            return 0.0

        com = calculate_com_trajectory_2d(approach_poses)
        vx = np.gradient(com[:, 0]) * fps
        vy = np.gradient(com[:, 1]) * fps
        # #851: use the full 2D heading arctan2(vy, vx). The previous form
        # passed a constant 1.0 as the second arctan2 arg, collapsing the
        # heading to arctan(vx) and ignoring the vertical CoM velocity —
        # curved / vertical approaches read as 0°.
        angles = np.degrees(np.arctan2(vy, vx))
        # #878: NaN-safe direction change. A NaN keypoint in the approach phase
        # used to leak nan through the CoM -> gradient -> arctan2 -> diff into
        # the sum, so compute_approach_direction_change returned nan. The
        # NaN-aware CoM (#871/#878 contract) keeps the CoM finite when a few
        # keypoints are occluded, but a fully-occluded frame still yields NaN
        # angles. np.nansum skips NaN diffs; if every frame is NaN there is no
        # data — return 0.0 (neutral "no direction change") instead of nan,
        # which would inflate the GOE approach_score via min(1.0, nan)=1.0
        # (#454).
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            total = float(np.nansum(np.abs(np.diff(angles))))
        if not np.isfinite(total):
            return 0.0
        return total

    def compute_arm_position(self, poses: NormalizedPose) -> float:
        """Compute arm position score.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).

        Returns:
            Score [0, 1] where 1 = arms close to body (good for jumps).
        """
        # Calculate average wrist-to-shoulder distance
        # #902: NaN wrist/shoulder (occluded — common during rotation when arms
        # cross the body) made np.mean→NaN, then the `max(0, 1 - nan)` clamp
        # floored NaN to 0.0 — a SILENT BEST score that rewards occlusion and
        # inflates the GOE proxy. np.nanmean skips occluded frames; if no frame
        # is finite, return NaN (a flag the recommender/GOE must treat as
        # "unknown", not "excellent") instead of the false-good 0.0.
        left_dist = np.linalg.norm(poses[:, H36Key.LWRIST] - poses[:, H36Key.LSHOULDER], axis=1)
        right_dist = np.linalg.norm(poses[:, H36Key.RWRIST] - poses[:, H36Key.RSHOULDER], axis=1)

        avg_dist = float(np.nanmean(left_dist + right_dist) / 2)
        if not np.isfinite(avg_dist):
            return float("nan")

        return float(max(0, 1 - avg_dist))

    def compute_trunk_lean(self, poses: NormalizedPose) -> TimeSeries:
        """Compute trunk lean angle.

        Uses Numba-jitted implementation for performance.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).

        Returns:
            Trunk angle in degrees (positive = forward lean).
        """
        return _compute_trunk_lean_series_numba(poses)

    def compute_knee_angle_series(self, poses: NormalizedPose, side: str = "left") -> TimeSeries:
        """Compute knee angle series for step elements.

        Uses Numba-jitted implementation for performance.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            side: "left" or "right" knee.

        Returns:
            Knee angle in degrees (num_frames,).
        """
        if side == "left":
            hip_idx, knee_idx, foot_idx = int(H36Key.LHIP), int(H36Key.LKNEE), int(H36Key.LFOOT)
        else:
            hip_idx, knee_idx, foot_idx = int(H36Key.RHIP), int(H36Key.RKNEE), int(H36Key.RFOOT)

        # #868: NaN guard in the Python wrapper, not the @njit core. Under
        # fastmath the jitted angle_3pt_rad raises ZeroDivisionError (nan/nan)
        # on a NaN knee instead of returning NaN, crashing analyze() and
        # killing every session metric. A guard inside @njit(fastmath) does
        # not help (fastmath reorders / ignores the finite check). Mask NaN
        # frames to a finite placeholder, run the jitted core, then restore
        # NaN on the occluded frames so callers can skip them (np.nanstd).
        triplet = poses[:, [hip_idx, knee_idx, foot_idx], :]  # (N, 3, 2)
        finite_frames = np.all(np.isfinite(triplet), axis=(1, 2))
        if not finite_frames.all():
            safe_poses = poses.copy()
            triplet_safe = np.nan_to_num(triplet, nan=0.0)
            safe_poses[:, hip_idx, :] = triplet_safe[:, 0, :]
            safe_poses[:, knee_idx, :] = triplet_safe[:, 1, :]
            safe_poses[:, foot_idx, :] = triplet_safe[:, 2, :]
            angles = _compute_knee_angle_series_numba(safe_poses, hip_idx, knee_idx, foot_idx)
            angles = angles.astype(np.float32, copy=True)
            angles[~finite_frames] = np.nan
            return angles
        return _compute_knee_angle_series_numba(poses, hip_idx, knee_idx, foot_idx)

    def compute_edge_indicator(
        self,
        poses: NormalizedPose,
        side: str = "left",
    ) -> TimeSeries:
        """Compute edge indicator using H3.6M 17-keypoint format.

        Vectorized implementation — processes all frames at once.

        Uses body lean angle and foot velocity to infer blade edge.
        - Inside edge: body leaning into turn (positive)
        - Outside edge: body leaning away from turn (negative)
        - Flat edge: body upright (near zero)

        Note: This is a simplified inference since H3.6M lacks detailed foot keypoints.
        For accurate blade detection, use BladeEdgeDetector3D with full 3D poses.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            side: "left" or "right" foot.

        Returns:
            Edge indicator: +1 = inside edge, -1 = outside edge, 0 = flat.
        """
        if side == "left":
            hip = poses[:, H36Key.LHIP]
            shoulder = poses[:, H36Key.LSHOULDER]
        else:
            hip = poses[:, H36Key.RHIP]
            shoulder = poses[:, H36Key.RSHOULDER]

        # #977: NaN hip/shoulder (occluded joint) -> NaN spine_vector ->
        # arctan2(NaN)=NaN -> clip(NaN)=NaN -> np.std(NaN)=NaN leaks NaN into
        # edge_change_smoothness. nan_to_num is identity on finite joints.
        hip = np.nan_to_num(hip, nan=0.0)
        shoulder = np.nan_to_num(shoulder, nan=0.0)

        # Vector from hip to shoulder: (N, 2)
        spine_vector = shoulder - hip

        # Angle from vertical: atan2(x, -y)
        angle = np.arctan2(spine_vector[:, 0], -spine_vector[:, 1])

        # Normalize to [-1, 1]
        edge_indicator = np.clip(angle / (np.pi / 6), -1, 1).astype(np.float32)

        return edge_indicator

    def compute_total_rotation_from_poses(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> tuple[float, float]:
        """Compute total rotation from pose sequence during flight.

        Extracts unwrapped shoulder axis angles during the flight phase
        and delegates to compute_total_rotation().

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            fps: Frame rate.

        Returns:
            (total_degrees, rotation_count).
        """
        if phases.takeoff >= phases.landing or phases.landing >= len(poses):
            return 0.0, 0.0

        flight_poses = poses[phases.takeoff : phases.landing]
        left_shoulder = flight_poses[:, H36Key.LSHOULDER]
        right_shoulder = flight_poses[:, H36Key.RSHOULDER]
        shoulder_vector = right_shoulder - left_shoulder
        angles = np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])
        unwrapped = np.unwrap(angles)
        # #909: NaN shoulder on a flight frame (occluded during fast rotation —
        # arms cross the body) -> shoulder_vector NaN -> arctan2(nan, x) = NaN
        # -> np.unwrap(NaN) = NaN -> abs(unwrapped[-1] - unwrapped[0]) = NaN
        # leaked into total_rotation_deg / rotation_count / under_rotation_deg
        # and the GOE proxy. rotation_count is the PRIMARY jump identifier
        # (1=single, 2=double, 3=triple) — a NaN hole there makes the
        # recommender unable to name the jump. Return the 0.0 sentinel (neutral
        # "no rotation") matching the degenerate-phases guard above, instead of
        # NaN. Identity on all-finite input. ponytail: all-NaN flight yields 0.0
        # (biased finite, not NaN); upgrade to inf sentinel if a
        # degenerate-flight signal is needed.
        if not np.all(np.isfinite(unwrapped)):
            return 0.0, 0.0

        return compute_total_rotation(unwrapped, fps)

    @staticmethod
    def compute_rotation_yaw_delta(
        poses_3d: np.ndarray,
        flight_indices: np.ndarray,
        fps: float = 30.0,
    ) -> tuple[float, float, np.ndarray]:
        """Alternative rotation count via 3D shoulder-axis yaw with physiological clamping.

        Uses Z-axis depth from 3D poses to avoid 2D projection collapse.
        Clamps per-frame deltas exceeding 720 deg/s (physiologically impossible).

        Args:
            poses_3d: 3D poses (N, 17, 3).
            flight_indices: Indices of flight-phase frames.
            fps: Frame rate.

        Returns:
            (total_degrees, rotation_count, clamped_mask) where clamped_mask
            is True for frames with physiologically impossible deltas.
        """
        if len(flight_indices) < 2:
            return 0.0, 0.0, np.array([], dtype=bool)

        l_sho = poses_3d[flight_indices, H36Key.LSHOULDER]
        r_sho = poses_3d[flight_indices, H36Key.RSHOULDER]

        # Shoulder length guard: skip frames where shoulder axis is near-zero.
        # #915: NaN shoulder (occlusion) -> shoulder_length NaN. np.median of a
        # NaN-containing array is NaN (NOT np.nanmedian), `NaN < 1e-6` = False
        # (NaN comparison) skips the degenerate guard, `NaN > 0.05*NaN` =
        # all-False empties valid_idx -> false-BAD (0.0, 0.0) sentinel. The 3D
        # yaw cross-check then OVERWRITES a valid 2D rotation_count with 0.0 in
        # _analyze_jump (line 392-397): `abs(rotation_count - 0.0) > 0.5` ->
        # rotation_count = 0.0. A triple with one occluded shoulder reads as
        # "0 rotations". Use np.nanmedian so a few NaN shoulder frames don't
        # poison the median; only all-NaN shoulder yields NaN. isfinite guard
        # returns a NaN sentinel (NOT 0.0) -> consumer's
        # `abs(rotation_count - nan) > 0.5` is False -> 2D rotation_count
        # preserved. A finite near-zero median (empty/degenerate frame) still
        # returns 0.0 (existing behavior). Mirrors #966 classify_jump
        # isfinite guard.
        shoulder_length = np.linalg.norm(r_sho - l_sho, axis=1)
        median_length = np.nanmedian(shoulder_length)
        if not np.isfinite(median_length):
            return float("nan"), float("nan"), np.zeros(len(flight_indices) - 1, dtype=bool)
        if median_length < 1e-6:
            return 0.0, 0.0, np.zeros(len(flight_indices) - 1, dtype=bool)
        valid = shoulder_length > 0.05 * median_length

        # Yaw from 3D: Z-depth avoids 2D collapse
        yaw = np.arctan2(r_sho[:, 2] - l_sho[:, 2], r_sho[:, 0] - l_sho[:, 0])

        # Interpolate invalid (incl. NaN-shoulder) frames from neighbors
        if not np.all(valid):
            valid_idx = np.where(valid)[0]
            if len(valid_idx) < 2:
                return float("nan"), float("nan"), np.zeros(len(flight_indices) - 1, dtype=bool)
            yaw[~valid] = np.interp(np.where(~valid)[0], valid_idx, yaw[valid])

        # Manual delta with wrap-around
        delta = np.diff(yaw)
        delta = np.where(delta > np.pi, delta - 2 * np.pi, delta)
        delta = np.where(delta < -np.pi, delta + 2 * np.pi, delta)

        # Physiological clamp: above ~2400 deg/s (quadruple jump ceiling) a delta
        # is a tracking artifact, not real rotation. Cap to the ceiling preserving
        # sign — zeroing (old behavior) destroyed the rotation count of real
        # triple/quadruple jumps (~2160-2400 deg/s). 720 deg/s was far too low. #426
        # #958: corrupt video reports fps=0 (cv2.CAP_PROP_FPS sentinel). Guard
        # the ceiling division — inf ceiling → np.clip no-op for finite deltas
        # → rotation count from raw deltas, NOT a ZeroDivisionError crash. The
        # clamp is meant to cap degenerate dt (tracking artifact); at fps<=0
        # "no clamp" is the correct degradation. Mirrors #499 fps=0 family.
        max_delta = np.radians(2400.0 / fps) if fps > 0 else np.inf
        clamped = np.abs(delta) > max_delta
        delta = np.clip(delta, -max_delta, max_delta)

        total_deg = float(np.sum(delta) * 180 / np.pi)
        rotation_count = round(abs(total_deg) / 360, 1)

        return total_deg, rotation_count, clamped

    @staticmethod
    def compute_spread_eagle_angle(poses: np.ndarray) -> np.ndarray:
        """Bilateral angle between left and right leg vectors (hip→knee).

        Args:
            poses: Poses array (N, 17, 2) or (N, 17, 3).

        Returns:
            Per-frame angle series in degrees [0, 180].
            Near 0° = legs parallel (normal skating), near 180° = spread eagle.
        """
        # #976: NaN joint (occluded hip/knee) -> NaN leg -> NaN cos ->
        # np.arccos(NaN)=NaN silently leaks into the angle series. +1e-8 does
        # NOT mask NaN, np.clip(NaN) is no-op. Guard the leg-vector joint
        # inputs at the trust boundary (NaN -> 0.0 sentinel), mirroring #978
        # (compute_goe_score nan_to_num) and #868 (compute_knee_angle_series
        # finite-frame mask). nan_to_num is identity on finite joints.
        l_leg = np.nan_to_num(poses[:, H36Key.LKNEE] - poses[:, H36Key.LHIP], nan=0.0)  # 5 - 4
        r_leg = np.nan_to_num(poses[:, H36Key.RKNEE] - poses[:, H36Key.RHIP], nan=0.0)  # 2 - 1

        dot_prod = np.sum(l_leg * r_leg, axis=-1)
        norms = np.linalg.norm(l_leg, axis=-1) * np.linalg.norm(r_leg, axis=-1) + 1e-8
        cos_angle = np.clip(dot_prod / norms, -1.0, 1.0)

        return np.degrees(np.arccos(cos_angle))

    @staticmethod
    def compute_spiral_indicator(poses: np.ndarray) -> np.ndarray:
        """Detect one-foot support via Y-coordinate gap between feet.

        Args:
            poses: Poses array (N, 17, 2) or (N, 17, 3). Y-down coords.

        Returns:
            Per-frame |LFOOT_y - RFOOT_y| difference. Large = spiral candidate.
        """
        # #976: NaN foot joint (occluded LFOOT/RFOOT) -> np.abs(NaN - finite) =
        # NaN silently leaks into the indicator series. Guard the foot joint
        # inputs at the trust boundary (NaN -> 0.0 sentinel), mirroring #978.
        # nan_to_num is identity on finite joints.
        l_foot_y = np.nan_to_num(poses[:, H36Key.LFOOT, 1], nan=0.0)
        r_foot_y = np.nan_to_num(poses[:, H36Key.RFOOT, 1], nan=0.0)
        return np.abs(l_foot_y - r_foot_y)

    def compute_ina_bauer_score(
        self, poses: np.ndarray, se_angle: np.ndarray | None = None
    ) -> np.ndarray:
        """Composite score for Ina Bauer detection.

        Only meaningful on frames where spread_eagle_angle >= 150 degrees.
        Components normalized to [0, 1] before weighting.

        Args:
            poses: Poses array (N, 17, 2) or (N, 17, 3).
            se_angle: Pre-computed spread eagle angle series (optional).

        Returns:
            Per-frame score in [0, 1]. >= 0.7 means Ina Bauer detected.
        """
        if se_angle is None:
            se_angle = self.compute_spread_eagle_angle(poses)

        # #976: NaN joint (occluded thorax/hip/knee/foot, or a caller-supplied
        # NaN se_angle) -> NaN leg_angle_norm / NaN trunk_norm -> arccos(NaN) =
        # NaN torso_lean / NaN knee_diff -> NaN composite (any NaN -> NaN sum).
        # Guard each component at the trust boundary (NaN -> 0.0 sentinel),
        # mirroring #978 (compute_goe_score nan_to_num). nan_to_num is identity
        # on finite inputs, so the all-finite case is unchanged.
        # Leg angle: 150 deg -> 0, 180 deg -> 1
        se_angle = np.nan_to_num(se_angle, nan=0.0)
        leg_angle_norm = np.clip((se_angle - 150.0) / 30.0, 0, 1)

        # Torso lean: angle between hip_center->thorax and vertical (0, -1)
        trunk = np.nan_to_num(
            poses[:, H36Key.THORAX] - poses[:, H36Key.HIP_CENTER], nan=0.0
        )  # 8 - 0
        trunk_norm = trunk / (np.linalg.norm(trunk, axis=-1, keepdims=True) + 1e-8)
        torso_lean = np.degrees(np.arccos(np.clip(-trunk_norm[:, 1], -1, 1)))
        torso_lean_norm = np.clip(torso_lean / 45.0, 0, 1)

        # Knee asymmetry: |L_knee_angle - R_knee_angle|
        l_knee = np.array(
            [
                self._angle_3pt_from_poses(poses, f, H36Key.LHIP, H36Key.LKNEE, H36Key.LFOOT)
                for f in range(len(poses))
            ]
        )
        r_knee = np.array(
            [
                self._angle_3pt_from_poses(poses, f, H36Key.RHIP, H36Key.RKNEE, H36Key.RFOOT)
                for f in range(len(poses))
            ]
        )
        knee_diff_norm = np.clip(
            np.abs(np.nan_to_num(l_knee, nan=0.0) - np.nan_to_num(r_knee, nan=0.0)) / 40.0,
            0,
            1,
        )

        return 0.5 * leg_angle_norm + 0.3 * torso_lean_norm + 0.2 * knee_diff_norm

    @staticmethod
    def _angle_3pt_from_poses(poses: np.ndarray, frame: int, j1: int, j2: int, j3: int) -> float:
        """Compute 3-point angle (j1-j2-j3) in degrees for a single frame."""
        a = poses[frame, j1]
        b = poses[frame, j2]
        c = poses[frame, j3]
        ba = a - b
        bc = c - b
        cos_val = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
        return float(np.degrees(np.arccos(np.clip(cos_val, -1.0, 1.0))))

    def compute_rotation_speed(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> float:
        """Compute peak rotation speed during jump.

        Vectorized implementation — processes all frames at once.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            fps: Frame rate.

        Returns:
            Peak rotation speed in deg/s.
        """
        # Vectorized shoulder axis angle: (N,)
        left_shoulder = poses[:, H36Key.LSHOULDER]
        right_shoulder = poses[:, H36Key.RSHOULDER]

        shoulder_vector = right_shoulder - left_shoulder
        angles = np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])
        angles_deg = np.degrees(angles)

        # Angular velocity
        velocity = self.compute_angular_velocity(angles_deg, fps)

        # Peak in flight phase
        if phases.takeoff < phases.landing and phases.landing < len(velocity):
            flight_velocity = velocity[phases.takeoff : phases.landing]
            # #903: np.nanmax (NOT np.max) so a NaN shoulder on a flight frame
            # (occluded during fast rotation — arms cross the body) does not
            # poison the peak into NaN. arctan2(nan, x) = NaN -> gradient NaN
            # -> np.max(np.abs(NaN)) = NaN leaked into rotation_speed / GOE.
            # nanmax skips NaN frames; if every flight frame is NaN there is
            # no data — 0.0 (neutral "no rotation") instead of NaN, which
            # breaks JSON serialization and the GOE composite. Identity on
            # all-finite input.
            peak = float(np.nanmax(np.abs(flight_velocity)))
            if not np.isfinite(peak):
                return 0.0
            return peak

        return 0.0

    def compute_symmetry(self, poses: NormalizedPose, phases: ElementPhase) -> float:
        """Compute body symmetry score.

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.

        Returns:
            Symmetry score [0, 1] where 1 = perfect symmetry.
        """
        # Get poses during element
        start = phases.start
        end = min(phases.end, len(poses))
        element_poses = poses[start:end]

        # Calculate left-right asymmetry for key joints
        joint_pairs = [
            (H36Key.LSHOULDER, H36Key.RSHOULDER),
            (H36Key.LELBOW, H36Key.RELBOW),
            (H36Key.LHIP, H36Key.RHIP),
            (H36Key.LKNEE, H36Key.RKNEE),
        ]

        # #852: mirror across the per-frame BODY MIDLINE, not the world x=0
        # axis. The midline is the sagittal axis — the mean x of the central
        # structural joints (hip, spine, thorax, neck) — which is independent
        # of the L/R pair being compared. A rigid sideways shift / tilt moves
        # the whole body, so the midline tracks it and a symmetric pose still
        # scores 1.0; real anatomical asymmetry (L ≠ mirrored-R about the
        # midline) survives. The old form (mirrored = -x about x=0) only
        # matched the midline when the skater sat exactly on x=0, so a
        # symmetric-but-tilted body read as asymmetric.
        central_joints = np.stack(
            [
                element_poses[:, H36Key.HIP_CENTER],
                element_poses[:, H36Key.SPINE],
                element_poses[:, H36Key.THORAX],
                element_poses[:, H36Key.NECK],
            ],
            axis=1,
        )
        midline_x = central_joints[:, :, 0].mean(axis=1)  # (N,)

        asymmetries: list[float] = []

        for left_idx, right_idx in joint_pairs:
            left_joints = element_poses[:, left_idx]
            right_joints = element_poses[:, right_idx]

            # Mirror left across the per-frame midline: x -> 2*midline_x - x.
            mirrored_left = left_joints.copy()
            mirrored_left[:, 0] = 2 * midline_x - left_joints[:, 0]

            # Calculate average distance.
            # #869: NaN-safe per pair — np.mean propagates NaN, so one occluded
            # joint poisons the pair and then the aggregate; np.nanmean skips
            # NaN frames. all-NaN pair → NaN, filtered from the aggregate below.
            # Suppress the "Mean of empty slice" warning for the all-NaN case.
            distances = np.linalg.norm(mirrored_left - right_joints, axis=1)
            # #869: nanmean of an all-NaN slice emits a "Mean of empty slice"
            # RuntimeWarning (not an errstate category) — silence it; the NaN
            # is filtered from the aggregate below.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                asymmetries.append(float(np.nanmean(distances)))

        # Symmetry = 1 - average asymmetry.
        # #869: NaN-safe aggregate + clamp. np.nanmean skips NaN pairs; if every
        # pair is NaN there is no data — return neutral 1.0 (perfect symmetry
        # default, matches "no data" rather than falsely scoring worst). The
        # old Python `max(0, 1 - nan)` was arg-order NaN-unsafe (#454): max(0,
        # nan)=0 graded a symmetric body with one occluded joint as worst.
        valid = [a for a in asymmetries if np.isfinite(a)]
        if not valid:
            return 1.0
        avg_asymmetry = float(np.mean(valid))
        return float(np.clip(1.0 - avg_asymmetry, 0.0, 1.0))

    def compute_relative_jump_height(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        com_trajectory: NDArray[np.float32] | None = None,
    ) -> float:
        """Compute jump height normalized by spine length (camera-independent).

        This metric provides a camera-independent measure of jump height by
        normalizing the Center of Mass displacement by the athlete's spine length.
        This removes dependence on camera distance and zoom level.

        Typical values:
        - 0.0: No jump
        - ~0.5: Typical jump
        - ~1.0+: Elite jump (CoM displacement equal to spine length)

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phases: Element phase boundaries.
            com_trajectory: Pre-computed CoM trajectory (optional, for caching).

        Returns:
            Relative jump height as ratio (CoM displacement / spine length).
            Returns 0.0 if takeoff >= landing (no jump detected).
        """
        # Guard against invalid phases
        if phases.takeoff >= phases.landing:
            return 0.0

        # Calculate average spine length around takeoff (vectorized)
        # Spine = distance from mid-hip to mid-shoulder
        start_frame = max(0, phases.takeoff - 2)
        end_frame = min(len(poses), phases.takeoff + 3)

        takeoff_window = poses[start_frame:end_frame]
        mid_hip = (takeoff_window[:, H36Key.LHIP] + takeoff_window[:, H36Key.RHIP]) / 2
        mid_shoulder = (
            takeoff_window[:, H36Key.LSHOULDER] + takeoff_window[:, H36Key.RSHOULDER]
        ) / 2
        spine_lengths = np.linalg.norm(mid_shoulder - mid_hip, axis=1)
        valid_spines = spine_lengths[spine_lengths >= 0.01]

        if len(valid_spines) == 0:
            return 0.0

        avg_spine = float(np.mean(valid_spines))

        if com_trajectory is None:
            com_trajectory = calculate_com_trajectory(poses)

        # Get CoM at takeoff
        takeoff_com = com_trajectory[phases.takeoff]

        # Find minimum CoM during flight (maximum height).
        # Y is inverted in normalized coords, so min Y = max height.
        # #875: np.nanmin (NOT np.min) so a NaN CoM frame (fully-occluded flight
        # frame — calculate_com_trajectory is NaN-aware (#871) and masks a few
        # occluded keypoints, but a fully-occluded frame still yields NaN) does
        # not poison the min into nan. Mirrors the sibling compute_max_height
        # guard (#879, line 832). nanmin skips NaN frames; if every flight frame
        # is NaN there is no data -- return 0.0 (neutral "no height") instead of
        # nan, which leaks into the GOE height_score via min(1.0, nan)=1.0
        # (#454 arg-order trap) and inflates the GOE by ~+0.20 (height weight
        # 0.20) -- occlusion rewarded as the BEST jump. Identity on all-finite.
        flight_com = com_trajectory[phases.takeoff : phases.landing + 1]
        peak_com = float(np.nanmin(flight_com))
        if not np.isfinite(peak_com):
            return 0.0

        # CoM displacement = takeoff - peak (both inverted, so difference is positive)
        com_displacement = float(takeoff_com - peak_com)
        if not np.isfinite(com_displacement):
            return 0.0

        # Return normalized height
        return com_displacement / avg_spine

    def compute_goe_score(
        self,
        poses: NormalizedPose,
        phases: ElementPhase,
        fps: float,
    ) -> float:
        """Compute GOE proxy score (0-10) from body kinematics.

        Components (each normalized to [0,1]):
        - Jump height (20%): relative CoM displacement
        - Rotation speed (15%): peak angular velocity
        - Landing quality (25%): smoothness + knee stability average
        - Airtime (15%): flight duration
        - Torso control (15%): trunk recovery after landing
        - Approach consistency (10%): direction change / 90 deg

        Returns: GOE proxy score in [0.0, 10.0]
        """
        rel_height = self.compute_relative_jump_height(poses, phases)
        # #875: np.nan_to_num before the Python min — min(1.0, nan) = 1.0
        # (#454 arg-order trap) would inflate the GOE height_score to BEST on a
        # NaN rel_height. compute_relative_jump_height now returns finite 0.0 on
        # no-data (#875 guard), but guard anyway in case a caller passes a NaN
        # path. NaN -> neutral 0.0 (worst height), not best 1.0. Mirrors the
        # approach_score guard below (#878).
        height_score = float(np.nan_to_num(rel_height / 1.0, nan=0.0))
        height_score = min(1.0, height_score)

        rot_speed = self.compute_rotation_speed(poses, phases, fps)
        # #978: np.nan_to_num before the Python min — min(1.0, nan) = 1.0
        # (#454 arg-order trap) would inflate the GOE rot_score to PERFECT on a
        # NaN rotation_speed (occluded shoulder during fast rotation).
        # Mirrors the height_score (#875) and approach_score (#878) guards.
        # NaN -> neutral 0.0 (worst rotation), not best 1.0.
        rot_score = float(np.nan_to_num(rot_speed / 720.0, nan=0.0))
        rot_score = min(1.0, rot_score)

        landing_smooth = self.compute_landing_smoothness(poses, phases, fps)
        landing_stab = self.compute_landing_knee_stability(poses, phases)
        hard_landing = self.compute_hard_landing(poses, phases, fps)
        toe_assist = self.compute_toe_assist_proxy(poses, phases, fps)
        # #978: np.nan_to_num on each landing sub-metric before the average —
        # a NaN landing sub-metric (NaN + finite) / 4 = NaN leaks into the GOE
        # composite (NaN-leak, breaks JSON). NaN -> 0.0 (worst), mirroring the
        # cap-site guards on height_score / rot_score / approach_score.
        landing_score = (
            float(np.nan_to_num(landing_smooth, nan=0.0))
            + float(np.nan_to_num(landing_stab, nan=0.0))
            + float(np.nan_to_num(hard_landing, nan=0.0))
            + float(np.nan_to_num(toe_assist, nan=0.0))
        ) / 4.0

        airtime = self.compute_airtime(phases, fps)
        # #978: np.nan_to_num before the Python min — min(1.0, nan) = 1.0
        # (#454 arg-order trap) would inflate the GOE airtime_score to PERFECT
        # on a NaN airtime. Mirrors the height_score (#875) guard.
        airtime_score = float(np.nan_to_num(airtime / 1.0, nan=0.0))
        airtime_score = min(1.0, airtime_score)

        # #978: np.nan_to_num on trunk_recovery — a NaN trunk_recovery
        # (occluded shoulder on landing) propagates `nan * 0.15 = nan` into the
        # GOE composite (NaN-leak). NaN -> 0.0 (worst recovery), mirroring the
        # cap-site guards on the other sub-scores.
        trunk_recovery = float(
            np.nan_to_num(self.compute_landing_trunk_recovery(poses, phases), nan=0.0)
        )

        approach_change = self.compute_approach_direction_change(poses, phases, fps)
        # #878: guard NaN before the Python min — min(1.0, nan) = 1.0 (arg-order
        # NaN-unsafe, #454) and would inflate the GOE approach_score to BEST on
        # occlusion. compute_approach_direction_change now returns finite 0.0 on
        # no-data, but guard anyway in case a caller passes a NaN path.
        approach_score = float(np.nan_to_num(approach_change / 90.0, nan=0.0))
        approach_score = min(1.0, approach_score)

        goe = (
            height_score * 0.20
            + rot_score * 0.15
            + landing_score * 0.25
            + airtime_score * 0.15
            + trunk_recovery * 0.15
            + approach_score * 0.10
        )
        return float(goe * 10.0)


def compute_total_rotation(
    shoulder_angles_unwrapped: np.ndarray,
    fps: float,
) -> tuple[float, float]:
    """Compute total rotation from unwrapped shoulder angle series.

    Args:
        shoulder_angles_unwrapped: Unwrapped shoulder axis angles in radians (N,).
        fps: Frame rate.

    Returns:
        (total_degrees, rotation_count).
    """
    if len(shoulder_angles_unwrapped) < 2:
        return 0.0, 0.0
    total_radians = float(abs(shoulder_angles_unwrapped[-1] - shoulder_angles_unwrapped[0]))
    total_degrees = np.degrees(total_radians)
    rotation_count = total_degrees / 360.0
    return total_degrees, rotation_count


def compute_under_rotation(
    measured_degrees: float,
    target_rotations: float,
) -> float:
    """Compute under-rotation in degrees.

    Args:
        measured_degrees: Measured total rotation in degrees.
        target_rotations: Expected number of rotations (e.g., 3 for triple).

    Returns:
        Under-rotation in degrees. Positive = under-rotated, negative = over-rotated.
    """
    target_degrees = target_rotations * 360.0
    return target_degrees - measured_degrees


@dataclass
class PhaseDetectionResult:
    """Result of automatic phase detection."""

    phases: ElementPhase
    """Detected phase boundaries."""

    confidence: float
    """Detection confidence score [0, 1]."""

    rotations: int = 0
    """Full body rotations counted over the flight phase (jumps only)."""
