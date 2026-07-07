"""Temporal smoothing using One-Euro Filter for pose sequences.

The One-Euro Filter (Casiez et al., 2012) is an adaptive low-pass filter
that combines noise reduction at low speeds with minimal lag at high speeds.
Ideal for smoothing human motion capture data from BlazePose.

Reference: https://github.com/jaantollander/OneEuroFilter
"""

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numba import njit  # type: ignore
from numpy.typing import NDArray

from ..types import NormalizedPose


# Numba-jitted core functions (for performance)
@njit(cache=True, fastmath=True)  # type: ignore[reportUntypedFunctionDecorator]
def _smoothing_factor_numba(te: float, cutoff: float) -> float:
    """Compute smoothing factor alpha from time interval and cutoff frequency (jitted).

    Args:
        te: Time interval since last sample.
        cutoff: Cutoff frequency in Hz.

    Returns:
        Smoothing factor alpha in [0, 1].
    """
    r = 2.0 * np.pi * cutoff * te
    return r / (r + 1.0)


@njit(cache=True, fastmath=True)  # type: ignore[reportUntypedFunctionDecorator]
def _exponential_smoothing_numba(alpha: float, x: float, x_prev: float) -> float:
    """Apply exponential smoothing filter (jitted).

    Args:
        alpha: Smoothing factor.
        x: Current input value.
        x_prev: Previous filtered value.

    Returns:
        Filtered output value.
    """
    return alpha * x + (1.0 - alpha) * x_prev


@njit(cache=True, fastmath=True)  # type: ignore[reportUntypedFunctionDecorator]
def _one_euro_filter_sequence_numba(
    x: np.ndarray,
    freq: float,
    min_cutoff: float,
    beta: float,
    derivative_cutoff: float,
) -> np.ndarray:
    """Filter a complete sequence using One-Euro filter (jitted).

    Args:
        x: Input sequence (num_samples,).
        freq: Sampling frequency in Hz.
        min_cutoff: Minimum cutoff frequency in Hz.
        beta: Speed coefficient.
        derivative_cutoff: Cutoff for derivative filtering.

    Returns:
        Filtered sequence (num_samples,).
    """
    n = len(x)
    filtered = np.zeros_like(x)
    # #948: corrupt video can report freq=0 (cv2.CAP_PROP_FPS=0). Fall back to
    # frame-based dt=1.0 (one sample per step, frame-index time) — mirrors the
    # phase-detector sibling (phase_detector.py:234) and the Sports2D tracker.
    # Valid freq unchanged; freq<=0 yields finite output instead of ZeroDivisionError.
    dt = 1.0 / freq if freq > 0 else 1.0

    # Initialization
    x_prev = x[0]
    dx_prev = 0.0
    filtered[0] = x_prev

    for i in range(1, n):
        # Compute derivative
        dx = (x[i] - x_prev) / dt

        # Filter derivative
        alpha_d = _smoothing_factor_numba(dt, derivative_cutoff)
        dx_filtered = _exponential_smoothing_numba(alpha_d, dx, dx_prev)

        # Adaptive cutoff
        cutoff = min_cutoff + beta * abs(dx_filtered)

        # Filter signal
        alpha = _smoothing_factor_numba(dt, cutoff)
        x_filtered = _exponential_smoothing_numba(alpha, x[i], x_prev)

        # Update state
        filtered[i] = x_filtered
        x_prev = x_filtered
        dx_prev = dx_filtered

    return filtered


@njit(cache=True, fastmath=True)  # type: ignore[reportUntypedFunctionDecorator]
def smooth_trajectory_2d_numba(
    trajectory: np.ndarray,
    fps: float,
    min_cutoff: float,
    beta: float,
    d_cutoff: float,
) -> np.ndarray:
    """Smooth 2D trajectory with OneEuro filter (jitted).

    Args:
        trajectory: (T, 2) array of (x, y) coordinates.
        fps: Frame rate.
        min_cutoff: Minimum cutoff frequency.
        beta: Speed coefficient.
        d_cutoff: Derivative cutoff frequency.

    Returns:
        (T, 2) smoothed trajectory.
    """
    t = trajectory.shape[0]
    smoothed = np.empty_like(trajectory)

    # Smooth x and y separately using jitted filter
    for dim in range(2):
        series = trajectory[:, dim]
        smoothed[:, dim] = _one_euro_filter_sequence_numba(series, fps, min_cutoff, beta, d_cutoff)

    return smoothed


