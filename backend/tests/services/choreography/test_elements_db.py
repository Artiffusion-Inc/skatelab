"""Tests for ISU element database."""

import pytest
from app.services.choreography.elements_db import (
    ELEMENTS,
    ML_TYPE_TO_FAMILY,
    ElementType,
    family_to_isu,
    get_element,
    get_elements_by_type,
    get_jumps,
    get_spins,
)


def test_get_triple_lutz():
    el = get_element("3Lz")
    assert el is not None
    assert el.code == "3Lz"
    assert el.name == "Triple Lutz"
    assert el.type == ElementType.JUMP
    assert el.rotations == 3.0
    assert el.has_toe_pick is True
    assert el.base_value == pytest.approx(5.90, abs=0.01)
    assert el.combo_eligible is True


def test_get_double_axel():
    el = get_element("2A")
    assert el is not None
    assert el.rotations == 2.5
    assert el.has_toe_pick is False


def test_get_spin():
    el = get_element("CSp4")
    assert el is not None
    assert el.type == ElementType.SPIN
    assert el.base_value == pytest.approx(3.20, abs=0.01)


def test_get_step_sequence():
    el = get_element("StSq4")
    assert el is not None
    assert el.type == ElementType.STEP_SEQUENCE


def test_get_choreo_sequence():
    el = get_element("ChSq1")
    assert el is not None
    assert el.type == ElementType.CHOREO_SEQUENCE
    assert el.base_value == pytest.approx(3.00, abs=0.01)


def test_get_element_not_found():
    assert get_element("9Zz") is None


def test_get_jumps_returns_only_jumps():
    jumps = get_jumps()
    assert len(jumps) > 0
    assert all(j.type == ElementType.JUMP for j in jumps)


def test_get_spins_returns_only_spins():
    spins = get_spins()
    assert len(spins) > 0
    assert all(s.type == ElementType.SPIN for s in spins)


def test_get_elements_by_type_step_sequence():
    elems = get_elements_by_type(ElementType.STEP_SEQUENCE)
    assert len(elems) > 0
    assert all(e.type == ElementType.STEP_SEQUENCE for e in elems)


def test_toe_pick_jumps():
    """Lutz, flip, toe loop have toe picks. Salchow, loop, axel do not."""
    assert get_element("3Lz").has_toe_pick is True
    assert get_element("3F").has_toe_pick is True
    assert get_element("3T").has_toe_pick is True
    assert get_element("3S").has_toe_pick is False
    assert get_element("3Lo").has_toe_pick is False
    assert get_element("3A").has_toe_pick is False


def test_combo_eligible():
    """All jumps with 2+ rotations are combo eligible."""
    assert get_element("3Lz").combo_eligible is True
    assert get_element("2A").combo_eligible is True
    assert get_element("1T").combo_eligible is False


def test_short_program_eligible():
    """Some spins/elements are allowed in SP, some only in FS."""
    # All jumps are SP-eligible
    assert get_element("3Lz").short_program_eligible is True
    # Step sequence and choreo sequence are SP-eligible
    assert get_element("StSq4").short_program_eligible is True
    assert get_element("ChSq1").short_program_eligible is True


def test_registry_has_localized_names_for_all():
    for code, el in ELEMENTS.items():
        assert el.name_ru, f"{code} missing name_ru"
        assert el.name_en, f"{code} missing name_en"
        assert el.family, f"{code} missing family"


def test_family_to_isu_composes_jump_code():
    assert family_to_isu("A", 3) == "3A"
    assert family_to_isu("T", 1) == "1T"
    assert family_to_isu("Eu", 1) == "1Eu"
    assert family_to_isu("1A", 0) == "1A"  # waltz = single axel, rotations ignored
    assert family_to_isu(ML_TYPE_TO_FAMILY["waltz_jump"], 3) == "1A"


def test_ml_type_to_family_covers_tas_vocabulary():
    for tas_type in [
        "axel",
        "toe_loop",
        "salchow",
        "loop",
        "flip",
        "lutz",
        "waltz_jump",
        "euler",
    ]:
        assert tas_type in ML_TYPE_TO_FAMILY, f"missing TAS type {tas_type}"
    assert ML_TYPE_TO_FAMILY["axel"] == "A"
    assert ML_TYPE_TO_FAMILY["toe_loop"] == "T"
    assert ML_TYPE_TO_FAMILY["waltz_jump"] == "1A"  # waltz = single axel
