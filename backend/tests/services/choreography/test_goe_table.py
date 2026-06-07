"""Tests for GOE scale table."""

from app.services.choreography.goe_table import ERROR_REDUCTIONS, GOE_SCALE, POSITIVE_BULLETS


class TestGOETable:
    def test_11_grades(self):
        assert len(GOE_SCALE) == 11

    def test_grade_range(self):
        assert -5 in GOE_SCALE
        assert 5 in GOE_SCALE

    def test_percentages(self):
        assert GOE_SCALE[-5].percentage == -50
        assert GOE_SCALE[0].percentage == 0
        assert GOE_SCALE[5].percentage == 50

    def test_6_positive_bullets(self):
        assert len(POSITIVE_BULLETS) == 6

    def test_bullets_1_3_required_for_plus4(self):
        required = [b for b in POSITIVE_BULLETS if b.required_for_plus4_plus5]
        assert len(required) == 3
        assert required[0].number == 1
        assert required[1].number == 2
        assert required[2].number == 3

    def test_error_reductions_loaded(self):
        assert len(ERROR_REDUCTIONS) >= 8