def _fill_nan_1d(series: np.ndarray, nan_mask: np.ndarray) -> np.ndarray:
    """Fill NaN in a 1D series with linear interpolation, ffill/bfill at edges.

    #462: the numba One-Euro path crashes on NaN input. We fill NaNs with
    finite values so the filter runs, then the caller restores NaN at the
    original mask. An all-NaN series (no observation at all) is filled with
    0.0 — the restored NaN mask hides it from downstream consumers.
    """
    out = series.astype(np.float64, copy=True)
    n = out.shape[0]
    idx = np.arange(n)
    finite = ~nan_mask
    if not finite.any():
        return np.zeros(n, dtype=np.float64)
    out[nan_mask] = np.interp(idx[nan_mask], idx[finite], out[finite])
    return out


def _fill_nan_2d(traj: np.ndarray, nan_mask: np.ndarray) -> np.ndarray:
    """Fill NaN per-column in a (T, 2) trajectory via _fill_nan_1d. #462."""
    out = traj.astype(np.float64, copy=True)
    for dim in range(traj.shape[1]):
        out[:, dim] = _fill_nan_1d(traj[:, dim], nan_mask[:, dim])
    return out


@dataclass(frozen=True)
class OneEuroFilterConfig:
    """Configuration for One-Euro Filter parameters.

    Defaults optimized for figure skating motion at 25-60 fps.

    Attributes:
        min_cutoff: Minimum cutoff frequency (Hz) - controls jitter reduction
            at low speeds. Lower = more smoothing but more lag. Range: [0.1, 10.0]
        beta: Speed coefficient - reduces lag at high speeds.
            Higher = less lag but more jitter. Range: [0.0, 1.0]
        derivative_cutoff: Cutoff frequency for velocity estimation. Range: [0.1, 10.0]
        freq: Sampling frequency in Hz (frames per second).
    """

    min_cutoff: float = 1.0
    beta: float = 0.007
    derivative_cutoff: float = 1.0
    freq: float = 30.0


