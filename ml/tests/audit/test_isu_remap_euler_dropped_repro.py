"""RED repro — remap_to_isu drops Euler/half_loop (180° half-revolution).

ml/src/analysis/isu_remap.py:24-32
    def remap_to_isu(tas_type: str, rotations: int) -> str | None:
        family = ML_TYPE_TO_FAMILY.get(tas_type)
        if family is None:
            return None
        if family == "1A":  # waltz_jump — fixed single axel code
            return "1A"
        if not 1 <= rotations <= 4:
            return None
        return f"{rotations}{family}"

ML_TYPE_TO_FAMILY maps waltz_jump -> "1A" (special-cased, returns "1A"
regardless of rotations), euler -> "Eu", half_loop -> "Eu".

count_rotations (phase_detector.py:43) returns FULL turns only:
    ceil(total_radians / (2*pi) - 0.5)
A 180° half-revolution (waltz jump, euler, half loop) is 0.5 turns =>
ceil(0.5 - 0.5) == 0.

Asymmetric special-case:
  waltz_jump + rotations=0 => "1A"  (correct — whitelisted)
  euler      + rotations=0 => None  (BUG — not whitelisted, 1<=0<=4 fails)
  half_loop  + rotations=0 => None  (BUG — euler alias, same failure)

Prod reachability:
  - TAS classifier emits "euler" label (ml/src/tas/dataset.py:48).
  - count_rotations returns 0 for the 180° euler.
  - backend/app/worker.py:507-511 compose_isu_element_type("euler", 0)
    => None => `if isu_code is not None` SKIPS saving session_obj.element_type
    => gamification enqueue receives element_type=None
    => _category_for_element returns None => Euler element DROPPED from
       XP / skill-unlock. Data loss.
  - Existing test test_invalid_rotations_returns_none tests axel+0
    (correctly rejected) but masks the Euler asymmetry — two 180° jumps,
    waltz whitelisted, euler dropped.
"""

from src.analysis.isu_remap import remap_to_isu


def test_euler_half_rotation_not_dropped():
    # Euler is a 180° half-revolution jump (ISU "1Eu"), same as waltz_jump is
    # 180° ("1A"). count_rotations returns 0 for half-revolution (full turns
    # only), so rotations=0 is the prod input.
    result = remap_to_isu("euler", 0)
    assert result is not None, (
        "BUG: remap_to_isu drops Euler (180° half-revolution) -> None while "
        "waltz_jump (same 180°) -> '1A'. Euler element lost from "
        "session.element_type + gamification XP. Asymmetric special-case: "
        "waltz whitelisted, euler not."
    )
    assert result == "1Eu", f"Expected '1Eu' for Euler half-revolution, got {result}"


def test_half_loop_alias_not_dropped():
    # half_loop is an alias for euler (both map to family "Eu").
    result = remap_to_isu("half_loop", 0)
    assert result is not None, "BUG: half_loop (Euler alias) also dropped"
    assert result == "1Eu", f"Expected '1Eu' for half_loop alias, got {result}"


def test_waltz_still_works():
    # Control — waltz_jump special case must keep working.
    result = remap_to_isu("waltz_jump", 0)
    assert result == "1A", f"Expected '1A' for waltz_jump, got {result}"
