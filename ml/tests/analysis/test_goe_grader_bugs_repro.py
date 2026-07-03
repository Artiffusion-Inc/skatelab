"""RED repro — GOE grader bugs from audit (tranche G-3).

Bug #5: goe_grader.py:196 `case "<<" | "e" | "!": return clean_bv` returns
  unchanged base_value for downgraded / wrong-edge / unclear-edge jumps,
  with comment "Downgraded/e/! need external BV lookup". This means
  `estimated_score = bv * (1 + grade * 0.10)` uses the FULL base value
  even when the element is downgraded — inflating the score.

ISU rule: a "<<" downgraded jump should be evaluated as the element with
FEWER rotations, AND the BV is reduced (typically ×0.7 for "<<"). Current
code uses the FULL BV.

Bug #6: goe_grader.py:81 `estimated_score = bv * (1 + grade * 0.10)` —
  formula documentation. Confirmed correct (grade ∈ [-5, 5], score ∈
  [0.5*bv, 1.5*bv]).

Bug #7: goe_grader.py:103-108 modifier logic for over-rotation.
  `shortfall = expected_rotations - actual`. If actual > expected
  (over-rotation), shortfall is NEGATIVE, so the `if 0 < shortfall`
  check correctly returns "" (no modifier). Confirmed correct — over-
  rotation does NOT trigger a modifier.

Bug #8: _is_fall hard_landing scale. hard_landing in [0,1] where 0.0 =
  very hard. fall_smoothness_max=0.05, fall_hard_landing_max=0.1.
  fall = smoothness < 0.05 AND hard_landing < 0.1.
  Confirmed: very-low smoothness AND very-low hard_landing (impact).
  Correct direction.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Bug #5: downgraded jumps get full BV (no reduction for "<<" / "e" / "!")
# ---------------------------------------------------------------------------


def test_downgraded_modifier_returns_full_base_value():
    """Bug #5a: modifier '<<' should reduce BV; pre-fix returned clean_bv.

    #560 fix: downgraded element gets clean_bv * 0.7 (per ISU rules).
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    # Triple axel (BV=8.0) intended as quad axel (BV=12.5), but actually
    # under-rotated. shortfall=1.5 ≥ 0.5 → modifier="<<".
    # ISU rule: downgraded element gets clean_bv * 0.7 multiplier.
    result = grader._adjusted_base_value(8.0, "<<")
    assert result == pytest.approx(5.6, abs=0.01), (
        f"Expected '<<' to apply 0.7 multiplier (8.0 * 0.7 = 5.6), got {result}. "
        f"Pre-fix: downgraded jumps got full base value."
    )


def test_compute_goe_grade_with_downgraded_inflates_score():
    """Bug #5b: full pipeline — downgraded jump yields estimated_score == full_bv.

    Triple axel attempted as quad: 2.5 actual rotations vs 3 expected.
    shortfall = 0.5 → modifier="<<".
    Grade = len(positives) = 0 (no other metrics provided) = 0.
    Estimated score = bv * (1 + 0 * 0.10) = bv = 8.0.

    ISU expectation: downgraded jumps should have REDUCED estimated_score
    because the element is "less than" what was attempted. Current code
    gives full credit.
    """
    from src.analysis.goe_grader import GOEGrader
    from src.types import MetricResult

    grader = GOEGrader()
    metrics = [
        MetricResult("airtime", 0.5, "s", True, (0.3, 0.6)),
        MetricResult("rotation_count", 2.5, "rot", True, (3, 4)),
    ]
    result = grader.compute_goe_grade(metrics, base_value=8.0, expected_rotations=3.0)

    assert result.modifier == "<<", f"Expected modifier='<<', got {result.modifier}"
    # #560 fix: downgraded jump with grade=0 should have estimated_score < 8.0
    # (ISU expects ~5.6 for '<<' on triple axel, with 0.7 multiplier).
    # With grade=0, estimated_score = bv * (1 + 0 * 0.10) = bv.
    # Post-fix: bv = 8.0 * 0.7 = 5.6, so estimated_score = 5.6.
    assert result.estimated_score == pytest.approx(5.6, abs=0.01), (
        f"Downgraded jump with grade=0 should have estimated_score ≈ 5.6 "
        f"(8.0 * 0.7), got {result.estimated_score}. "
        f"Pre-fix: 8.0 (full BV) — downgraded jumps were inflated."
    )


def test_e_modifier_returns_full_base_value():
    """Bug #5c: 'e' (wrong edge take-off) should reduce BV.

    #560 fix: 'e' applies 0.7 multiplier (same as '<<' — both are serious
    technical errors per ISU rules).
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    result = grader._adjusted_base_value(5.9, "e")
    assert result == pytest.approx(4.13, abs=0.01), (
        f"Expected 'e' to apply 0.7 multiplier (5.9 * 0.7 = 4.13), got {result}. "
        f"Pre-fix: 'e' returned 5.9 (full BV). Wrong-edge take-off is a "
        f"serious error; BV should be reduced."
    )


def test_exclamation_modifier_returns_full_base_value():
    """Bug #5d: '!' (unclear edge) should reduce BV.

    #560 fix: '!' applies 0.85 multiplier (less serious than 'e' but
    still penalized).
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    result = grader._adjusted_base_value(5.9, "!")
    assert result == pytest.approx(5.015, abs=0.01), (
        f"Expected '!' to apply 0.85 multiplier (5.9 * 0.85 = 5.015), "
        f"got {result}. Pre-fix: '!' returned 5.9 (full BV). "
        f"Unclear edge should still reduce BV (less than 'e' but still penalised)."
    )


# ---------------------------------------------------------------------------
# NOT-a-bug guards
# ---------------------------------------------------------------------------


def test_over_rotation_does_not_trigger_q_modifier():
    """NOT a bug: over-rotation (actual > expected) correctly returns no modifier.

    shortfall = expected - actual. If actual > expected, shortfall < 0.
    `0 < shortfall` is False, so no modifier is applied. Correct.
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    result = grader.detect_modifier(
        {"rotation_count": 3.5},  # over-rotated (3.5 vs 3 expected)
        expected_rotations=3.0,
    )
    assert result == "", f"Over-rotation should NOT trigger any modifier, got {result!r}"


def test_q_modifier_unchanged_bv():
    """NOT a bug: 'q' (slight under-rotation) keeps BV unchanged.

    ISU rule: 'q' is informational, BV is unchanged but grade is capped.
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    result = grader._adjusted_base_value(8.0, "q")
    assert result == 8.0, f"'q' modifier should keep BV unchanged, got {result}"


def test_single_under_modifier_80_percent_bv():
    """NOT a bug: '<' (under-rotated) reduces BV by 0.8 — this is correct.

    ISU rule: '<' reduces BV by 20% (multiplier 0.8). Current code matches.
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    result = grader._adjusted_base_value(8.0, "<")
    assert result == pytest.approx(6.4, abs=0.01), (
        f"'<' modifier should reduce BV by 0.8 (8.0 * 0.8 = 6.4), got {result}"
    )