class OneEuroFilter:
    """One-Euro Filter for smoothing noisy 1D signals.

    Implements the adaptive low-pass filter from Casiez et al. (2012).
    Filters a single time series (e.g., x-coordinate of one joint).
    Stateful: processes samples incrementally.

    Example:
        >>> filter = OneEuroFilter(freq=30.0, min_cutoff=1.0, beta=0.007)
        >>> filtered = filter.reset_and_filter(x_sequence)
    """

    def __init__(
        self,
        freq: float,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        derivative_cutoff: float = 1.0,
    ) -> None:
        """Initialize One-Euro Filter.

        Args:
            freq: Sampling frequency in Hz (frames per second).
            min_cutoff: Minimum cutoff frequency in Hz.
            beta: Speed coefficient for adaptive cutoff.
            derivative_cutoff: Cutoff for derivative filtering.
        """
        self.freq: Final[float] = freq
        self.min_cutoff: Final[float] = min_cutoff
        self.beta: Final[float] = beta
        self.derivative_cutoff: Final[float] = derivative_cutoff

        # State variables (reset between sequences)
        self._x_prev: float = 0.0
        self._dx_prev: float = 0.0
        self._t_prev: float = 0.0
        self._initialized: bool = False

    @staticmethod
    def _smoothing_factor(te: float, cutoff: float) -> float:
        """Compute smoothing factor alpha from time interval and cutoff frequency.

        Uses Numba-jitted implementation for performance.

        Args:
            te: Time interval since last sample.
            cutoff: Cutoff frequency in Hz.

        Returns:
            Smoothing factor alpha in [0, 1].
        """
        return _smoothing_factor_numba(te, cutoff)

    @staticmethod
    def _exponential_smoothing(alpha: float, x: float, x_prev: float) -> float:
        """Apply exponential smoothing filter.

        Uses Numba-jitted implementation for performance.

        Args:
            alpha: Smoothing factor.
            x: Current input value.
            x_prev: Previous filtered value.

        Returns:
            Filtered output value.
        """
        return _exponential_smoothing_numba(alpha, x, x_prev)

    def reset(self) -> None:
        """Reset filter state for new sequence."""
        self._x_prev = 0.0
        self._dx_prev = 0.0
        self._t_prev = 0.0
        self._initialized = False

    def filter_sample(self, t: float, x: float) -> float:
        """Filter a single sample (stateful incremental processing).

        Args:
            t: Timestamp in seconds.
            x: Input value to filter.

        Returns:
            Filtered value.

        Raises:
            ValueError: If the timestamp is not finite, or if timestamps are
                not monotonically increasing.
        """
        # Reject non-finite timestamps (NaN/inf) before any arithmetic.
        # NaN bypasses the monotonic guard (`NaN <= x == False`) and poisons
        # `te = t - self._t_prev`, crashing `_smoothing_factor_numba` under
        # `fastmath=True` (NaN-as-0 → ZeroDivisionError). See #1033.
        if not math.isfinite(t):
            msg = f"Timestamp must be finite: t={t}"
            raise ValueError(msg)

        if not self._initialized:
            # First sample - pass through
            self._x_prev = x
            self._dx_prev = 0.0
            self._t_prev = t
            self._initialized = True
            return x

        # Check monotonic timestamps
        if t <= self._t_prev:
            msg = f"Timestamps must be monotonically increasing: {t} <= {self._t_prev}"
            raise ValueError(msg)

        # Time interval
        te = t - self._t_prev

        # Filter the derivative (velocity)
        dx = (x - self._x_prev) / te
        alpha_d = self._smoothing_factor(te, self.derivative_cutoff)
        dx_hat = self._exponential_smoothing(alpha_d, dx, self._dx_prev)

        # Adaptive cutoff based on filtered velocity
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)

        # Filter the signal
        alpha = self._smoothing_factor(te, cutoff)
        x_hat = self._exponential_smoothing(alpha, x, self._x_prev)

        # Update state
        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t

        return x_hat

    def filter_sequence(
        self,
        x: NDArray[np.float32],
        timestamps: NDArray[np.float32] | None = None,
    ) -> NDArray[np.float32]:
        """Filter a complete sequence (batch processing).

        Args:
            x: Input sequence (num_samples,).
            timestamps: Optional timestamps (num_samples,). If None, uses uniform spacing.

        Returns:
            Filtered sequence (num_samples,).
        """
        if timestamps is None:
            # #948: freq=0 (corrupt video) → frame-index timestamps (0,1,2,…)
            # instead of /self.freq ZeroDivision. Matches the kernel fallback.
            ts_step = 1.0 / self.freq if self.freq > 0 else 1.0
            timestamps = np.arange(len(x), dtype=np.float32) * ts_step

        if len(x) != len(timestamps):
            msg = f"Length mismatch: {len(x)} != {len(timestamps)}"
            raise ValueError(msg)

        self.reset()
        filtered = np.zeros_like(x)

        for i in range(len(x)):
            filtered[i] = self.filter_sample(float(timestamps[i]), float(x[i]))

        return filtered.astype(np.float32)

    def reset_and_filter(self, x: NDArray[np.float32]) -> NDArray[np.float32]:
        """Convenience method: reset and filter sequence with uniform timestamps.

        Args:
            x: Input sequence (num_samples,).

        Returns:
            Filtered sequence (num_samples,).
        """
        return self.filter_sequence(x, None)


