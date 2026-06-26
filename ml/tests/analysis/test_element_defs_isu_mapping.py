"""Tests for element_defs ISU code mapping."""

import pytest

from src.analysis.element_defs import (
    ELEMENT_DEFS,
    ISU_CODE_TO_SLUG,
    get_element_def,
    get_isu_codes_for_element,
)


class TestElementDefISUPrefix:
    def test_all_jumps_have_isu_prefix(self):
        for name in ("waltz_jump", "toe_loop", "flip", "salchow", "loop", "lutz", "axel"):
            defn = get_element_def(name)
            assert defn is not None
            assert defn.isu_prefix != "", f"{name} missing isu_prefix"

    def test_three_turn_has_isu_prefix(self):
        defn = get_element_def("three_turn")
        assert defn.isu_prefix == "StSq"

    def test_toe_loop_prefix(self):
        defn = get_element_def("toe_loop")
        assert defn.isu_prefix == "T"

    def test_axel_prefix(self):
        defn = get_element_def("axel")
        assert defn.isu_prefix == "A"

    def test_get_isu_codes_for_toe_loop(self):
        codes = get_isu_codes_for_element("toe_loop")
        assert "1T" in codes
        assert "2T" in codes
        assert "3T" in codes
        assert "4T" in codes


class TestISUCodeResolution:
    """ISU codes forwarded from backend worker must resolve to ElementDefs (GPU seam)."""

    def test_isu_code_3a_resolves_to_axel(self):
        defn = get_element_def("3A")
        assert defn is not None
        assert defn.name == "axel"

    def test_isu_code_1a_resolves_to_axel_not_waltz(self):
        """Single axel (1A) maps to the axel ElementDef, not waltz_jump."""
        defn = get_element_def("1A")
        assert defn is not None
        assert defn.name == "axel"

    def test_isu_code_4t_resolves_to_toe_loop(self):
        defn = get_element_def("4T")
        assert defn is not None
        assert defn.name == "toe_loop"

    def test_isu_code_2s_resolves_to_salchow(self):
        defn = get_element_def("2S")
        assert defn is not None
        assert defn.name == "salchow"

    def test_isu_code_3lo_resolves_to_loop(self):
        defn = get_element_def("3Lo")
        assert defn is not None
        assert defn.name == "loop"

    def test_isu_code_1f_resolves_to_flip(self):
        defn = get_element_def("1F")
        assert defn is not None
        assert defn.name == "flip"

    def test_isu_code_4lz_resolves_to_lutz(self):
        defn = get_element_def("4Lz")
        assert defn is not None
        assert defn.name == "lutz"

    def test_legacy_slug_still_works(self):
        assert get_element_def("axel") is ELEMENT_DEFS["axel"]
        assert get_element_def("toe_loop") is ELEMENT_DEFS["toe_loop"]
        assert get_element_def("three_turn") is ELEMENT_DEFS["three_turn"]

    def test_euler_returns_none(self):
        """Euler has no ElementDef — must return None, not crash."""
        assert get_element_def("1Eu") is None

    def test_step_sequence_resolves_to_three_turn(self):
        for code in ("StSq1", "StSq2", "StSq3", "StSq4"):
            defn = get_element_def(code)
            assert defn is not None, f"{code} should resolve"
            assert defn.name == "three_turn"

    @pytest.mark.parametrize(
        "isu_code,expected_slug",
        [
            ("1USp", "upright_spin"),
            ("2USp", "upright_spin"),
            ("3USp", "upright_spin"),
            ("4USp", "upright_spin"),
            ("1CSp", "one_foot_spin"),
            ("2CSp", "one_foot_spin"),
            ("3CSp", "one_foot_spin"),
            ("4CSp", "one_foot_spin"),
            ("1LSp", "scratch_spin"),
            ("2LSp", "scratch_spin"),
            ("3LSp", "scratch_spin"),
            ("4LSp", "scratch_spin"),
            ("1FSp", "scratch_spin"),
            ("2FSp", "scratch_spin"),
            ("3FSp", "scratch_spin"),
            ("4FSp", "scratch_spin"),
            ("1CSpB", "scratch_spin"),
            ("2CSpB", "scratch_spin"),
            ("3CSpB", "scratch_spin"),
            ("4CSpB", "scratch_spin"),
        ],
    )
    def test_spin_isu_codes(self, isu_code: str, expected_slug: str):
        defn = get_element_def(isu_code)
        assert defn is not None, f"{isu_code} should resolve"
        assert defn.name == expected_slug

    def test_isu_code_to_slug_coverage(self):
        """Every entry in ISU_CODE_TO_SLUG resolves to an existing ElementDef."""
        for code, slug in ISU_CODE_TO_SLUG.items():
            assert slug in ELEMENT_DEFS, f"ISU_CODE_TO_SLUG['{code}'] -> missing slug '{slug}'"
            assert get_element_def(code) is ELEMENT_DEFS[slug]
