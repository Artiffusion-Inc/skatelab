"""Tests for element_defs ISU code mapping."""

from src.analysis.element_defs import ELEMENT_DEFS, get_element_def, get_isu_codes_for_element


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