class PoseSmoother:
    """Smooth pose sequences using One-Euro Filter.

    Applies One-Euro Filter to all pose keypoints independently.
    Each joint's x and y coordinates are filtered as separate time series.

    Supports H3.6M 17-keypoint format for 3D-only pipeline.

    Integration point in pipeline:
        PoseExtractor → PoseNormalizer → PoseSmoother → PhaseDetector
                                                          ↓
                                                    BiomechanicsAnalyzer
    """

    def __init__(
        self,
        config: OneEuroFilterConfig | None = None,
        freq: float = 30.0,
    ) -> None:
        """Initialize pose smoother.

        Args:
            config: Filter configuration. If None, uses skating-optimized defaults.
            freq: Sampling frequency in Hz (video FPS).
        """
        if config is None:
            config = OneEuroFilterConfig(freq=freq)

        self.config = config
        self.freq = freq

        # Create filter for each dimension (33 joints x 2 coords)
        # We'll create filters on-demand to save memory
        self._filters: dict[tuple[int, int], OneEuroFilter] = {}

    def _get_filter(self, joint_idx: int, coord_idx: int) -> OneEuroFilter:
        """Get or create filter for specific joint and coordinate.

        Args:
            joint_idx: BlazePose joint index (0-32).
            coord_idx: Coordinate index (0=x, 1=y).

        Returns:
            OneEuroFilter instance for this time series.
        """
        key = (joint_idx, coord_idx)
        if key not in self._filters:
            self._filters[key] = OneEuroFilter(
                freq=self.freq,
                min_cutoff=self.config.min_cutoff,
                beta=self.config.beta,
                derivative_cutoff=self.config.derivative_cutoff,
            )
        return self._filters[key]

    def smooth(self, poses: NormalizedPose) -> NormalizedPose:
        """Smooth pose sequence using One-Euro Filter (Numba batch path).

        Auto-detects 2D (N, J, 2) vs 3D (N, J, 3) input and delegates accordingly.

        Args:
            poses: NormalizedPose (num_frames, num_joints, 2 or 3).

        Returns:
            Smoothed poses with same shape as input.
        """
        _num_frames, num_joints, num_coords = poses.shape

        if num_coords == 3:
            return self.smooth_3d(poses)

        if num_coords != 2:
            msg = f"Expected shape (N, J, 2) or (N, J, 3), got {poses.shape}"
            raise ValueError(msg)

        if num_joints not in (17, 33):
            msg = f"Expected 17 or 33 joints, got {num_joints}"
            raise ValueError(msg)

        smoothed = np.zeros_like(poses)

        for joint_idx in range(num_joints):
            # #462: a single NaN keypoint crashes the numba One-Euro path —
            # @njit(fastmath=True) rewrites r/(r+1)→1/(1+1/r), and 1/NaN raises
            # ZeroDivisionError (not silent NaN). Mask NaN inputs, fill the
            # gap so the filter runs on finite values, then restore NaN where
            # the input was NaN — preserving it as a "no observation" sentinel
            # for downstream consumers instead of fabricating a value.
            traj = poses[:, joint_idx, :]
            nan_mask = np.isnan(traj)
            has_nan = bool(nan_mask.any())
            if has_nan:
                traj = _fill_nan_2d(traj, nan_mask)
            out = smooth_trajectory_2d_numba(
                traj,
                fps=self.config.freq,
                min_cutoff=self.config.min_cutoff,
                beta=self.config.beta,
                d_cutoff=self.config.derivative_cutoff,
            )
            if has_nan:
                out[nan_mask] = np.nan
            smoothed[:, joint_idx, :] = out

        return smoothed

    def smooth_3d(self, poses_3d: NDArray[np.float32]) -> NDArray[np.float32]:
        """Smooth 3D pose sequence using One-Euro Filter (Numba batch path).

        Args:
            poses_3d: 3D poses (num_frames, 17, 3) with x, y, z in meters.

        Returns:
            Smoothed 3D poses (num_frames, 17, 3).
        """
        _num_frames, num_joints, num_coords = poses_3d.shape

        if num_joints != 17 or num_coords != 3:
            msg = f"Expected shape (N, 17, 3), got {poses_3d.shape}"
            raise ValueError(msg)

        smoothed = np.zeros_like(poses_3d)

        for joint_idx in range(num_joints):
            # #462: mask NaN, fill, smooth, restore NaN — see smooth().
            traj2d = poses_3d[:, joint_idx, :2]
            nan_mask2 = np.isnan(traj2d)
            has_nan2 = bool(nan_mask2.any())
            if has_nan2:
                traj2d = _fill_nan_2d(traj2d, nan_mask2)
            out2d = smooth_trajectory_2d_numba(
                traj2d,
                fps=self.config.freq,
                min_cutoff=self.config.min_cutoff,
                beta=self.config.beta,
                d_cutoff=self.config.derivative_cutoff,
            )
            if has_nan2:
                out2d[nan_mask2] = np.nan
            smoothed[:, joint_idx, :2] = out2d

            series = poses_3d[:, joint_idx, 2]
            nan_mask1 = np.isnan(series)
            has_nan1 = bool(nan_mask1.any())
            if has_nan1:
                series = _fill_nan_1d(series, nan_mask1)
            out1d = _one_euro_filter_sequence_numba(
                series,
                self.config.freq,
                self.config.min_cutoff,
                self.config.beta,
                self.config.derivative_cutoff,
            )
            if has_nan1:
                out1d[nan_mask1] = np.nan
            smoothed[:, joint_idx, 2] = out1d

        return smoothed

    def smooth_phase_aware(
        self,
        poses: NormalizedPose,
        phase_boundaries: list[int],
    ) -> NormalizedPose:
        """Smooth poses with phase-aware processing.

        Resets filter at each phase boundary to avoid smoothing across
        rapid transitions (e.g., takeoff, landing).

        Args:
            poses: NormalizedPose (num_frames, 17, 2).
            phase_boundaries: List of frame indices where phases change.
                E.g., [takeoff, peak, landing] for jumps.

        Returns:
            Smoothed poses (num_frames, 17, 2).
        """
        if not phase_boundaries:
            return self.smooth(poses)

        # Sort boundaries and add start/end
        boundaries = sorted([0, *phase_boundaries, len(poses)])

        # Create output array
        smoothed = np.zeros_like(poses)

        # Process each phase independently
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i + 1]

            if end <= start:
                continue

            # Extract phase
            phase_poses = poses[start:end]

            # Smooth phase
            smoothed_phase = self.smooth(phase_poses)

            # Copy to output
            smoothed[start:end] = smoothed_phase

        return smoothed

    def smooth_phase_aware_3d(
        self,
        poses_3d: NDArray[np.float32],
        phase_boundaries: list[int],
    ) -> NDArray[np.float32]:
        """Smooth 3D poses with phase-aware processing.

        Resets filter at each phase boundary to avoid smoothing across
        rapid transitions (e.g., takeoff, landing).

        Args:
            poses_3d: (num_frames, 17, 3) 3D poses.
            phase_boundaries: List of frame indices where phases change.

        Returns:
            Smoothed 3D poses (num_frames, 17, 3).
        """
        if not phase_boundaries:
            return self.smooth_3d(poses_3d)

        boundaries = sorted([0, *phase_boundaries, len(poses_3d)])
        smoothed = np.zeros_like(poses_3d)

        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i + 1]
            if end <= start:
                continue
            phase_poses = poses_3d[start:end]
            smoothed_phase = self.smooth_3d(phase_poses)
            smoothed[start:end] = smoothed_phase

        return smoothed

    def set_frequency(self, freq: float) -> None:
        """Update sampling frequency and reset filters."""
        self.freq = freq
        self.config = OneEuroFilterConfig(
            freq=freq,
            min_cutoff=self.config.min_cutoff,
            beta=self.config.beta,
            derivative_cutoff=self.config.derivative_cutoff,
        )
        self._filters.clear()


def get_skating_optimized_config(fps: float = 30.0) -> OneEuroFilterConfig:
    """Get One-Euro Filter config optimized for figure skating.

    Figure skating has specific characteristics:
    - Slow preparatory movements (crossovers, setup)
    - Very fast rotations (jumps: 300-600 deg/s)
    - Sudden transitions (takeoff, landing)

    This config balances jitter reduction for slow movements
    with minimal lag for fast rotations.

    Args:
        fps: Video frame rate (affects frequency scaling).

    Returns:
        Optimized configuration for figure skating.
    """
    # Scale parameters based on FPS
    # Higher FPS → slightly higher min_cutoff (less smoothing needed)
    # Lower FPS → slightly lower min_cutoff (more smoothing needed)
    base_min_cutoff = 1.0
    fps_scaling = fps / 30.0  # Normalize to 30 FPS
    min_cutoff = base_min_cutoff * fps_scaling

    # Beta: controls lag reduction at high speeds
    # Skating needs fast response during rotations
    beta = 0.007  # Conservative: reduce jitter more than lag

    return OneEuroFilterConfig(
        min_cutoff=min_cutoff,
        beta=beta,
        derivative_cutoff=1.0,
        freq=fps,
    )
