"""Bridge to ML analysis scoring. Pure-data function, no GPU/pipeline deps."""

from __future__ import annotations

from typing import Any


def compute_subscores_safe(metrics: dict[str, float]) -> Any:
    """Call ML compute_subscores with safe fallback.

    Returns MultiDimensionalScore dataclass. If ML import fails, returns a
    neutral score so the pipeline doesn't crash.
    """
    try:
        from src.analysis.multi_score import compute_subscores  # type: ignore[import-untyped]

        return compute_subscores(metrics)
    except Exception:
        # Fallback: neutral 5.0/10 score
        from src.analysis.types import (  # type: ignore[import-untyped]
            MultiDimensionalScore,
            SubScore,
        )

        subscores = [
            SubScore("takeoff_power", "Взлётная мощь", 5.0, 0.5, ["airtime"]),
            SubScore("rotation_axis", "Ось вращения", 5.0, 0.5, ["rotation_speed"]),
            SubScore("arm_coordination", "Координация рук", 5.0, 0.5, ["symmetry"]),
            SubScore("landing_absorption", "Амортизация", 5.0, 0.5, ["landing_knee_angle"]),
            SubScore("core_stability", "Стабильность корпуса", 5.0, 0.5, ["trunk_lean"]),
        ]
        return MultiDimensionalScore(
            subscores=subscores,
            overall=5.0,
            data_quality="partial",
            skeleton_reliability="uncertain",
        )