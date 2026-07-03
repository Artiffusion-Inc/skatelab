"""RED repro — recommender system bugs from audit (tranche G).

Bug #2: NaN metric value → _is_bad returns True (NaN comparison) →
  _determine_severity returns "default" → template.format(value=NaN) renders
  "nan" silently in Russian text (Python 3.11/3.12) or raises ValueError
  (Python 3.13+). Source: recommender.py:49, 55-60, 147-152.

Bug #3: Multiple rules in jump_rules.py have only "too_low" and "default"
  templates, missing "too_high". When a value is above the reference range,
  the "default" template (e.g., "Следи за высотой прыжка") is used — but
  the message doesn't acknowledge the value is TOO HIGH. Misleads users
  about which direction the error is.

Bug #4: recommend() returns [] silently for unknown element_type.
  A typo in element_type looks identical to "no problems detected".
  Source: recommender.py:40.

These tests document bugs as code-level assertions + a small smoke test
for the recommender's behaviour on NaN values.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Bug #2: NaN value reaches template.format() and silently corrupts Russian
# ---------------------------------------------------------------------------


def test_is_bad_returns_true_for_nan():
    """Bug #2a: _is_bad(NaN, ref_range) returns True (NaN comparisons fail)."""
    from ml.src.analysis.rules.jump_rules import _is_bad

    nan = float("nan")
    result = _is_bad(nan, (0.0, 1.0))
    # NaN comparison is always False, so `not (False)` = True
    assert result is True, f"_is_bad(NaN, (0,1)) should return True (NaN comparison), got {result}"


def test_nan_value_reaches_template_format():
    """Bug #2b: when value is NaN, the "default" template fires with NaN value.

    Reproduce the flow: _is_bad(NaN, range) is True (rule triggers),
    _determine_severity(NaN, range) returns "default", template.format(value=NaN)
    renders the NaN as the string "nan" in the Russian message.
    """
    from src.analysis.recommender import Recommender
    from src.types import MetricResult

    r = Recommender()
    nan_metric = MetricResult(
        name="airtime",
        value=float("nan"),
        unit="s",
        is_good=False,
        reference_range=(0.3, 0.6),
    )

    recs = r.recommend([nan_metric], "waltz_jump")
    # #557 fix: NaN values are skipped at the recommender entry, before
    # the rule fires. No recommendation is generated for a NaN value
    # (we can't tell if the metric is good or bad, so no advice is
    # actionable). Pre-fix: NaN triggered the rule, rendered 'nan' in
    # Russian text on 3.11/3.12, or crashed on 3.13+ via format() ValueError.
    assert recs == [], (
        f"NaN metric should produce no recommendations (skipped at the entry), got: {recs}."
    )


def test_nan_with_formatted_template_renders_nan_string():
    """Bug #2c: when a rule with `{value:.2f}` is selected, NaN renders as 'nan'.

    In Python 3.11/3.12, `f"{float('nan'):.2f}"` returns "nan".
    In Python 3.13+, it raises ValueError.
    This test documents the silent-corruption behavior on 3.11/3.12.
    """
    # The 'airtime' rule "too_low" template has `{value:.2f}`. If we force
    # _determine_severity to return "too_low" with NaN value, format() would
    # render NaN as "nan" or crash.
    template = "Время полёта {value:.2f}с (эталон {target_min:.2f}-{target_max:.2f}с)."
    nan = float("nan")
    try:
        result = template.format(value=nan, target_min=0.3, target_max=0.6)
        # In Python 3.11/3.12, NaN formats to "nan" — silent corruption
        assert "nan" in result, f"Expected 'nan' in formatted result, got: {result!r}"
    except ValueError as e:
        # In Python 3.13+, format spec on NaN raises ValueError
        assert "Unknown format code" in str(e), f"Unexpected error: {e}"


# ---------------------------------------------------------------------------
# Bug #3: rules missing "too_high" templates silently use "default" for too-high
# ---------------------------------------------------------------------------


