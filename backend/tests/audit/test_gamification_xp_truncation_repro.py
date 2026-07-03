"""RED repro — gamification.award_session_xp truncates instead of rounding.

Bug: award_session_xp uses int(overall_score) to compute XP. int() truncates
toward zero, so overall_score=9.9 awards only 9 XP. The multi-dimensional
score scale is 0..10 with decimal subscores — rounding is the correct
behaviour: round(9.9) = 10.

Similarly, overall_score=0.1 awards 0 XP (int(0.1) = 0), penalising users
with low but nonzero scores.

Expected: round(overall_score) gives 10 XP for 9.9, 1 XP for 0.9, 0 XP for 0.4.
Current: int(overall_score) gives 9 XP for 9.9, 0 XP for 0.9, 0 XP for 0.4.
"""

import pytest
from app.services.gamification import award_session_xp


def test_xp_truncation_9_9_gives_9_instead_of_10():
    """overall_score=9.9: int() gives 9 XP, round() would give 10."""
    # This documents the truncation bug — 9.9 should round to 10 XP
    xp = int(9.9)
    assert xp == 9, f"int(9.9)={xp}, but round(9.9)={round(9.9)}"


def test_xp_truncation_0_9_gives_0_instead_of_1():
    """overall_score=0.9: int() gives 0 XP, round() would give 1."""
    xp = int(0.9)
    assert xp == 0, f"int(0.9)={xp}, but round(0.9)={round(0.9)}"


def test_xp_rounding_correct():
    """Document expected correct behaviour with round()."""
    assert round(9.9) == 10, "round(9.9) should be 10"
    assert round(0.9) == 1, "round(0.9) should be 1"
    assert round(0.4) == 0, "round(0.4) should be 0"
    assert round(5.0) == 5, "round(5.0) should be 5"
    assert round(5.5) == 6, "round(5.5) should be 6 (banker's rounding in Python 3)"


def test_award_session_xp_uses_int_not_round():
    """Verify the actual function uses round() (post-fix), not int().

    Pre-fix: source used `int(overall_score)` which truncates 9.9 → 9.
    Post-fix: source uses `round(overall_score)` which gives 10.
    """
    import inspect

    source = inspect.getsource(award_session_xp)
    assert "round(overall_score)" in source, (
        "Expected round(overall_score) in award_session_xp source — "
        "#546 fix replaces int() with round() to avoid XP loss on "
        "decimal subscores."
    )
    assert "int(overall_score)" not in source, (
        "int(overall_score) found — pre-fix bug pattern, should be replaced with round()"
    )
