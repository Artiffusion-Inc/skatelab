"""Tests for ISU remap: (tas_type, rotations) -> ISU code."""

from src.analysis.isu_remap import remap_to_isu


def test_jump_type_and_rotations_compose_code():
    assert remap_to_isu("axel", 3) == "3A"
    assert remap_to_isu("toe_loop", 1) == "1T"
    assert remap_to_isu("lutz", 4) == "4Lz"


def test_waltz_jump_is_single_axel():
    assert remap_to_isu("waltz_jump", 1) == "1A"  # rotations ignored for waltz


def test_unknown_type_returns_none():
    assert remap_to_isu("unknown_thing", 3) is None


def test_invalid_rotations_returns_none():
    assert remap_to_isu("axel", 0) is None  # can't have 0-rotation jump
    assert remap_to_isu("axel", 5) is None