def test_max_height_rule_missing_too_high_template():
    """Bug #3a: max_height rule has no 'too_high' key — falls back to default."""
    from src.analysis.rules.jump_rules import _COMMON_JUMP_RULES

    max_height_rule = next(r for r in _COMMON_JUMP_RULES if r.metric_name == "max_height")
    assert "too_high" not in max_height_rule.templates, (
        "Expected 'too_high' to be MISSING from max_height templates — "
        "this is the bug (falls back to generic 'default' for too-high values)"
    )
    # The fallback that gets used
    assert max_height_rule.templates.get("default", "") != ""


def test_too_high_value_falls_back_to_default_template():
    """Bug #3b: when value > max_good, the default template is used (misleading).

    A value that's too high should ideally have its own "too_high" template.
    Currently the user sees a generic "Следи за высотой" message that doesn't
    acknowledge the actual issue (value is ABOVE the reference range, not
    "needs monitoring").
    """
    from src.analysis.recommender import Recommender
    from src.types import MetricResult

    r = Recommender()
    # max_height range is typically 0.3-0.6 — value 2.0 is way too high
    too_high_metric = MetricResult(
        name="max_height",
        value=2.0,
        unit="m",
        is_good=False,
        reference_range=(0.3, 0.6),
    )
    recs = r.recommend([too_high_metric], "waltz_jump")
    assert recs, "Expected at least one recommendation for too-high value"
    # The default template says "Следи за высотой прыжка." — it does NOT
    # tell the user the value is ABOVE the reference range. This is the bug.
    rec_text = " ".join(recs).lower()
    assert "следи за высотой" in rec_text or "контролируй" in rec_text, (
        f"Expected generic 'check the height' message, got: {recs}"
    )
    # The text does NOT acknowledge "too high" — that's the bug.
    # A correct too_high message would say something like "Слишком высокий прыжок"
    has_too_high_acknowledgement = any(
        word in rec_text for word in ("слишком высок", "выше референс", "выше норм", "отличн")
    )
    # Document: the generic default is used, NOT a too_high-aware message
    # (this is a code defect, not a test failure — the assertion below
    # documents the current broken behaviour)
    assert not has_too_high_acknowledgement, f"Unexpectedly got a too-high-aware message: {recs}"


def test_count_rules_missing_too_high_template():
    """Bug #3c: count all rules in jump_rules.py missing 'too_high' template."""
    from src.analysis.rules.jump_rules import _COMMON_JUMP_RULES

    missing_too_high = [r.metric_name for r in _COMMON_JUMP_RULES if "too_high" not in r.templates]
    # Document the count. Expectation: at least 6 rules lack "too_high".
    # airtime has too_high, landing_knee_angle has too_high, rotation_speed has
    # too_high, approach_torso_lean has too_high, arm_position_score has
    # too_high, toe_assist_proxy has too_high, toe_pick_clean has too_high.
    # Missing: max_height, relative_jump_height, landing_com_velocity,
    # landing_smoothness, landing_trunk_recovery, landing_knee_stability,
    # hard_landing, goe_score
    assert len(missing_too_high) >= 6, (
        f"Expected >= 6 rules missing 'too_high' template, got {len(missing_too_high)}: "
        f"{missing_too_high}"
    )


# ---------------------------------------------------------------------------
# Bug #4: unknown element_type silently returns []
# ---------------------------------------------------------------------------


def test_unknown_element_type_returns_empty_silently():
    """Bug #4: recommend() silently returns [] for unknown element_type.

    #559 fix: validate element_type against registered rules. A typo in
    element_type (e.g. "waltz" instead of "waltz_jump") must NOT be
    indistinguishable from "no problems detected" — that misleads the
    user about their performance. The recommender must raise ValueError
    with a clear message listing the registered types.
    """
    from src.analysis.recommender import Recommender
    from src.types import MetricResult

    r = Recommender()
    m = MetricResult(
        name="airtime",
        value=0.1,  # well below range
        unit="s",
        is_good=False,
        reference_range=(0.3, 0.6),
    )
    # Typo: "waltz" instead of "waltz_jump" — must raise.
    with pytest.raises(ValueError, match="Unknown element_type"):
        r.recommend([m], "waltz")
