"""Figure skating element definitions and ideal metrics.

This module defines the skating elements supported by the system,
including their biomechanical characteristics and ideal performance ranges.
"""

from dataclasses import dataclass

from ..types import H36Key


@dataclass(frozen=True)
class ElementDef:
    """Definition of a figure skating element.

    Attributes:
        name: Element identifier (e.g., 'three_turn', 'waltz_jump').
        name_ru: Russian name for display.
        rotations: Number of rotations (0.0 for steps, 1.0+ for jumps, 1.5 for axel).
        has_toe_pick: True if takeoff uses toe pick (toe loop, flip, lutz).
        key_joints: List of H36Key indices relevant for analysis.
        ideal_metrics: Dict of metric_name -> (min_good, max_good) ranges.
        isu_prefix: ISU code prefix for SOV lookup (e.g., 'T' for toe loop, 'A' for axel).
    """

    name: str
    name_ru: str
    rotations: float
    has_toe_pick: bool
    key_joints: list[int]
    ideal_metrics: dict[str, tuple[float, float]]
    isu_prefix: str = ""


# Element definitions ordered by complexity
ELEMENT_DEFS: dict[str, ElementDef] = {
    "three_turn": ElementDef(
        name="three_turn",
        name_ru="тройка",
        rotations=0,
        has_toe_pick=False,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
        ],
        ideal_metrics={
            "knee_angle": (100, 140),  # Knee bend during entry (flexed knees)
            "trunk_lean": (-15, 20),  # Torso angle relative to vertical (slight forward OK)
            "edge_change_smoothness": (0.1, 0.5),  # Smooth edge transition (low std = smooth)
            "symmetry": (0.6, 1.0),  # Body symmetry score
        },
        isu_prefix="StSq",
    ),
    "waltz_jump": ElementDef(
        name="waltz_jump",
        name_ru="вальсовый прыжок",
        rotations=1,  # Half jump, but treated as jump for analysis
        has_toe_pick=False,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
            H36Key.LWRIST,
            H36Key.RWRIST,
        ],
        ideal_metrics={
            "airtime": (0.3, 0.7),  # Seconds in flight
            "max_height": (0.2, 0.5),  # Normalized height units
            "landing_knee_angle": (70, 110),  # Knee angle at landing (shock absorption)
            "arm_position_score": (0.6, 1.0),  # Arms controlled (close to body)
            "takeoff_angle": (70, 85),  # Takeoff angle relative to ice
            "landing_knee_stability": (0.5, 1.0),  # Knee stability after landing
            "landing_trunk_recovery": (0.5, 1.0),  # Trunk stays upright after landing
            "relative_jump_height": (0.3, 1.5),  # Height normalized by spine length
            "rotation_speed": (0, 360),  # Waltz jump is half rotation
            "landing_com_velocity": (-2.0, 0.0),
            "landing_smoothness": (0.5, 1.0),
            "approach_torso_lean": (-30, 30),
            "approach_direction_change": (0, 90),
            "symmetry": (0.6, 1.0),
            "toe_assist_proxy": (0.5, 1.0),
            "hard_landing": (0.5, 1.0),
            "goe_score": (5.0, 10.0),
        },
        isu_prefix="1A",
    ),
    "toe_loop": ElementDef(
        name="toe_loop",
        name_ru="перекидной",
        rotations=1,
        has_toe_pick=True,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
        ],
        ideal_metrics={
            "airtime": (0.35, 0.6),  # Seconds for single rotation
            "rotation_speed": (300, 500),  # Degrees per second
            "landing_knee_angle": (80, 120),  # Knee angle at landing
            "edge_quality": (0.7, 1.0),  # Clean edge on landing
            "toe_pick_timing": (0.1, 0.3),  # Time from toe pick to takeoff
            "landing_knee_stability": (0.5, 1.0),  # Knee stability after landing
            "landing_trunk_recovery": (0.5, 1.0),  # Trunk stays upright after landing
            "relative_jump_height": (0.3, 1.5),  # Height normalized by spine length
            "landing_com_velocity": (-2.0, 0.0),
            "landing_smoothness": (0.5, 1.0),
            "approach_torso_lean": (-30, 30),
            "approach_direction_change": (0, 90),
            "toe_assist_proxy": (0.5, 1.0),
            "hard_landing": (0.5, 1.0),
            "goe_score": (5.0, 10.0),
        },
        isu_prefix="T",
    ),
    "flip": ElementDef(
        name="flip",
        name_ru="флип",
        rotations=1,
        has_toe_pick=True,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
        ],
        ideal_metrics={
            "airtime": (0.35, 0.6),  # Seconds for single rotation
            "rotation_speed": (350, 550),  # Degrees per second
            "landing_knee_angle": (90, 130),  # Knee angle at landing
            "pick_quality": (0.7, 1.0),  # Clean toe pick
            "air_position": (0.7, 1.0),  # Body position in air (tight vs loose)
            "landing_knee_stability": (0.5, 1.0),  # Knee stability after landing
            "landing_trunk_recovery": (0.5, 1.0),  # Trunk stays upright after landing
            "relative_jump_height": (0.3, 1.5),  # Height normalized by spine length
            "landing_com_velocity": (-2.0, 0.0),
            "landing_smoothness": (0.5, 1.0),
            "approach_torso_lean": (5, 30),
            "approach_direction_change": (0, 45),
            "toe_assist_proxy": (0.5, 1.0),
            "hard_landing": (0.5, 1.0),
            "goe_score": (5.0, 10.0),
        },
        isu_prefix="F",
    ),
    "salchow": ElementDef(
        name="salchow",
        name_ru="перекидной",
        rotations=1,
        has_toe_pick=False,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
        ],
        ideal_metrics={
            "airtime": (0.3, 0.6),
            "max_height": (0.15, 0.4),
            "landing_knee_angle": (80, 120),
            "rotation_speed": (300, 500),
            "takeoff_angle": (65, 85),
            "landing_knee_stability": (0.5, 1.0),  # Knee stability after landing
            "landing_trunk_recovery": (0.5, 1.0),  # Trunk stays upright after landing
            "relative_jump_height": (0.3, 1.5),  # Height normalized by spine length
            "landing_com_velocity": (-2.0, 0.0),
            "landing_smoothness": (0.5, 1.0),
            "approach_torso_lean": (-30, 30),
            "approach_direction_change": (0, 90),
            "toe_assist_proxy": (0.5, 1.0),
            "hard_landing": (0.5, 1.0),
            "goe_score": (5.0, 10.0),
        },
        isu_prefix="S",
    ),
    "loop": ElementDef(
        name="loop",
        name_ru="петля",
        rotations=1,
        has_toe_pick=False,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
        ],
        ideal_metrics={
            "airtime": (0.3, 0.6),
            "max_height": (0.15, 0.4),
            "landing_knee_angle": (80, 120),
            "rotation_speed": (300, 500),
            "landing_knee_stability": (0.5, 1.0),  # Knee stability after landing
            "landing_trunk_recovery": (0.5, 1.0),  # Trunk stays upright after landing
            "relative_jump_height": (0.3, 1.5),  # Height normalized by spine length
            "landing_com_velocity": (-2.0, 0.0),
            "landing_smoothness": (0.5, 1.0),
            "approach_torso_lean": (-30, 30),
            "approach_direction_change": (0, 90),
            "toe_assist_proxy": (0.5, 1.0),
            "hard_landing": (0.5, 1.0),
            "goe_score": (5.0, 10.0),
        },
        isu_prefix="Lo",
    ),
    "lutz": ElementDef(
        name="lutz",
        name_ru="льютц",
        rotations=1,
        has_toe_pick=True,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
        ],
        ideal_metrics={
            "airtime": (0.35, 0.6),
            "max_height": (0.15, 0.4),
            "landing_knee_angle": (90, 130),
            "pick_quality": (0.7, 1.0),
            "rotation_speed": (350, 550),
            "landing_knee_stability": (0.5, 1.0),  # Knee stability after landing
            "landing_trunk_recovery": (0.5, 1.0),  # Trunk stays upright after landing
            "relative_jump_height": (0.3, 1.5),  # Height normalized by spine length
            "landing_com_velocity": (-2.0, 0.0),
            "landing_smoothness": (0.5, 1.0),
            "approach_torso_lean": (-30, -5),
            "approach_direction_change": (20, 90),
            "toe_assist_proxy": (0.5, 1.0),
            "hard_landing": (0.5, 1.0),
            "goe_score": (5.0, 10.0),
        },
        isu_prefix="Lz",
    ),
    "axel": ElementDef(
        name="axel",
        name_ru="аксель",
        rotations=1.5,
        has_toe_pick=False,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
        ],
        ideal_metrics={
            "airtime": (0.4, 0.7),
            "max_height": (0.2, 0.5),
            "landing_knee_angle": (90, 130),
            "rotation_speed": (350, 550),
            "takeoff_angle": (65, 85),
            "landing_knee_stability": (0.5, 1.0),  # Knee stability after landing
            "landing_trunk_recovery": (0.5, 1.0),  # Trunk stays upright after landing
            "relative_jump_height": (0.3, 1.5),  # Height normalized by spine length
            "landing_com_velocity": (-2.0, 0.0),
            "landing_smoothness": (0.5, 1.0),
            "approach_torso_lean": (-30, 30),
            "approach_direction_change": (0, 90),
            "toe_assist_proxy": (0.5, 1.0),
            "hard_landing": (0.5, 1.0),
            "goe_score": (5.0, 10.0),
        },
        isu_prefix="A",
    ),
    # Spin elements — rotations=0, classified by spin detection
    "upright_spin": ElementDef(
        name="upright_spin",
        name_ru="Вертикальное вращение",
        rotations=0,
        has_toe_pick=False,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
        ],
        ideal_metrics={
            "spin_type": (0.5, 1.0),
            "spin_peak_velocity": (300, 600),
            "total_rotation_deg": (360, 1440),
            "rotation_count": (1.0, 4.0),
            "symmetry": (0.6, 1.0),
        },
        isu_prefix="USp",
    ),
    "one_foot_spin": ElementDef(
        name="one_foot_spin",
        name_ru="Вращение на одной ноге",
        rotations=0,
        has_toe_pick=False,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
        ],
        ideal_metrics={
            "spin_type": (0.5, 1.0),
            "spin_peak_velocity": (300, 600),
            "total_rotation_deg": (360, 1440),
            "rotation_count": (1.0, 4.0),
            "symmetry": (0.6, 1.0),
        },
        isu_prefix="CSp",
    ),
    "scratch_spin": ElementDef(
        name="scratch_spin",
        name_ru="Скрестное вращение",
        rotations=0,
        has_toe_pick=False,
        key_joints=[
            H36Key.LHIP,
            H36Key.RHIP,
            H36Key.LKNEE,
            H36Key.RKNEE,
            H36Key.LFOOT,
            H36Key.RFOOT,
            H36Key.LSHOULDER,
            H36Key.RSHOULDER,
        ],
        ideal_metrics={
            "spin_type": (0.5, 1.0),
            "spin_peak_velocity": (300, 600),
            "total_rotation_deg": (360, 1440),
            "rotation_count": (1.0, 4.0),
            "symmetry": (0.6, 1.0),
        },
        isu_prefix="LSp",
    ),
}


