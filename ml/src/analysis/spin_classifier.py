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
) -> tuple[bool, float, float, NDArray[np.bool_]]:
    """Detect if a segment contains a spin.

    Args:
        angular_velocity_series: Per-frame angular velocity (deg/s).
        hip_y_series: Per-frame normalized hip Y position.
        fps: Video frame rate.
        threshold_deg_per_sec: Minimum angular velocity to count as spinning.

    Returns:
        (is_spin, duration_s, hip_y_range, is_spinning_mask) tuple.
        ``is_spinning_mask`` is the per-frame boolean mask of frames above the
        spin threshold (#858) so callers can restrict per-frame aggregates
        (e.g. peak velocity) to the detected spin segment instead of taking a
        global max over the whole clip.
    """
    above = np.abs(angular_velocity_series) > threshold_deg_per_sec

    if not np.any(above):
        return False, 0.0, 0.0, above

    # #858: find CONTIGUOUS above-threshold runs. A transient shoulder-vector
    # jump OUTSIDE the spin (entry arm swing, exit flail, tracking glitch) is
    # a 1-2 frame gradient spike — its own short run, not part of the spin.
    # The spin mask must be the spin SEGMENT (the run that lasts ≥ 1.0 s), not
    # every above-threshold frame, or an isolated spike merges into the global
    # max and is reported as the spin peak.
    change = np.diff(above.astype(np.int8))
    run_starts = np.where(change == 1)[0] + 1
    if above[0]:
        run_starts = np.insert(run_starts, 0, 0)
    run_ends = np.where(change == -1)[0] + 1  # exclusive end
    if above[-1]:
        run_ends = np.append(run_ends, above.size)

    best_start, best_end, best_duration = 0, 0, 0.0
    for start, end in zip(run_starts, run_ends, strict=True):
        duration = (end - start) / fps if fps > 0 else 0.0
        if duration > best_duration:
            best_start, best_end, best_duration = start, end, duration

    spin_mask = np.zeros_like(above, dtype=bool)
    # #515: spin_frames[-1] - spin_frames[0] is a SPAN (exclusive end); the
    # frame COUNT (inclusive end) is +1. A 30-frame spin at 30 fps (indices
    # 0..29) is a true 1.0 s spin, but span=29 → 29/30=0.9667 < 1.0 →
    # is_spin=False; the exact-1.0 s threshold spin is missed. Use count.
    # #505: fps<=0 → 0.0 duration (fails the >= 1.0 spin gate; #499/#501 sibling).
    is_spin = best_duration >= 1.0
    if is_spin:
        spin_mask[best_start:best_end] = True
        hip_y_range = float(np.ptp(hip_y_series[spin_mask]))
    else:
        hip_y_range = float(np.ptp(hip_y_series[above])) if np.any(above) else 0.0

    return is_spin, best_duration, hip_y_range, spin_mask
