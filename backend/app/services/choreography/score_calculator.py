"""IJS score calculation: TES, GOE, back-half bonus.

GOE formula: score = base_value * (1 + grade * 0.10)
Each GOE step = +/-10% of base value (ISU standard).
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from app.config import settings
from app.services.choreography.isu_loader import ISULoader, SOVEntry

DATA_DIR = Path(settings.app.data_dir) / "isu"

_loader = ISULoader(data_dir=DATA_DIR, season="2025-26")
ELEMENTS: dict[str, SOVEntry] = _loader.load_sov()


def calculate_element_score(base_value: float, goe: int) -> float:
    """Calculate element score using ISU percentage formula.

    score = base_value * (1 + goe * 0.10)
    GOE range: -5 to +5.

    This replaces the old calculate_goe_total() which used incorrect
    "GOE factors" (0.5/0.7/1.0) that are actually PCS factors.
    """
    clamped = max(-5, min(5, goe))
    return base_value * (1 + clamped * 0.10)


def calculate_goe_total(base_value: float, goe: int) -> float:
    """DEPRECATED: Use calculate_element_score() instead.

    Kept for backward compatibility. Will be removed in next release.
    """
    return calculate_element_score(base_value, goe)


def goe_factor(base_value: float) -> float:
    """DEPRECATED: GOE factors (0.5/0.7/1.0) are NOT ISU GOE factors.

    These are PCS factors mistakenly used for GOE in previous versions.
    Kept for backward compatibility only.
    """
    if base_value < 2.0:
        return 0.5
    if base_value < 4.0:
        return 0.7
    return 1.0


def calculate_tes(
    elements: list[dict],
    back_half_indices: set[int] | frozenset[int],
) -> float:
    """Calculate Total Element Score.

    Args:
        elements: list of dicts with keys "code" and "goe".
        back_half_indices: set of element indices qualifying for back-half bonus (+10% BV).

    Returns:
        Sum of all element scores including back-half bonus.
    """
    total = 0.0
    for i, el in enumerate(elements):
        elem_def = ELEMENTS.get(el["code"])
        if elem_def is None:
            continue
        bv = elem_def.base_value
        if i in back_half_indices:
            bv *= 1.10  # back-half bonus
        total += calculate_element_score(bv, el["goe"])
    return total