# ISU code → ELEMENT_DEFS slug mapping.
# Covers jumps (1..4 rotations), spins, and step sequences.
# Euler (1Eu) is omitted — no ElementDef exists for it.
ISU_CODE_TO_SLUG: dict[str, str] = {
    # Jumps — Axel family (single axel = 1A maps to axel, not waltz_jump)
    "1A": "axel",
    "2A": "axel",
    "3A": "axel",
    "4A": "axel",
    # Jumps — Toe loop family
    "1T": "toe_loop",
    "2T": "toe_loop",
    "3T": "toe_loop",
    "4T": "toe_loop",
    # Jumps — Salchow family
    "1S": "salchow",
    "2S": "salchow",
    "3S": "salchow",
    "4S": "salchow",
    # Jumps — Loop family
    "1Lo": "loop",
    "2Lo": "loop",
    "3Lo": "loop",
    "4Lo": "loop",
    # Jumps — Flip family
    "1F": "flip",
    "2F": "flip",
    "3F": "flip",
    "4F": "flip",
    # Jumps — Lutz family
    "1Lz": "lutz",
    "2Lz": "lutz",
    "3Lz": "lutz",
    "4Lz": "lutz",
    # Spins
    "1USp": "upright_spin",
    "2USp": "upright_spin",
    "3USp": "upright_spin",
    "4USp": "upright_spin",
    "1CSp": "one_foot_spin",
    "2CSp": "one_foot_spin",
    "3CSp": "one_foot_spin",
    "4CSp": "one_foot_spin",
    "1LSp": "scratch_spin",
    "2LSp": "scratch_spin",
    "3LSp": "scratch_spin",
    "4LSp": "scratch_spin",
    # Flying / Camel spins — no exact match; map to scratch_spin for generic spin analysis
    "1FSp": "scratch_spin",
    "2FSp": "scratch_spin",
    "3FSp": "scratch_spin",
    "4FSp": "scratch_spin",
    "1CSpB": "scratch_spin",
    "2CSpB": "scratch_spin",
    "3CSpB": "scratch_spin",
    "4CSpB": "scratch_spin",
    # Step sequences
    "StSq1": "three_turn",
    "StSq2": "three_turn",
    "StSq3": "three_turn",
    "StSq4": "three_turn",
}


