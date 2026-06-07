"""Tests for IJS score calculation."""

import pytest
from app.services.choreography.score_calculator import (
    calculate_element_score,
    calculate_goe_total,
    calculate_tes,
    goe_factor,
)

# --- calculate_element_score (correct ISU formula) ---


def test_calculate_element_score_clean_positive():
    """3T (BV=4.20) with GOE +3: 4.20 * (1 + 3*0.10) = 5.46"""
    score = calculate_element_score(4.20, 3)
    assert score == pytest.approx(5.46)


def test_calculate_element_score_negative():
    """3T (BV=4.20) with GOE -2: 4.20 * (1 + (-2)*0.10) = 3.36"""
    score = calculate_element_score(4.20, -2)
    assert score == pytest.approx(3.36)


def test_calculate_element_score_fall():
    """Fall: BV=4.20, GOE -5: 4.20 * (1 + (-5)*0.10) = 2.10"""
    score = calculate_element_score(4.20, -5)
    assert score == pytest.approx(2.10)


def test_calculate_element_score_zero():
    """GOE 0: BV unchanged."""
    score = calculate_element_score(4.20, 0)
    assert score == pytest.approx(4.20)


def test_calculate_element_score_plus5():
    """GOE +5: 4.20 * 1.50 = 6.30"""
    score = calculate_element_score(4.20, 5)
    assert score == pytest.approx(6.30)


def test_calculate_element_score_low_bv():
    """1T (BV=0.40) with GOE +5: 0.40 * 1.50 = 0.60"""
    score = calculate_element_score(0.40, 5)
    assert score == pytest.approx(0.60)


def test_calculate_element_score_clamps_goe():
    """GOE outside -5/+5 is clamped."""
    assert calculate_element_score(4.20, 10) == calculate_element_score(4.20, 5)
    assert calculate_element_score(4.20, -10) == calculate_element_score(4.20, -5)


# --- Deprecated functions (backward compat) ---


def test_goe_factor_low_bv():
    """BV < 2.0: factor = 0.5 (DEPRECATED but still works)"""
    assert goe_factor(1.50) == pytest.approx(0.5)


def test_goe_factor_mid_bv():
    """2.0 <= BV < 4.0: factor = 0.7 (DEPRECATED but still works)"""
    assert goe_factor(3.30) == pytest.approx(0.7)


def test_goe_factor_high_bv():
    """BV >= 4.0: factor = 1.0 (DEPRECATED but still works)"""
    assert goe_factor(5.90) == pytest.approx(1.0)


def test_calculate_goe_total_positive():
    """GOE +3 on 3Lz (BV 5.90): 5.90 * (1 + 3*0.10) = 7.67"""
    total = calculate_goe_total(5.90, 3)
    assert total == pytest.approx(7.67)


def test_calculate_goe_total_negative():
    """GOE -2 on 2A (BV 3.30): 3.30 * (1 + (-2)*0.10) = 2.64"""
    total = calculate_goe_total(3.30, -2)
    assert total == pytest.approx(2.64)


# --- TES calculation ---


def test_calculate_tes_basic():
    """Simple program with 3 elements, no back-half bonus."""
    elements = [
        {"code": "3Lz", "goe": 2},
        {"code": "CSp4", "goe": 1},
        {"code": "StSq4", "goe": 0},
    ]
    result = calculate_tes(elements, back_half_indices=set())
    # 3Lz: 5.90 * 1.20 = 7.08
    # CSp4: 3.20 * 1.10 = 3.52
    # StSq4: 3.90 * 1.00 = 3.90
    assert result == pytest.approx(14.50, abs=0.01)


def test_calculate_tes_with_back_half_bonus():
    """Back-half elements get +10% BV."""
    elements = [
        {"code": "3Lz", "goe": 2},
        {"code": "3F", "goe": 1},
        {"code": "3Lo", "goe": 0},
    ]
    result = calculate_tes(elements, back_half_indices={1, 2})
    # 3Lz: 5.90 * 1.20 = 7.08
    # 3F: (5.30 * 1.10) * 1.10 = 6.41
    # 3Lo: (4.90 * 1.10) * 1.00 = 5.39
    assert result == pytest.approx(18.88, abs=0.01)


def test_calculate_tes_empty():
    assert calculate_tes([], back_half_indices=set()) == 0.0
