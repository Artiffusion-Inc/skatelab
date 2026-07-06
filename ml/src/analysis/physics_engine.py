"""Physics calculations for figure skating biomechanics analysis.

Implements:
- Center of Mass (CoM) calculation using anthropometric data
- Moment of Inertia (I) calculation
- Angular Momentum (L = I * w)
- Parabolic trajectory fitting for jump height

References:
- Dempster (1955) anthropometric tables
- Zatsiorsky (2002) biomechanics
- AthletePose3D: Monocular 3D pose for sports
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import curve_fit

# Anthropometric data (segment mass ratios)
# Based on Dempster (1955) - normalized to total body mass
SEGMENT_MASS_RATIOS = {
    "head": 0.081,
    "torso": 0.497,  # Includes thorax, abdomen, pelvis
    "left_upper_arm": 0.028,
    "left_forearm": 0.016,
    "left_hand": 0.006,
    "right_upper_arm": 0.028,
    "right_forearm": 0.016,
    "right_hand": 0.006,
    "left_thigh": 0.100,
    "left_shin": 0.0465,  # Lower leg
    "left_foot": 0.0145,
    "right_thigh": 0.100,
    "right_shin": 0.0465,
    "right_foot": 0.0145,
}

# Default body mass (kg) - can be overridden
DEFAULT_BODY_MASS = 60.0  # Typical figure skater


@dataclass
class PhysicsResult:
    """Result of physics calculations."""

    center_of_mass: np.ndarray  # (N, 3) CoM trajectory
    moment_of_inertia: np.ndarray  # (N,) I values
    angular_momentum: np.ndarray  # (N,) L values
    jump_height: float | None = None  # meters
    flight_time: float | None = None  # seconds
    rotation_rate: float | None = None  # deg/sec


class PhysicsEngine:
    """Physics calculations from 3D pose data.

    Uses anthropometric data to calculate:
    - Center of Mass (CoM) trajectory
    - Moment of Inertia (I)
    - Angular Momentum (L)
    - Jump height from parabolic fit
    """

    def __init__(self, body_mass: float = DEFAULT_BODY_MASS):
        """Initialize physics engine.

        Args:
            body_mass: Total body mass in kg
        """
        self.body_mass = body_mass
        self.segment_masses = {
            name: ratio * body_mass for name, ratio in SEGMENT_MASS_RATIOS.items()
        }

    def calculate_center_of_mass(
        self,
        poses_3d: np.ndarray,
    ) -> np.ndarray:
        """Calculate Center of Mass trajectory from 3D poses.

        CoM = (1/M) * sum(m_i * p_i)

        Where:
            M = total body mass
            mᵢ = segment mass
            pᵢ = segment center position

        Args:
            poses_3d: (N, 17, 3) array of H3.6M format poses
                - N = number of frames
                - 17 = H3.6M keypoints
                - 3 = (x, y, z) coordinates in meters

        Returns:
            com_trajectory: (N, 3) array of CoM positions
        """
        from ..pose_estimation import H36Key

        # Extract all keypoints as (N, 3) arrays
        head = poses_3d[:, H36Key.HEAD]
        spine = poses_3d[:, H36Key.SPINE]
        thorax = poses_3d[:, H36Key.THORAX]
        l_shoulder = poses_3d[:, H36Key.LSHOULDER]
        l_elbow = poses_3d[:, H36Key.LELBOW]
        l_wrist = poses_3d[:, H36Key.LWRIST]
        r_shoulder = poses_3d[:, H36Key.RSHOULDER]
        r_elbow = poses_3d[:, H36Key.RELBOW]
        r_wrist = poses_3d[:, H36Key.RWRIST]
        l_hip = poses_3d[:, H36Key.LHIP]
        l_knee = poses_3d[:, H36Key.LKNEE]
        l_foot = poses_3d[:, H36Key.LFOOT]
        r_hip = poses_3d[:, H36Key.RHIP]
        r_knee = poses_3d[:, H36Key.RKNEE]
        r_foot = poses_3d[:, H36Key.RFOOT]

        # Initialize CoM trajectory
        n_frames = poses_3d.shape[0]
        com_trajectory = np.zeros((n_frames, 3), dtype=np.float32)

        # #884: NaN-aware CoM — an occluded keypoint must NOT poison the CoM and
        # leak NaN into fit_jump_trajectory height. Mask each segment's
        # contribution to 0 when NaN (its mass is simply absent for that frame).
        # All-valid case is byte-identical: np.where(isfinite, term, 0) == term
        # when finite. Segment masses sum to body_mass, so dividing by
        # body_mass is unchanged on the all-valid path.
        def _w(name: str, seg: np.ndarray) -> np.ndarray:
            term = self.segment_masses[name] * seg
            return np.where(np.isfinite(seg), term, 0.0)

        # Head: direct keypoint
        com_trajectory += _w("head", head)

        # Torso: weighted average of spine and thorax
        torso_pos = (spine + thorax) / 2
        com_trajectory += _w("torso", torso_pos)

        # Upper arm: shoulder to elbow midpoint
        l_upper_arm = (l_shoulder + l_elbow) / 2
        r_upper_arm = (r_shoulder + r_elbow) / 2
        com_trajectory += _w("left_upper_arm", l_upper_arm)
        com_trajectory += _w("right_upper_arm", r_upper_arm)

        # Forearm: elbow to wrist midpoint
        l_forearm = (l_elbow + l_wrist) / 2
        r_forearm = (r_elbow + r_wrist) / 2
        com_trajectory += _w("left_forearm", l_forearm)
        com_trajectory += _w("right_forearm", r_forearm)

        # Hands: wrist position
        com_trajectory += _w("left_hand", l_wrist)
        com_trajectory += _w("right_hand", r_wrist)

        # Thigh: hip to knee midpoint
        l_thigh = (l_hip + l_knee) / 2
        r_thigh = (r_hip + r_knee) / 2
        com_trajectory += _w("left_thigh", l_thigh)
        com_trajectory += _w("right_thigh", r_thigh)

        # Shin: knee to ankle midpoint
        l_shin = (l_knee + l_foot) / 2
        r_shin = (r_knee + r_foot) / 2
        com_trajectory += _w("left_shin", l_shin)
        com_trajectory += _w("right_shin", r_shin)

        # Feet: ankle position
        com_trajectory += _w("left_foot", l_foot)
        com_trajectory += _w("right_foot", r_foot)

        # Normalize by total mass
        com_trajectory /= self.body_mass

        return com_trajectory

    def calculate_moment_of_inertia(
        self,
        poses_3d: np.ndarray,
        axis: str = "vertical",
    ) -> np.ndarray:
        """Calculate Moment of Inertia about a rotation axis.

        I = sum(m_i * r_i^2)

        Where:
            mᵢ = segment mass
            rᵢ = perpendicular distance from rotation axis

        Args:
            poses_3d: (N, 17, 3) array of poses
            axis: Rotation axis ("vertical", "sagittal", "frontal")

        Returns:
            inertia: (N,) array of moment of inertia values (kg·m²)
        """
        com_trajectory = self.calculate_center_of_mass(poses_3d)
        return self._calculate_moment_of_inertia_with_com(poses_3d, com_trajectory, axis)

    def calculate_angular_momentum(
        self,
        poses_3d: np.ndarray,
        angular_velocity: np.ndarray,
    ) -> np.ndarray:
        """Calculate Angular Momentum.

        L = I * w

        Args:
            poses_3d: (N, 17, 3) array of poses
            angular_velocity: (N,) array of angular velocities (rad/s)

        Returns:
            angular_momentum: (N,) array of L values (kg·m²/s)
        """
        inertia = self.calculate_moment_of_inertia(poses_3d)
        return inertia * angular_velocity

    def _calculate_moment_of_inertia_with_com(
        self,
        poses_3d: np.ndarray,
        com_trajectory: np.ndarray,
        axis: str = "vertical",
    ) -> np.ndarray:
        """Calculate MoI using pre-computed CoM (avoids recomputation).

        Same logic as calculate_moment_of_inertia but uses passed com_trajectory
        instead of calling self.calculate_center_of_mass(poses_3d).

        Args:
            poses_3d: (N, 17, 3) array of poses
            com_trajectory: (N, 3) pre-computed CoM trajectory
            axis: Rotation axis ("vertical", "sagittal", "frontal")

        Returns:
            inertia: (N,) array of moment of inertia values (kg·m²)
        """
        from ..pose_estimation import H36Key

        # Extract all keypoints as (N, 3) arrays
        head = poses_3d[:, H36Key.HEAD]
        spine = poses_3d[:, H36Key.SPINE]
        thorax = poses_3d[:, H36Key.THORAX]
        l_shoulder = poses_3d[:, H36Key.LSHOULDER]
        l_elbow = poses_3d[:, H36Key.LELBOW]
        l_wrist = poses_3d[:, H36Key.LWRIST]
        r_shoulder = poses_3d[:, H36Key.RSHOULDER]
        r_elbow = poses_3d[:, H36Key.RELBOW]
        r_wrist = poses_3d[:, H36Key.RWRIST]
        l_hip = poses_3d[:, H36Key.LHIP]
        l_knee = poses_3d[:, H36Key.LKNEE]
        l_foot = poses_3d[:, H36Key.LFOOT]
        r_hip = poses_3d[:, H36Key.RHIP]
        r_knee = poses_3d[:, H36Key.RKNEE]
        r_foot = poses_3d[:, H36Key.RFOOT]

        # Initialize inertia array
        n_frames = poses_3d.shape[0]
        inertia = np.zeros(n_frames, dtype=np.float32)

        # #854: rᵢ is the PERPENDICULAR distance from the rotation axis, not
        # the full 3D distance from CoM. Project the offset onto the plane
        # perpendicular to the axis (drop the component along the axis):
        #   vertical  → drop Y (rotation about the vertical axis)
        #   sagittal  → drop X
        #   frontal   → drop Z
        # The old full-norm computed inertia about a POINT, not an axis: mass
        # lying on the axis (head/feet above CoM) contributed m·dy² that should
        # be 0 → angular momentum inflated, all three axes collapsed.
        if axis == "vertical":
            drop = 1  # Y
        elif axis == "sagittal":
            drop = 0  # X
        elif axis == "frontal":
            drop = 2  # Z
        else:
            raise ValueError(f"Unknown axis: {axis!r} (vertical|sagittal|frontal)")

        # Helper function to compute squared distances
        def add_segment_inertia(segments: list[tuple[np.ndarray, float]]) -> None:
            """Add inertia contribution from segments.

            Args:
                segments: List of (position, mass) tuples
            """
            for pos, mass in segments:
                offset = pos - com_trajectory
                offset = np.delete(offset, drop, axis=-1)
                r = np.linalg.norm(offset, axis=1)
                inertia[:] += mass * r**2

        # Head
        add_segment_inertia([(head, self.segment_masses["head"])])

        # Torso: weighted average of spine and thorax
        torso_pos = (spine + thorax) / 2
        add_segment_inertia([(torso_pos, self.segment_masses["torso"])])

        # Arm segments
        l_upper_arm = (l_shoulder + l_elbow) / 2
        r_upper_arm = (r_shoulder + r_elbow) / 2
        l_forearm = (l_elbow + l_wrist) / 2
        r_forearm = (r_elbow + r_wrist) / 2

        add_segment_inertia(
            [
                (l_upper_arm, self.segment_masses["left_upper_arm"]),
                (r_upper_arm, self.segment_masses["right_upper_arm"]),
                (l_forearm, self.segment_masses["left_forearm"]),
                (r_forearm, self.segment_masses["right_forearm"]),
                (l_wrist, self.segment_masses["left_hand"]),
                (r_wrist, self.segment_masses["right_hand"]),
            ]
        )

        # Leg segments
        l_thigh = (l_hip + l_knee) / 2
        r_thigh = (r_hip + r_knee) / 2
        l_shin = (l_knee + l_foot) / 2
        r_shin = (r_knee + r_foot) / 2

        add_segment_inertia(
            [
                (l_thigh, self.segment_masses["left_thigh"]),
                (r_thigh, self.segment_masses["right_thigh"]),
                (l_shin, self.segment_masses["left_shin"]),
                (r_shin, self.segment_masses["right_shin"]),
                (l_foot, self.segment_masses["left_foot"]),
                (r_foot, self.segment_masses["right_foot"]),
            ]
        )

        return inertia

    def _fit_jump_trajectory_with_com(
        self,
        poses_3d: np.ndarray,
        takeoff_idx: int,
        landing_idx: int,
        com_trajectory: np.ndarray,
        fps: float = 30.0,
    ) -> dict:
        """Fit parabolic trajectory using pre-computed CoM.

        Args:
            poses_3d: (N, 17, 3) array of poses (unused, kept for interface consistency)
            takeoff_idx: Frame index of takeoff
            landing_idx: Frame index of landing
            com_trajectory: (N, 3) pre-computed CoM trajectory
            fps: Video framerate (was hardcoded 30; #423)

        Returns:
            dict with:
                - height: Max jump height (meters)
                - flight_time: Time in air (seconds)
                - takeoff_velocity: Vertical velocity at takeoff (m/s)
                - fit_quality: R² of parabolic fit
        """
        # Guard reversed/degenerate phases (phase-detector failure): an empty
        # slice crashes curve_fit/np.max. Sibling analyze_2d is tolerant. #428
        if takeoff_idx > landing_idx:
            return {
                "height": 0.0,
                "flight_time": 0.0,
                "takeoff_velocity": 0.0,
                "fit_quality": 0.0,
            }
        # #937: corrupt video reports fps=0 (cv2.CAP_PROP_FPS sentinel). Guard
        # before any /fps — mirrors the degenerate-phase guard above. Sibling
        # pose_tracker (#952) / smoothing (#948) fall back to dt=1.0; physics
        # has no meaningful per-frame time without fps, so return zeros.
        if fps <= 0:
            return {
                "height": 0.0,
                "flight_time": 0.0,
                "takeoff_velocity": 0.0,
                "fit_quality": 0.0,
            }
        # Extract flight phase (vertical component = Y axis)
        flight_com = com_trajectory[takeoff_idx : landing_idx + 1, 1]  # Y coordinate
        n_frames = len(flight_com)
        t = np.arange(n_frames) / fps  # #423: was hardcoded / 30.0

        # Parabolic fit: h(t) = at² + bt + c
        def parabola(t: Any, a: float, b: float, c: float) -> Any:
            return a * t**2 + b * t + c

        try:
            params, _ = curve_fit(parabola, t, flight_com)
            a, b, c = params

            # Calculate derived values
            # g = -2a (acceleration due to gravity)
            # v₀ = b (initial velocity)
            # h₀ = c (initial height)

            # Peak height occurs at t* = -b/(2a)
            t_peak = -b / (2 * a)
            h_peak = parabola(t_peak, a, b, c)
            h_takeoff = parabola(0, a, b, c)
            jump_height = h_peak - h_takeoff

            # Flight time
            flight_time = t[-1] - t[0]

            # R² for fit quality
            residuals = flight_com - parabola(t, a, b, c)
            ss_res = np.sum(residuals**2)
            ss_tot = np.sum((flight_com - np.mean(flight_com)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            return {
                "height": abs(jump_height),  # meters
                "flight_time": flight_time,  # seconds
                "takeoff_velocity": b,  # m/s
                "fit_quality": r_squared,
            }

        except Exception:
            # Fallback: simple height difference. #884: NaN-safe — a fully
            # occluded flight frame must not leak NaN into height.
            finite_com = flight_com[np.isfinite(flight_com)]
            fallback_height = (
                float(np.max(finite_com) - np.min(finite_com)) if finite_com.size > 0 else 0.0
            )
            if not np.isfinite(fallback_height):
                fallback_height = 0.0
            return {
                "height": fallback_height,
                "flight_time": n_frames / fps,  # #423: was / 30.0
                "takeoff_velocity": 0.0,
                "fit_quality": 0.0,
            }

    def fit_jump_trajectory(
        self,
        poses_3d: np.ndarray,
        takeoff_idx: int,
        landing_idx: int,
        fps: float = 30.0,
    ) -> dict:
        """Fit parabolic trajectory to CoM during flight.

        During flight, CoM follows: h(t) = h₀ + v₀t - ½gt²

        Args:
            poses_3d: (N, 17, 3) array of poses
            takeoff_idx: Frame index of takeoff
            landing_idx: Frame index of landing
            fps: Video framerate (was hardcoded 30; #423)

        Returns:
            dict with:
                - height: Max jump height (meters)
                - flight_time: Time in air (seconds)
                - takeoff_velocity: Vertical velocity at takeoff (m/s)
                - fit_quality: R² of parabolic fit
        """
        # Get CoM trajectory
        com_trajectory = self.calculate_center_of_mass(poses_3d)

        # Guard reversed/degenerate phases. #428
        if takeoff_idx > landing_idx:
            return {
                "height": 0.0,
                "flight_time": 0.0,
                "takeoff_velocity": 0.0,
                "fit_quality": 0.0,
            }
        # #937: corrupt video reports fps=0 — guard before any /fps (mirrors
        # the degenerate-phase guard above and _fit_jump_trajectory_with_com).
        if fps <= 0:
            return {
                "height": 0.0,
                "flight_time": 0.0,
                "takeoff_velocity": 0.0,
                "fit_quality": 0.0,
            }
        # Extract flight phase (vertical component = Y axis)
        flight_com = com_trajectory[takeoff_idx : landing_idx + 1, 1]  # Y coordinate
        n_frames = len(flight_com)
        t = np.arange(n_frames) / fps  # #423: was hardcoded / 30.0

        # Parabolic fit: h(t) = at² + bt + c
        def parabola(t: Any, a: float, b: float, c: float) -> Any:
            return a * t**2 + b * t + c

        try:
            params, _ = curve_fit(parabola, t, flight_com)
            a, b, c = params

            # Calculate derived values
            # g = -2a (acceleration due to gravity)
            # v₀ = b (initial velocity)
            # h₀ = c (initial height)

            # Peak height occurs at t* = -b/(2a)
            t_peak = -b / (2 * a)
            h_peak = parabola(t_peak, a, b, c)
            h_takeoff = parabola(0, a, b, c)
            jump_height = h_peak - h_takeoff

            # Flight time
            flight_time = t[-1] - t[0]

            # R² for fit quality
            residuals = flight_com - parabola(t, a, b, c)
            ss_res = np.sum(residuals**2)
            ss_tot = np.sum((flight_com - np.mean(flight_com)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            return {
                "height": abs(jump_height),  # meters
                "flight_time": flight_time,  # seconds
                "takeoff_velocity": b,  # m/s
                "fit_quality": r_squared,
            }

        except Exception:
            # Fallback: simple height difference. #884: NaN-safe — a fully
            # occluded flight frame must not leak NaN into height.
            finite_com = flight_com[np.isfinite(flight_com)]
            fallback_height = (
                float(np.max(finite_com) - np.min(finite_com)) if finite_com.size > 0 else 0.0
            )
            if not np.isfinite(fallback_height):
                fallback_height = 0.0
            return {
                "height": fallback_height,
                "flight_time": n_frames / fps,  # #423: was / 30.0
                "takeoff_velocity": 0.0,
                "fit_quality": 0.0,
            }

    def analyze(
        self,
        poses_3d: np.ndarray,
        takeoff_idx: int | None = None,
        landing_idx: int | None = None,
        fps: float = 30.0,
    ) -> PhysicsResult:
        """Run full physics analysis on 3D pose sequence.

        Computes CoM once and reuses it for all calculations.

        Args:
            poses_3d: (N, 17, 3) array of poses
            takeoff_idx: Optional takeoff frame index
            landing_idx: Optional landing frame index
            fps: Video framerate (was hardcoded 30 in the trajectory fit; #423)

        Returns:
            PhysicsResult with all calculated values
        """
        # Calculate CoM once — share with moment of inertia and trajectory
        com = self.calculate_center_of_mass(poses_3d)

        # Calculate moment of inertia using pre-computed CoM
        inertia = self._calculate_moment_of_inertia_with_com(poses_3d, com)

        # Angular momentum (assume zero angular velocity for now)
        angular_momentum = np.zeros_like(inertia)

        # Jump height (if takeoff/landing provided)
        jump_height = None
        flight_time = None

        if takeoff_idx is not None and landing_idx is not None:
            trajectory = self._fit_jump_trajectory_with_com(
                poses_3d, takeoff_idx, landing_idx, com, fps=fps
            )
            jump_height = trajectory["height"]
            flight_time = trajectory["flight_time"]

        return PhysicsResult(
            center_of_mass=com,
            moment_of_inertia=inertia,
            angular_momentum=angular_momentum,
            jump_height=jump_height,
            flight_time=flight_time,
            rotation_rate=None,
        )

    def analyze_2d(
        self,
        poses_2d: np.ndarray,
        takeoff_idx: int | None = None,
        landing_idx: int | None = None,
        fps: float = 30.0,
    ) -> dict[str, Any]:
        """Run 2D physics analysis using CoM trajectory.

        For when 3D poses are unavailable. Computes jump height and
        flight time from 2D CoM parabolic fit.

        Args:
            poses_2d: (N, 17, 2) normalized pose sequence.
            takeoff_idx: Takeoff frame index (None if unknown).
            landing_idx: Landing frame index (None if unknown).
            fps: Video framerate.

        Returns:
            Dict with jump_height, flight_time, takeoff_velocity,
            fit_quality, avg_inertia (None for 2D).
        """
        from ..utils.geometry import calculate_com_trajectory_2d

        com = calculate_com_trajectory_2d(poses_2d)  # (N, 2)

        jump_height: float | None = None
        flight_time: float | None = None
        takeoff_velocity: float | None = None
        fit_quality: float | None = None

        if takeoff_idx is not None and landing_idx is not None:
            # #939: corrupt video reports fps=0 (cv2.CAP_PROP_FPS sentinel).
            # Guard before any /fps — skip jump-physics, fields stay None
            # (graceful "unknown"). Mirrors #937 (3D sibling) guard-before-/fps.
            if fps <= 0:
                return {
                    "jump_height": None,
                    "flight_time": None,
                    "takeoff_velocity": None,
                    "fit_quality": None,
                    "avg_inertia": None,  # requires 3D
                }
            # #519: landing_idx is an INCLUSIVE frame index (the slice below
            # uses landing_idx+1). flight_frames must be the COUNT
            # (landing - takeoff + 1), not the exclusive span, so flight_time
            # matches the com[takeoff:landing+1] slice duration and t_flight
            # aligns with flight_com_y (both length = flight_frames).
            flight_frames = landing_idx - takeoff_idx + 1
            flight_time = flight_frames / fps

            flight_com_y = com[takeoff_idx : landing_idx + 1, 1]

            # #855: jump height is the CoM elevation ABOVE takeoff, not the
            # full peak-to-trough range over the window. In Y-down image coords
            # the peak is the MINIMUM y. The old form (max - min) took the
            # landing frame as the max when a knee-bend dropped the CoM below
            # takeoff, so a deeper landing reported a TALLER jump for the same
            # physical jump — landing absorption was conflated with jump height.
            # takeoff_y - peak_y is invariant to landing depth.
            # #883: NaN-safe peak — np.min propagates NaN if a flight frame is
            # fully occluded. Use a finite mask so jump_height never leaks NaN.
            finite_com_y = flight_com_y[np.isfinite(flight_com_y)]
            if finite_com_y.size == 0 or not np.isfinite(com[takeoff_idx, 1]):
                jump_height = 0.0
            else:
                jump_height = float(com[takeoff_idx, 1] - np.min(finite_com_y))

            if takeoff_idx > 0:
                dt = 1.0 / fps
                takeoff_velocity_y = float((com[takeoff_idx, 1] - com[takeoff_idx - 1, 1]) / dt)
                # #883: guard NaN leak on the backward diff.
                takeoff_velocity = (
                    abs(takeoff_velocity_y) if np.isfinite(takeoff_velocity_y) else 0.0
                )

            try:
                t_flight = np.arange(flight_frames) / fps
                coeffs = np.polyfit(t_flight, flight_com_y, 2)
                y_pred = np.polyval(coeffs, t_flight)
                ss_res = np.sum((flight_com_y - y_pred) ** 2)
                ss_tot = np.sum((flight_com_y - np.mean(flight_com_y)) ** 2)
                fit_quality = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
            except (np.linalg.LinAlgError, ValueError):
                fit_quality = 0.0

        return {
            "jump_height": jump_height,
            "flight_time": flight_time,
            "takeoff_velocity": takeoff_velocity,
            "fit_quality": fit_quality,
            "avg_inertia": None,  # requires 3D
        }
