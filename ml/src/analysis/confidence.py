"""Phase detection confidence scoring."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import PhaseDetectionResultV2, PhaseExtended


def compute_phase_confidence(
    phase: PhaseExtended,
    total_frames: int,
    fps: float,
) -> float:
    """Compute confidence for a single phase.

    Factors:
    1. Duration reasonableness (too short = low confidence)
    2. Detection method (com_parabola > tas_segment > heuristic)
    3. Frame coverage (fraction of total)
    4. Boundary smoothness (not provided here, defaults to 1.0)
    """
    # #1051: trust-boundary NaN guard. `fps > 0` and `total_frames > 0`
    # silently coerce NaN to False (NaN comparisons are False), masking
    # bad upstream inputs. Coerce NaN/inf to safe defaults at the boundary
    # so a corrupt input falls through to the legitimate fps=0 / total_frames=0
    # path (which already returns 0 confidence via the `else 0` branch)
    # AND so `duration_sec`/`coverage` math is NaN-free downstream.
    # Mirrors the PR 1025 (commit 258488c8) `np.isfinite` guard pattern.
    if not math.isfinite(fps):
        fps = 0.0
    if not math.isfinite(float(total_frames)):
        total_frames = 0

    duration_frames = phase.end_frame - phase.start_frame
    duration_sec = duration_frames / fps if fps > 0 else 0

    # Factor 1: Duration reasonableness
    if duration_sec < 0.05:  # Less than 50ms is suspicious
        duration_factor = 0.3
    elif duration_sec < 0.1:
        duration_factor = 0.6
    else:
        duration_factor = 1.0

    # Factor 2: Detection method reliability
    method_factors = {"com_parabola": 0.95, "tas_segment": 0.85, "heuristic": 0.7}
    method_factor = method_factors.get(phase.detection_method, 0.5)

    # Factor 3: Frame coverage
    coverage = duration_frames / total_frames if total_frames > 0 else 0
    coverage_factor = min(1.0, coverage / 0.1)  # 10%+ coverage = full factor

    # Weighted combination
    confidence = (
        phase.confidence * 0.4
        + duration_factor * 0.25
        + method_factor * 0.25
        + coverage_factor * 0.10
    )

    # #561: explicit NaN guard. Python's min(1.0, NaN) returns 1.0
    # (NaN comparisons are False, so min defaults to the first arg),
    # then max(0.0, 1.0) returns 1.0. A phase with completely
    # missing/NaN upstream confidence was reported as 100% confident.
    # If confidence is NaN, the phase detection is unreliable —
    # return 0.0.
    if math.isnan(confidence):
        return 0.0
    return max(0.0, min(1.0, confidence))


def compute_overall_confidence(
    result: PhaseDetectionResultV2, total_frames: int, fps: float
) -> float:
    """Compute overall confidence across all phases.

    Weighted average with emphasis on key phases (takeoff, air, landing).
    """
    if not result.phases:
        return 0.0

    phase_weights = {
        "approach": 0.10,
        "takeoff": 0.25,
        "air": 0.30,
        "landing": 0.25,
        "glide_out": 0.10,
    }

    total_weight = 0.0
    weighted_sum = 0.0
    for phase in result.phases:
        conf = compute_phase_confidence(phase, total_frames, fps)
        w = phase_weights.get(phase.name, 0.15)
        weighted_sum += conf * w
        total_weight += w

    return weighted_sum / total_weight if total_weight > 0 else 0.0
