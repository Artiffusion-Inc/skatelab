"""Multi-dimensional scoring for figure skating elements."""

from __future__ import annotations

import math

from .types import MultiDimensionalScore, SubScore


def _normalize(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp and normalize to [0, 1].

    #850: NaN must be treated as a missing metric (neutral 0.0), not perfect.
    Bare ``max(0.0, min(1.0, NaN))`` clips to 1.0 because NaN comparisons are
    always False (the non-NaN operand wins), inflating broken/failed-metric
    sessions to a perfect 10.0. Guard before the clamp.
    """
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


def compute_subscores(metrics: dict[str, float]) -> MultiDimensionalScore:
    """Compute 5 subscores from biomechanical metrics.

    Args:
        metrics: Dict with keys like airtime, relative_jump_height, rotation_speed, etc.

    Returns:
        MultiDimensionalScore with 5 subscores and weighted overall.
    """
    # takeoff_power: airtime + height + approach consistency
    takeoff = _normalize(
        metrics.get("airtime", 0) / 0.7 * 0.4
        + metrics.get("relative_jump_height", 0) / 1.0 * 0.4
        # #500: align with ML emit key. metrics.py:348 emits
        # `approach_direction_change` (the angle in degrees), not
        # `approach_consistency`. The old name was a typo in the
        # consumer; the metrics dict never contained it, so the term
        # was always (1 - abs(0)/90) * 0.2 = 0.2 — a constant bonus
        # for every jump regardless of approach variability. Now
        # takeoff_power responds to approach direction.
        + (1 - abs(metrics.get("approach_direction_change", 0)) / 90) * 0.2
    )

    # rotation_axis — combines rotation speed, total rotation, and under-rotation
    rotation = _normalize(
        min(metrics.get("rotation_speed", 0) / 720, 1.0) * 0.4
        + min(metrics.get("total_rotation_deg", 0) / 1620, 1.0) * 0.3
        # #555: under_rotation_deg is negative on over-rotation (e.g. measured 1100deg vs target 1080deg). Sign-sensitive formula (1 - x/90) REWARDS over-rotation (1 - -20/90 = 1.222 -> 0.367 > nominal 0.3). abs() — both under/over-rotation penalised equally (judges deduct for both).
        + (1 - abs(metrics.get("under_rotation_deg", 0)) / 90) * 0.3
    )

    # arm_coordination: arm position + symmetry
    arms = _normalize(metrics.get("arm_position_score", 0) * 0.6 + metrics.get("symmetry", 0) * 0.4)

    # landing_absorption: knee angle + stability + smoothness + hard_landing
    # hard_landing scale: 1.0 = soft, 0.0 = very hard (compute_hard_landing,
    # metrics.py:988). Soft landing → higher absorption, so use the value
    # directly. Old code used (1 - hard_landing), inverting the scale (#434).
    landing = _normalize(
        (1 - abs(metrics.get("landing_knee_angle", 110) - 110) / 40) * 0.3
        + metrics.get("landing_knee_stability", 0) * 0.3
        + metrics.get("landing_smoothness", 0) * 0.2
        + metrics.get("hard_landing", 0) * 0.2
    )

    # core_stability: trunk recovery + torso lean
    core = _normalize(
        metrics.get("landing_trunk_recovery", 0) * 0.5
        + (1 - abs(metrics.get("approach_torso_lean", 0)) / 20) * 0.25
        + (1 - abs(metrics.get("trunk_lean", 0)) / 20) * 0.25
    )

    subscores = [
        SubScore(
            "takeoff_power",
            "Взлётная мощь",
            takeoff * 10,
            0.85,
            ["airtime", "relative_jump_height"],
        ),
        SubScore(
            "rotation_axis",
            "Ось вращения",
            rotation * 10,
            0.72,
            ["rotation_speed", "total_rotation_deg"],
        ),
        SubScore(
            "arm_coordination",
            "Координация рук",
            arms * 10,
            0.68,
            ["arm_position_score", "symmetry"],
        ),
        SubScore(
            "landing_absorption",
            "Амортизация",
            landing * 10,
            0.91,
            ["landing_knee_angle", "hard_landing"],
        ),
        SubScore(
            "core_stability",
            "Стабильность корпуса",
            core * 10,
            0.79,
            ["landing_trunk_recovery", "trunk_lean"],
        ),
    ]

    weights = [0.30, 0.25, 0.15, 0.25, 0.10]
    # #512: weights sum to 1.05, not 1.0 — a perfect session (all subscores
    # 10.0) gave overall = 10 * 1.05 = 10.5, exceeding the /10 ceiling and
    # crossing gamification skill-unlock thresholds (>=8.0 gold) early.
    # Normalize the weighted sum by the weight total so overall stays in
    # [0, 10] regardless of the weight vector (preserves relative balance).
    weight_total = sum(weights)
    overall = sum(s.value * w for s, w in zip(subscores, weights, strict=True)) / weight_total

    return MultiDimensionalScore(
        subscores=subscores,
        overall=overall,
        data_quality="good",
        skeleton_reliability="reliable",
    )
