"""Tests for ElementDef float rotations and is_jump behavior."""

import pytest

from src.analysis.element_defs import ELEMENT_DEFS, is_jump


class TestAxelRotations:
    """Axel rotations must be float (1.5, 2.5, 3.5), not truncated."""

    def test_axel_rotations_is_float_1_5(self):
        assert ELEMENT_DEFS["axel"].rotations == 1.5

    def test_axel_is_jump(self):
        assert is_jump("axel") is True

    def test_single_jump_rotations_is_float(self):
        for name in ("toe_loop", "flip", "salchow", "loop", "lutz"):
            assert ELEMENT_DEFS[name].rotations == 1.0

    def test_spin_rotations_zero(self):
        for name in ("upright_spin", "one_foot_spin", "scratch_spin"):
            assert ELEMENT_DEFS[name].rotations == 0.0

    def test_three_turn_rotations_zero(self):
        assert ELEMENT_DEFS["three_turn"].rotations == 0.0

    def test_is_jump_false_for_spins(self):
        assert is_jump("upright_spin") is False

    def test_is_jump_true_for_jumps(self):
        assert is_jump("axel") is True
        assert is_jump("toe_loop") is True


class TestUnderRotation:
    """compute_under_rotation must use rotations directly, no +0.5 hack."""

    def test_axel_under_rotation_uses_540_target(self):
        """Axel target = 1.5 * 360 = 540 degrees."""
        from src.analysis.metrics import compute_under_rotation

        result = compute_under_rotation(540.0, ELEMENT_DEFS["axel"].rotations)
        assert result == pytest.approx(0.0, abs=0.1)

    def test_single_jump_under_rotation_uses_360_target(self):
        from src.analysis.metrics import compute_under_rotation

        result = compute_under_rotation(360.0, ELEMENT_DEFS["toe_loop"].rotations)
        assert result == pytest.approx(0.0, abs=0.1)

    def test_under_rotation_detects_under_rotation(self):
        from src.analysis.metrics import compute_under_rotation

        # 450 degrees actual vs 540 degrees target for axel = 90 degrees under-rotated
        result = compute_under_rotation(450.0, ELEMENT_DEFS["axel"].rotations)
        assert result == pytest.approx(90.0, abs=0.1)
