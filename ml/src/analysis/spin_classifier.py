"""Rule-based spin type classifier for figure skating.

Classifies spins into upright, one-foot, and scratch types based on
biomechanical features: duration, hip vertical displacement, and angular velocity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .element_defs import SPIN_TYPES

if TYPE_CHECKING:
    from numpy.typing import NDArray


def classify_spin(
    duration_s: float,
    hip_y_range: float,
    angular_velocity_mean: float,
) -> tuple[str, float]:
    """Classify spin type from biomechanical features.

    Args:
        duration_s: Duration of the spinning segment in seconds.
        hip_y_range: Normalized vertical hip displacement during spin.
        angular_velocity_mean: Mean angular velocity during spin (deg/s).

    Returns:
        (spin_name, confidence) tuple. Confidence in [0, 1].
    """
    candidates: list[tuple[str, float]] = []
    for spin in SPIN_TYPES.values():
        score = 0.0

        # Duration check
        if duration_s >= spin.min_duration_s:
            score += 0.3
        else:
            score += 0.1 * (duration_s / spin.min_duration_s)

        # Hip displacement check (less displacement = more upright)
        if hip_y_range <= spin.hip_y_range_max:
            score += 0.4
        else:
            score += 0.1

        # Angular velocity (higher = more advanced spin)
        if angular_velocity_mean > 300:
            score += 0.3
        elif angular_velocity_mean > 200:
            score += 0.2
        else:
            score += 0.1

        candidates.append((spin.name, score))

    if not candidates:
        return "unknown", 0.0

    best = max(candidates, key=lambda x: x[1])
    return best[0], min(best[1], 1.0)


def detect_spin(
    angular_velocity_series: NDArray[np.floating],
    hip_y_series: NDArray[np.floating],
    fps: float,
    threshold_deg_per_sec: float = 200.0,
) -> tuple[bool, float, float]:
    """Detect if a segment contains a spin.

    Args:
        angular_velocity_series: Per-frame angular velocity (deg/s).
        hip_y_series: Per-frame normalized hip Y position.
        fps: Video frame rate.
        threshold_deg_per_sec: Minimum angular velocity to count as spinning.

    Returns:
        (is_spin, duration_s, hip_y_range) tuple.
    """
    is_spinning = np.abs(angular_velocity_series) > threshold_deg_per_sec

    if not np.any(is_spinning):
        return False, 0.0, 0.0

    spin_frames = np.where(is_spinning)[0]
    duration_s = (spin_frames[-1] - spin_frames[0]) / fps
    hip_y_range = float(np.ptp(hip_y_series[is_spinning])) if np.any(is_spinning) else 0.0

    return duration_s >= 1.0, duration_s, hip_y_range