def get_element_def(element_type: str) -> ElementDef | None:
    """Get element definition by type.

    Accepts both legacy slugs (e.g. 'axel') and ISU codes (e.g. '3A').

    Args:
        element_type: Element identifier (e.g., 'three_turn', '3A').

    Returns:
        ElementDef or None if not found.
    """
    if element_type in ELEMENT_DEFS:
        return ELEMENT_DEFS[element_type]
    slug = ISU_CODE_TO_SLUG.get(element_type)
    return ELEMENT_DEFS.get(slug) if slug else None


@dataclass(frozen=True)
class SpinDef:
    """Definition of a figure skating spin type.

    Attributes:
        name: Spin identifier (e.g., 'upright_spin').
        name_ru: Russian name for display.
        min_duration_s: Minimum spin duration in seconds.
        hip_y_range_max: Max hip vertical displacement (normalized).
    """

    name: str
    name_ru: str
    min_duration_s: float
    hip_y_range_max: float


SPIN_TYPES: dict[str, SpinDef] = {
    "upright_spin": SpinDef(
        name="upright_spin",
        name_ru="Вертикальное вращение",
        min_duration_s=1.0,
        hip_y_range_max=0.1,
    ),
    "one_foot_spin": SpinDef(
        name="one_foot_spin",
        name_ru="Вращение на одной ноге",
        min_duration_s=1.0,
        hip_y_range_max=0.15,
    ),
    "scratch_spin": SpinDef(
        name="scratch_spin",
        name_ru="Скрестное вращение",
        min_duration_s=1.5,
        hip_y_range_max=0.2,
    ),
}


