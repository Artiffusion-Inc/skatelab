"""Tests for ISU rules engine."""

from app.services.choreography.rules_engine import (
    validate_layout,
)


def _make_layout(elements, segment="free_skate"):
    """Helper: build layout dict from list of (code, goe, is_jump_pass) tuples."""
    layout_elements = []
    jump_pass_index = 0
    for code, goe, is_jump_pass in elements:
        entry = {"code": code, "goe": goe, "timestamp": 0.0}
        if is_jump_pass:
            entry["jump_pass_index"] = jump_pass_index
            jump_pass_index += 1
        layout_elements.append(entry)
    return {
        "discipline": "mens_singles",
        "segment": segment,
        "elements": layout_elements,
    }


def test_valid_free_skate_mens():
    """A well-balanced men's FS: 7 jump passes, 3 spins, 1 StSq, 1 ChSq."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3T", 1, False),  # combo part, not counted as separate pass
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("3Lz", 1, True),  # repeated, second time — must be in combo (it is: +2T below)
            ("2T", 0, False),  # combo part
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert result.is_valid
    assert len(result.errors) == 0


def test_zayak_violation_triple_repeated():
    """3Lz attempted 3 times → Zayak violation (max 2 for 3+ rotations)."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3Lz", 1, True),
            ("3Lz", 0, True),
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert not result.is_valid
    assert any("Zayak" in e for e in result.errors)


def test_zayak_second_repeat_not_in_combo():
    """3Lz attempted twice but neither in a combination → Zayak violation."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3F", 1, True),
            ("3Lz", 1, True),  # second 3Lz as standalone pass
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert any("combination" in e.lower() or "combo" in e.lower() for e in result.errors)


def test_too_many_jump_passes():
    """8 jump passes in FS → capacity violation (max 7)."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("3Lz", 1, True),
            ("3T", 0, True),
            ("2A", 0, True),  # 8th pass
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert not result.is_valid
    assert any("7" in e and "jump" in e.lower() for e in result.errors)


def test_missing_step_sequence():
    """No StSq → well-balanced program violation."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("3Lz", 1, True),
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert any("step sequence" in e.lower() or "StSq" in e for e in result.errors)


def test_missing_choreo_sequence():
    """No ChSq → well-balanced program violation."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("3Lz", 1, True),
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert any("choreographic" in e.lower() or "ChSq" in e for e in result.errors)


def test_too_many_spins():
    """4 spins → violation (max 3)."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("3Lz", 1, True),
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("USp4", 0, False),  # 4th spin
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert any("spin" in e.lower() and "3" in e for e in result.errors)


def test_warnings_empty():
    """Valid layout should have no warnings."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("3Lz", 1, True),
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert len(result.warnings) == 0


def test_no_axel_warning():
    """No Axel-type jump → warning (not error in MVP, but ISU requires it)."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("3S", 0, True),
            ("3T", 0, True),
            ("3Lz", 1, True),
            ("3T", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert any("axel" in w.lower() for w in result.warnings)


def test_too_many_combinations():
    """4 jump combos/sequences → violation (max 3)."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("2T", 0, False),  # combo
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("2Lo", 0, False),  # combo
            ("3S", 0, True),
            ("3T", 0, False),  # combo
            ("3Lz", 1, True),
            ("2T", 0, False),  # combo (4th)
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert not result.is_valid
    assert any("combination" in e.lower() and "3" in e for e in result.errors)


def test_too_many_triple_combos():
    """2 three-jump combos → violation (max 1)."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("2T", 0, False),
            ("2Lo", 0, False),  # triple combo 1
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("3Lz", 1, True),
            ("2T", 0, False),
            ("2Lo", 0, False),  # triple combo 2
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert not result.is_valid
    assert any("three-jump" in e.lower() for e in result.errors)


def test_euler_max_once():
    """Euler (1Eu) used twice → violation."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("1Eu", 0, True),
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("3Lz", 1, True),
            ("1Eu", 0, True),  # second Euler
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert not result.is_valid
    assert any("euler" in e.lower() or "1Eu" in e for e in result.errors)


def test_duplicate_spin_types_warning():
    """Two spins of same family → warning."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("3Lz", 1, True),
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("CSp3", 0, False),  # duplicate combo spin
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="free_skate",
    )
    result = validate_layout(layout)
    assert any("duplicate" in w.lower() for w in result.warnings)


def test_short_program_too_many_spins():
    """SP allows max 2 spins."""
    layout = _make_layout(
        [
            ("3Lz", 2, True),
            ("3F", 1, True),
            ("3Lo", 0, True),
            ("2A", 1, True),
            ("3S", 0, True),
            ("3Lz", 1, True),
            ("2A", 0, True),
            ("CSp4", 1, False),
            ("FSp4", 0, False),
            ("LSp4", 1, False),
            ("StSq4", 0, False),
            ("ChSq1", 0, False),
        ],
        segment="short_program",
    )
    result = validate_layout(layout)
    assert not result.is_valid
    assert any("short program" in e.lower() and "2" in e for e in result.errors)
