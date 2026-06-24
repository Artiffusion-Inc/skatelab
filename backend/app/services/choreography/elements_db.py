"""ISU element registry — static database of all elements with properties.

Data source: ISU Communication 2707 (2025/26 season).
Singles only (Men + Women), Short Program + Free Skate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ElementType(StrEnum):
    JUMP = "jump"
    SPIN = "spin"
    STEP_SEQUENCE = "step_sequence"
    CHOREO_SEQUENCE = "choreo_sequence"


@dataclass(frozen=True)
class ElementDef:
    code: str
    name: str
    type: ElementType
    base_value: float
    rotations: float = 0.0
    has_toe_pick: bool = False
    entry_edge: str = ""
    exit_edge: str = ""
    combo_eligible: bool = False
    short_program_eligible: bool = True
    name_ru: str = ""
    name_en: str = ""
    family: str = ""
    aliases: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Static element database
# ---------------------------------------------------------------------------

ELEMENTS: dict[str, ElementDef] = {
    # --- Jumps (ISU 2025/26 BV) ---
    # Single jumps
    "1T": ElementDef(
        "1T",
        "Single Toe Loop",
        ElementType.JUMP,
        0.40,
        1.0,
        True,
        "",
        "RBO",
        False,
        name_ru="Одинарный Тулуп",
        name_en="Single Toe Loop",
        family="T",
        aliases=("toe_loop",),
    ),
    "1S": ElementDef(
        "1S",
        "Single Salchow",
        ElementType.JUMP,
        0.40,
        1.0,
        False,
        "",
        "RBO",
        False,
        name_ru="Одинарный Сальхов",
        name_en="Single Salchow",
        family="S",
        aliases=("salchow",),
    ),
    "1Lo": ElementDef(
        "1Lo",
        "Single Loop",
        ElementType.JUMP,
        0.50,
        1.0,
        False,
        "",
        "RBO",
        False,
        name_ru="Одинарный Риттбергер",
        name_en="Single Loop",
        family="Lo",
        aliases=("loop",),
    ),
    "1F": ElementDef(
        "1F",
        "Single Flip",
        ElementType.JUMP,
        0.50,
        1.0,
        True,
        "",
        "RBO",
        False,
        name_ru="Одинарный Флип",
        name_en="Single Flip",
        family="F",
        aliases=("flip",),
    ),
    "1Lz": ElementDef(
        "1Lz",
        "Single Lutz",
        ElementType.JUMP,
        0.60,
        1.0,
        True,
        "",
        "RBO",
        False,
        name_ru="Одинарный Лутц",
        name_en="Single Lutz",
        family="Lz",
        aliases=("lutz",),
    ),
    "1A": ElementDef(
        "1A",
        "Single Axel",
        ElementType.JUMP,
        1.10,
        1.5,
        False,
        "",
        "RBO",
        False,
        name_ru="Одинарный Аксель",
        name_en="Single Axel",
        family="A",
        aliases=("axel", "waltz_jump"),
    ),
    # Double jumps
    "2T": ElementDef(
        "2T",
        "Double Toe Loop",
        ElementType.JUMP,
        1.30,
        2.0,
        True,
        "",
        "RBO",
        True,
        name_ru="Двойной Тулуп",
        name_en="Double Toe Loop",
        family="T",
        aliases=("toe_loop",),
    ),
    "2S": ElementDef(
        "2S",
        "Double Salchow",
        ElementType.JUMP,
        1.30,
        2.0,
        False,
        "",
        "RBO",
        True,
        name_ru="Двойной Сальхов",
        name_en="Double Salchow",
        family="S",
        aliases=("salchow",),
    ),
    "2Lo": ElementDef(
        "2Lo",
        "Double Loop",
        ElementType.JUMP,
        1.70,
        2.0,
        False,
        "",
        "RBO",
        True,
        name_ru="Двойной Риттбергер",
        name_en="Double Loop",
        family="Lo",
        aliases=("loop",),
    ),
    "2F": ElementDef(
        "2F",
        "Double Flip",
        ElementType.JUMP,
        1.80,
        2.0,
        True,
        "",
        "RBO",
        True,
        name_ru="Двойной Флип",
        name_en="Double Flip",
        family="F",
        aliases=("flip",),
    ),
    "2Lz": ElementDef(
        "2Lz",
        "Double Lutz",
        ElementType.JUMP,
        2.10,
        2.0,
        True,
        "",
        "RBO",
        True,
        name_ru="Двойной Лутц",
        name_en="Double Lutz",
        family="Lz",
        aliases=("lutz",),
    ),
    "2A": ElementDef(
        "2A",
        "Double Axel",
        ElementType.JUMP,
        3.30,
        2.5,
        False,
        "",
        "RBO",
        True,
        name_ru="Двойной Аксель",
        name_en="Double Axel",
        family="A",
        aliases=("axel",),
    ),
    # Triple jumps
    "3T": ElementDef(
        "3T",
        "Triple Toe Loop",
        ElementType.JUMP,
        4.20,
        3.0,
        True,
        "",
        "RBO",
        True,
        name_ru="Тройной Тулуп",
        name_en="Triple Toe Loop",
        family="T",
        aliases=("toe_loop",),
    ),
    "3S": ElementDef(
        "3S",
        "Triple Salchow",
        ElementType.JUMP,
        4.30,
        3.0,
        False,
        "",
        "RBO",
        True,
        name_ru="Тройной Сальхов",
        name_en="Triple Salchow",
        family="S",
        aliases=("salchow",),
    ),
    "3Lo": ElementDef(
        "3Lo",
        "Triple Loop",
        ElementType.JUMP,
        4.90,
        3.0,
        False,
        "",
        "RBO",
        True,
        name_ru="Тройной Риттбергер",
        name_en="Triple Loop",
        family="Lo",
        aliases=("loop",),
    ),
    "3F": ElementDef(
        "3F",
        "Triple Flip",
        ElementType.JUMP,
        5.30,
        3.0,
        True,
        "",
        "RBO",
        True,
        name_ru="Тройной Флип",
        name_en="Triple Flip",
        family="F",
        aliases=("flip",),
    ),
    "3Lz": ElementDef(
        "3Lz",
        "Triple Lutz",
        ElementType.JUMP,
        5.90,
        3.0,
        True,
        "",
        "RBO",
        True,
        name_ru="Тройной Лутц",
        name_en="Triple Lutz",
        family="Lz",
        aliases=("lutz",),
    ),
    "3A": ElementDef(
        "3A",
        "Triple Axel",
        ElementType.JUMP,
        8.00,
        3.5,
        False,
        "",
        "RBO",
        True,
        name_ru="Тройной Аксель",
        name_en="Triple Axel",
        family="A",
        aliases=("axel",),
    ),
    # Quad jumps (Men)
    "4T": ElementDef(
        "4T",
        "Quad Toe Loop",
        ElementType.JUMP,
        9.50,
        4.0,
        True,
        "",
        "RBO",
        True,
        name_ru="Четверной Тулуп",
        name_en="Quad Toe Loop",
        family="T",
        aliases=("toe_loop",),
    ),
    "4S": ElementDef(
        "4S",
        "Quad Salchow",
        ElementType.JUMP,
        9.70,
        4.0,
        False,
        "",
        "RBO",
        True,
        name_ru="Четверной Сальхов",
        name_en="Quad Salchow",
        family="S",
        aliases=("salchow",),
    ),
    "4Lo": ElementDef(
        "4Lo",
        "Quad Loop",
        ElementType.JUMP,
        10.50,
        4.0,
        False,
        "",
        "RBO",
        True,
        name_ru="Четверной Риттбергер",
        name_en="Quad Loop",
        family="Lo",
        aliases=("loop",),
    ),
    "4F": ElementDef(
        "4F",
        "Quad Flip",
        ElementType.JUMP,
        11.00,
        4.0,
        True,
        "",
        "RBO",
        True,
        name_ru="Четверной Флип",
        name_en="Quad Flip",
        family="F",
        aliases=("flip",),
    ),
    "4Lz": ElementDef(
        "4Lz",
        "Quad Lutz",
        ElementType.JUMP,
        11.50,
        4.0,
        True,
        "",
        "RBO",
        True,
        name_ru="Четверной Лутц",
        name_en="Quad Lutz",
        family="Lz",
        aliases=("lutz",),
    ),
    "4A": ElementDef(
        "4A",
        "Quad Axel",
        ElementType.JUMP,
        12.50,
        4.5,
        False,
        "",
        "RBO",
        True,
        name_ru="Четверной Аксель",
        name_en="Quad Axel",
        family="A",
        aliases=("axel",),
    ),
    # Half jumps (used in combinations)
    "1Eu": ElementDef(
        "1Eu",
        "Euler (half-loop)",
        ElementType.JUMP,
        0.50,
        0.5,
        False,
        "",
        "RBO",
        True,
        name_ru="Эйлер (перекидной)",
        name_en="Euler (half-loop)",
        family="Eu",
        aliases=("euler", "half_loop"),
    ),
    # --- Spins (ISU 2025/26 BV) ---
    # Combination spins
    "CSp1": ElementDef(
        "CSp1",
        "Change Foot Combination Spin Lv1",
        ElementType.SPIN,
        1.50,
        name_ru="Вращение со сменой ноги (комб.) ур.1",
        name_en="Change Foot Combination Spin Lv1",
        family="CSp",
    ),
    "CSp2": ElementDef(
        "CSp2",
        "Change Foot Combination Spin Lv2",
        ElementType.SPIN,
        2.00,
        name_ru="Вращение со сменой ноги (комб.) ур.2",
        name_en="Change Foot Combination Spin Lv2",
        family="CSp",
    ),
    "CSp3": ElementDef(
        "CSp3",
        "Change Foot Combination Spin Lv3",
        ElementType.SPIN,
        2.50,
        name_ru="Вращение со сменой ноги (комб.) ур.3",
        name_en="Change Foot Combination Spin Lv3",
        family="CSp",
    ),
    "CSp4": ElementDef(
        "CSp4",
        "Change Foot Combination Spin Lv4",
        ElementType.SPIN,
        3.20,
        name_ru="Вращение со сменой ноги (комб.) ур.4",
        name_en="Change Foot Combination Spin Lv4",
        family="CSp",
    ),
    # Flying spins
    "FSp1": ElementDef(
        "FSp1",
        "Flying Change Foot Spin Lv1",
        ElementType.SPIN,
        1.70,
        name_ru="Вращение с перелётом (комб.) ур.1",
        name_en="Flying Change Foot Spin Lv1",
        family="FSp",
    ),
    "FSp2": ElementDef(
        "FSp2",
        "Flying Change Foot Spin Lv2",
        ElementType.SPIN,
        2.30,
        name_ru="Вращение с перелётом (комб.) ур.2",
        name_en="Flying Change Foot Spin Lv2",
        family="FSp",
    ),
    "FSp3": ElementDef(
        "FSp3",
        "Flying Change Foot Spin Lv3",
        ElementType.SPIN,
        2.80,
        name_ru="Вращение с перелётом (комб.) ур.3",
        name_en="Flying Change Foot Spin Lv3",
        family="FSp",
    ),
    "FSp4": ElementDef(
        "FSp4",
        "Flying Change Foot Spin Lv4",
        ElementType.SPIN,
        3.00,
        name_ru="Вращение с перелётом (комб.) ур.4",
        name_en="Flying Change Foot Spin Lv4",
        family="FSp",
    ),
    # Layback spins (Women) / Single position spins
    "LSp1": ElementDef(
        "LSp1",
        "Layback Spin Lv1",
        ElementType.SPIN,
        1.50,
        name_ru="Либелла ур.1",
        name_en="Layback Spin Lv1",
        family="LSp",
    ),
    "LSp2": ElementDef(
        "LSp2",
        "Layback Spin Lv2",
        ElementType.SPIN,
        2.00,
        name_ru="Либелла ур.2",
        name_en="Layback Spin Lv2",
        family="LSp",
    ),
    "LSp3": ElementDef(
        "LSp3",
        "Layback Spin Lv3",
        ElementType.SPIN,
        2.50,
        name_ru="Либелла ур.3",
        name_en="Layback Spin Lv3",
        family="LSp",
    ),
    "LSp4": ElementDef(
        "LSp4",
        "Layback Spin Lv4",
        ElementType.SPIN,
        3.00,
        name_ru="Либелла ур.4",
        name_en="Layback Spin Lv4",
        family="LSp",
    ),
    # Spin in one position (Men)
    "USp1": ElementDef(
        "USp1",
        "Upright Spin Lv1",
        ElementType.SPIN,
        1.50,
        name_ru="Вращение (стоя) ур.1",
        name_en="Upright Spin Lv1",
        family="USp",
    ),
    "USp2": ElementDef(
        "USp2",
        "Upright Spin Lv2",
        ElementType.SPIN,
        2.00,
        name_ru="Вращение (стоя) ур.2",
        name_en="Upright Spin Lv2",
        family="USp",
    ),
    "USp3": ElementDef(
        "USp3",
        "Upright Spin Lv3",
        ElementType.SPIN,
        2.50,
        name_ru="Вращение (стоя) ур.3",
        name_en="Upright Spin Lv3",
        family="USp",
    ),
    "USp4": ElementDef(
        "USp4",
        "Upright Spin Lv4",
        ElementType.SPIN,
        3.00,
        name_ru="Вращение (стоя) ур.4",
        name_en="Upright Spin Lv4",
        family="USp",
    ),
    # Camel spins
    "CSpB1": ElementDef(
        "CSpB1",
        "Camel Spin Lv1",
        ElementType.SPIN,
        1.70,
        name_ru="Вращение (ласточка) ур.1",
        name_en="Camel Spin Lv1",
        family="CSpB",
    ),
    "CSpB2": ElementDef(
        "CSpB2",
        "Camel Spin Lv2",
        ElementType.SPIN,
        2.30,
        name_ru="Вращение (ласточка) ур.2",
        name_en="Camel Spin Lv2",
        family="CSpB",
    ),
    "CSpB3": ElementDef(
        "CSpB3",
        "Camel Spin Lv3",
        ElementType.SPIN,
        2.80,
        name_ru="Вращение (ласточка) ур.3",
        name_en="Camel Spin Lv3",
        family="CSpB",
    ),
    "CSpB4": ElementDef(
        "CSpB4",
        "Camel Spin Lv4",
        ElementType.SPIN,
        3.00,
        name_ru="Вращение (ласточка) ур.4",
        name_en="Camel Spin Lv4",
        family="CSpB",
    ),
    # Step sequences
    "StSq1": ElementDef(
        "StSq1",
        "Step Sequence Lv1",
        ElementType.STEP_SEQUENCE,
        1.50,
        name_ru="Дорожка шагов ур.1",
        name_en="Step Sequence Lv1",
        family="StSq",
    ),
    "StSq2": ElementDef(
        "StSq2",
        "Step Sequence Lv2",
        ElementType.STEP_SEQUENCE,
        2.60,
        name_ru="Дорожка шагов ур.2",
        name_en="Step Sequence Lv2",
        family="StSq",
    ),
    "StSq3": ElementDef(
        "StSq3",
        "Step Sequence Lv3",
        ElementType.STEP_SEQUENCE,
        3.30,
        name_ru="Дорожка шагов ур.3",
        name_en="Step Sequence Lv3",
        family="StSq",
    ),
    "StSq4": ElementDef(
        "StSq4",
        "Step Sequence Lv4",
        ElementType.STEP_SEQUENCE,
        3.90,
        name_ru="Дорожка шагов ур.4",
        name_en="Step Sequence Lv4",
        family="StSq",
    ),
    # Choreographic sequence
    "ChSq1": ElementDef(
        "ChSq1",
        "Choreographic Sequence",
        ElementType.CHOREO_SEQUENCE,
        3.00,
        name_ru="Хореографическая дорожка",
        name_en="Choreographic Sequence",
        family="ChSq1",
    ),
}


def get_element(code: str) -> ElementDef | None:
    return ELEMENTS.get(code)


def get_elements_by_type(element_type: ElementType) -> list[ElementDef]:
    return [el for el in ELEMENTS.values() if el.type == element_type]


def get_jumps() -> list[ElementDef]:
    return get_elements_by_type(ElementType.JUMP)


def get_spins() -> list[ElementDef]:
    return get_elements_by_type(ElementType.SPIN)


# ---------------------------------------------------------------------------
# ML / TAS vocabulary mapping
# ---------------------------------------------------------------------------

# Maps ML/TAS slug element names to ISU jump family codes. "waltz_jump" is a
# single Axel (fixed 1A code, not a rotation-composable family) — encoded as
# the literal code "1A" so family_to_isu returns it directly.
ML_TYPE_TO_FAMILY: dict[str, str] = {
    "axel": "A",
    "toe_loop": "T",
    "salchow": "S",
    "loop": "Lo",
    "flip": "F",
    "lutz": "Lz",
    "waltz_jump": "1A",
    "euler": "Eu",
    "half_loop": "Eu",
}


def family_to_isu(family: str, rotations: int) -> str | None:
    """Compose an ISU element code from a jump family and rotation count.

    Returns None for invalid rotation counts (outside 1..4). "1A" is a fixed
    waltz-jump alias and is returned verbatim regardless of the rotation arg.
    """
    if family == "1A":  # waltz_jump alias — fixed code
        return "1A"
    return f"{rotations}{family}" if 1 <= rotations <= 4 else None
