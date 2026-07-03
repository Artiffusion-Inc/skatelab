"""
Metric Registry — Single Source of Truth for Biomechanical Metrics.

Defines all available metrics, their display properties, and applicability
to different element types. Shared between backend and frontend.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MetricDef:
    """Definition of a biomechanical metric.

    Attributes:
        name: Unique metric identifier (snake_case)
        label_ru: Russian display label
        unit: Unit of measurement ("s", "deg", "score", "norm", "ratio", "deg/s")
        format: Python format spec (e.g., ".2f" for 2 decimal places)
        direction: "higher" = higher is better, "lower" = lower is better
        element_types: Tuple of element types this metric applies to
        ideal_range: (min, max) range for elite-level performance
    """

    name: str
    label_ru: str
    unit: Literal["s", "deg", "score", "norm", "ratio", "deg/s"]
    format: str
    direction: Literal["higher", "lower"]
    element_types: tuple[str, ...]
    ideal_range: tuple[float, float]


# Element type groups — ISU code families (canonical).
# Replaces the legacy slug vocabulary (waltz_jump, three_turn, upright_spin, ...).
AXEL_FAMILY = ("1A", "2A", "3A", "4A")
TOE_LOOP_FAMILY = ("1T", "2T", "3T", "4T")
SALCHOW_FAMILY = ("1S", "2S", "3S", "4S")
LOOP_FAMILY = ("1Lo", "2Lo", "3Lo", "4Lo")
FLIP_FAMILY = ("1F", "2F", "3F", "4F")
LUTZ_FAMILY = ("1Lz", "2Lz", "3Lz", "4Lz")
EULER = ("1Eu",)

JUMP_ELEMENTS = (
    *AXEL_FAMILY,
    *TOE_LOOP_FAMILY,
    *SALCHOW_FAMILY,
    *LOOP_FAMILY,
    *FLIP_FAMILY,
    *LUTZ_FAMILY,
    *EULER,
)

SPIN_ELEMENTS = (
    "CSp1",
    "CSp2",
    "CSp3",
    "CSp4",
    "FSp1",
    "FSp2",
    "FSp3",
    "FSp4",
    "LSp1",
    "LSp2",
    "LSp3",
    "LSp4",
    "USp1",
    "USp2",
    "USp3",
    "USp4",
    "CSpB1",
    "CSpB2",
    "CSpB3",
    "CSpB4",
)

STEP_ELEMENTS = ("StSq1", "StSq2", "StSq3", "StSq4")
CHOREO_ELEMENTS = ("ChSq1",)

# Metrics formerly under the "three_turn" slug (turn/edge technique) now apply
# to step sequences — the closest ISU element family for turn technique.
TURN_METRIC_ELEMENTS = STEP_ELEMENTS

ALL_ELEMENTS = JUMP_ELEMENTS + SPIN_ELEMENTS + STEP_ELEMENTS + CHOREO_ELEMENTS


# Metric registry
METRIC_REGISTRY: dict[str, MetricDef] = {
    # Jump-specific metrics
    "airtime": MetricDef(
        name="airtime",
        label_ru="Время полёта",
        unit="s",
        format=".2f",
        direction="higher",
        element_types=JUMP_ELEMENTS,
        ideal_range=(0.3, 0.7),
    ),
    "max_height": MetricDef(
        name="max_height",
        label_ru="Высота прыжка",
        unit="norm",
        format=".3f",
        direction="higher",
        element_types=JUMP_ELEMENTS,
        ideal_range=(0.2, 0.5),
    ),
    "relative_jump_height": MetricDef(
        name="relative_jump_height",
        label_ru="Относительная высота",
        unit="ratio",
        format=".2f",
        direction="higher",
        element_types=JUMP_ELEMENTS,
        ideal_range=(0.3, 1.5),
    ),
    "landing_knee_angle": MetricDef(
        name="landing_knee_angle",
        label_ru="Угол колена при приземлении",
        unit="deg",
        format=".0f",
        direction="lower",
        element_types=JUMP_ELEMENTS,
        ideal_range=(90, 130),
    ),
    "landing_knee_stability": MetricDef(
        name="landing_knee_stability",
        label_ru="Стабильность приземления",
        unit="score",
        format=".2f",
        direction="higher",
        element_types=JUMP_ELEMENTS,
        ideal_range=(0.5, 1.0),
    ),
    "landing_trunk_recovery": MetricDef(
        name="landing_trunk_recovery",
        label_ru="Восстановление корпуса",
        unit="score",
        format=".2f",
        direction="higher",
        element_types=JUMP_ELEMENTS,
        ideal_range=(0.5, 1.0),
    ),
    "arm_position_score": MetricDef(
        name="arm_position_score",
        label_ru="Контроль рук",
        unit="score",
        format=".2f",
        direction="higher",
        element_types=JUMP_ELEMENTS,
        ideal_range=(0.6, 1.0),
    ),
    "rotation_speed": MetricDef(
        name="rotation_speed",
        label_ru="Скорость вращения",
        unit="deg/s",
        format=".0f",
        direction="higher",
        element_types=JUMP_ELEMENTS,
        ideal_range=(300, 550),
    ),
    "total_rotation_deg": MetricDef(
        name="total_rotation_deg",
        label_ru="Полное вращение",
        unit="deg",
        format=".0f",
        direction="higher",
        element_types=(*JUMP_ELEMENTS, *SPIN_ELEMENTS),
        ideal_range=(360, 1620),
    ),
    "rotation_count": MetricDef(
        name="rotation_count",
        label_ru="Количество вращений",
        unit="score",
        format=".1f",
        direction="higher",
        element_types=(*JUMP_ELEMENTS, *SPIN_ELEMENTS),
        ideal_range=(1.0, 4.5),
    ),
    "under_rotation_deg": MetricDef(
        name="under_rotation_deg",
        label_ru="Недокрут",
        unit="deg",
        format=".0f",
        direction="lower",
        element_types=JUMP_ELEMENTS,
        ideal_range=(0, 90),
    ),
    "jump_type": MetricDef(
        name="jump_type",
        label_ru="Тип прыжка",
        unit="score",
        format=".2f",
        direction="higher",
        element_types=JUMP_ELEMENTS,
        ideal_range=(0.5, 1.0),
    ),
    # Step/turn technique metrics (formerly under "three_turn")
    "knee_angle": MetricDef(
        name="knee_angle",
        label_ru="Угол колена",
        unit="deg",
        format=".0f",
        direction="lower",
        element_types=TURN_METRIC_ELEMENTS,
        ideal_range=(100, 140),
    ),
    "trunk_lean": MetricDef(
        name="trunk_lean",
        label_ru="Наклон корпуса",
        unit="deg",
        format=".1f",
        direction="lower",
        element_types=TURN_METRIC_ELEMENTS,
        ideal_range=(-15, 20),
    ),
    "edge_change_smoothness": MetricDef(
        name="edge_change_smoothness",
        label_ru="Плавность смены ребра",
        unit="score",
        format=".2f",
        direction="higher",
        element_types=TURN_METRIC_ELEMENTS,
        ideal_range=(0.1, 0.5),
    ),
    # Spin-specific metrics
    "spin_type": MetricDef(
        name="spin_type",
        label_ru="Тип вращения",
        unit="score",
        format=".2f",
        direction="higher",
        element_types=SPIN_ELEMENTS,
        ideal_range=(0.5, 1.0),
    ),
    "spin_peak_velocity": MetricDef(
        name="spin_peak_velocity",
        label_ru="Пиковая скорость вращения",
        unit="deg/s",
        format=".0f",
        direction="higher",
        element_types=SPIN_ELEMENTS,
        ideal_range=(300, 600),
    ),
    # Universal metrics
    "symmetry": MetricDef(
        name="symmetry",
        label_ru="Симметрия",
        unit="score",
        format=".2f",
        direction="higher",
        element_types=ALL_ELEMENTS,
        ideal_range=(0.6, 1.0),
    ),
    # DS_Skating technique metrics
    "rotation_discrepancy": MetricDef(
        name="rotation_discrepancy",
        label_ru="Расхождение подсчёта вращений",
        unit="score",
        format=".0f",
        direction="lower",
        element_types=(*JUMP_ELEMENTS, *SPIN_ELEMENTS),
        ideal_range=(0, 0),
    ),
    "spread_eagle_angle": MetricDef(
        name="spread_eagle_angle",
        label_ru="Угол развода ног (spread eagle)",
        unit="deg",
        format=".0f",
        direction="higher",
        element_types=TURN_METRIC_ELEMENTS,
        ideal_range=(150, 180),
    ),
    "ina_bauer_score": MetricDef(
        name="ina_bauer_score",
        label_ru="Оценка Ina Bauer",
        unit="score",
        format=".2f",
        direction="higher",
        element_types=TURN_METRIC_ELEMENTS,
        ideal_range=(0.7, 1.0),
    ),
    "spiral_indicator": MetricDef(
        name="spiral_indicator",
        label_ru="Индикатор спирали",
        unit="norm",
        format=".3f",
        direction="lower",
        element_types=TURN_METRIC_ELEMENTS,
        ideal_range=(0, 0.05),
    ),
    # GOE-derived metrics
    "goe_score": MetricDef(
        name="goe_score",
        label_ru="Оценка элемента (баллы)",
        unit="score",
        format=".2f",
        direction="higher",
        element_types=(*JUMP_ELEMENTS, *SPIN_ELEMENTS, *STEP_ELEMENTS),
        ideal_range=(0.0, 20.0),
    ),
}


def get_metrics_for_element(element_type: str) -> dict[str, MetricDef]:
    """Return metrics applicable to a given element type.

    Args:
        element_type: ISU element code (e.g., "3A", "CSp4", "StSq1", "ChSq1")

    Returns:
        Dictionary mapping metric names to MetricDef objects

    Raises:
        ValueError: If element_type is not a recognized ISU code. Legacy
            slug vocabulary ("waltz_jump", "three_turn", "axel", ...) is
            rejected — callers must pass canonical ISU codes.
    """
    if element_type not in ALL_ELEMENTS:
        raise ValueError(f"Unknown element type: {element_type}. Valid options: {ALL_ELEMENTS}")

    return {
        metric_name: metric_def
        for metric_name, metric_def in METRIC_REGISTRY.items()
        if element_type in metric_def.element_types
    }
