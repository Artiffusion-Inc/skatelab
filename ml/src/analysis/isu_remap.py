"""Remap ML TAS coarse output + phase_detector rotations to canonical ISU code.

ML is NOT retrained (decision: remap layer, not retraining). The TAS classifier
emits a jump type slug; phase_detector counts rotations. This composes the ISU
code via the shared ML_TYPE_TO_FAMILY map (mirrors backend elements_db.aliases).
"""

from __future__ import annotations

# Must stay in sync with backend/app/services/choreography/elements_db.py ML_TYPE_TO_FAMILY.
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


def remap_to_isu(tas_type: str, rotations: int) -> str | None:
    family = ML_TYPE_TO_FAMILY.get(tas_type)
    if family is None:
        return None
    if family == "1A":  # waltz_jump — fixed single axel code
        return "1A"
    if not 1 <= rotations <= 4:
        return None
    return f"{rotations}{family}"