SPIN_TYPE_NAMES: set[str] = {s.name for s in SPIN_TYPES.values()}


def list_supported_elements() -> list[str]:
    """List all supported element types.

    Returns:
        List of element type identifiers.
    """
    return list(ELEMENT_DEFS.keys())


def is_jump(element_type: str) -> bool:
    """Check if element is a jump.

    Args:
        element_type: Element identifier.

    Returns:
        True if element has takeoff/flight phases.
    """
    element_def = get_element_def(element_type)
    return element_def.rotations > 0 if element_def else False


def is_spin(element_type: str) -> bool:
    """Check if element is a spin.

    Args:
        element_type: Element identifier.

    Returns:
        True if element is a spin type.
    """
    return element_type in SPIN_TYPE_NAMES


def get_isu_codes_for_element(element_type: str) -> list[str]:
    """Get available ISU codes for an element type from SOV data.

    Looks up the element's isu_prefix in the ISU Scale of Values JSON data
    and returns all matching codes (e.g., for toe_loop with prefix 'T',
    returns ['1T', '2T', '3T', '4T']).

    Args:
        element_type: Element identifier (e.g., 'toe_loop').

    Returns:
        Sorted list of matching ISU codes. Empty list if element not found,
        has no prefix, or SOV data file missing.
    """
    import json
    from pathlib import Path

    defn = get_element_def(element_type)
    if not defn or not defn.isu_prefix:
        return []
    sov_path = Path(__file__).parent.parent.parent.parent / "data" / "isu" / "sov_2025_26.json"
    if not sov_path.exists():
        return []
    with sov_path.open() as f:
        sov = json.load(f)
    prefix = defn.isu_prefix
    return sorted(
        code
        for section in ("jumps", "spins", "step_sequences", "choreo_sequences")
        for code in sov.get(section, {})
        if code.endswith(prefix) or code.startswith(prefix)
    )
