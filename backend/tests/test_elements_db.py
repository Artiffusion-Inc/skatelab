from app.services.choreography.elements_db import (
    ELEMENTS,
    ML_TYPE_TO_FAMILY,
    family_to_isu,
    get_element,
)


def test_registry_has_localized_names_for_all():
    for code, el in ELEMENTS.items():
        assert el.name_ru, f"{code} missing name_ru"
        assert el.name_en, f"{code} missing name_en"
        assert el.family, f"{code} missing family"


def test_family_to_isu_composes_jump_code():
    assert family_to_isu("A", 3) == "3A"
    assert family_to_isu("T", 1) == "1T"
    assert family_to_isu("Eu", 1) == "1Eu"


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
