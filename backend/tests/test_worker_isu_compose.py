"""Tests for worker ISU composition and gamification category lookup."""

from __future__ import annotations

import pytest
from app.worker import _category_for_element, compose_isu_element_type


def test_worker_composes_isu_code_from_tas_and_rotations():
    # TAS says "axel", phase_detector says 3 -> session.element_type = "3A"
    code = compose_isu_element_type(tas_type="axel", rotations=3)
    assert code == "3A"


def test_worker_composes_isu_code_other_jumps():
    assert compose_isu_element_type("salchow", 2) == "2S"
    assert compose_isu_element_type("lutz", 4) == "4Lz"
    assert compose_isu_element_type("toe_loop", 1) == "1T"


def test_worker_unknown_tas_stores_none():
    assert compose_isu_element_type(tas_type="garbage", rotations=3) is None


def test_worker_none_rotations_stores_none():
    assert compose_isu_element_type(tas_type="axel", rotations=None) is None


def test_worker_none_tas_stores_none():
    assert compose_isu_element_type(tas_type=None, rotations=3) is None


def test_gamification_category_from_isu_code():
    assert _category_for_element("3A") == "jumps"
    assert _category_for_element("CSp4") == "spins"
    assert _category_for_element("StSq2") == "control"
    assert _category_for_element(None) is None


def test_gamification_category_unknown_code():
    assert _category_for_element("XYZ123") is None
