"""RED repro — `three_turn_rules._is_bad` false-positive on NaN (tranche MW).

Root cause (`ml/src/analysis/rules/three_turn_rules.py:9-11`):

    def _is_bad(value: float, ref_range: tuple[float, float]) -> bool:
        return not (ref_range[0] <= value <= ref_range[1])

NaN comparison rule (IEEE 754): every comparison involving NaN returns
False. So for `value = float('nan')` and `ref_range = (0.0, 1.0)`:

    0.0 <= NaN  -> False
    NaN <= 1.0  -> False
    (False and False) -> False
    not False   -> True
    _is_bad(NaN, (0.0, 1.0)) -> True   ← rule FIRES

`THREE_TURN_RULES` are wired with `condition=_is_bad` for every rule
(trunk_lean, edge_change_smoothness, knee_angle, shoulder_stability).
When a NaN metric value reaches the rule, `_is_bad(NaN, range) = True`
fires the rule. The downstream template is rendered with `value=NaN`,
which produces silent "nan" in the Russian text (3.11/3.12) or raises
`ValueError` (3.13+ via format spec on NaN).

Consumer chain: NaN metric value -> _is_bad(NaN) = True -> rule fires
-> Russian recommendation text with literal "nan" in the diagnostic
sentence -> user sees actionable advice to "fix" a metric that has
no valid data. False-worst: the rule reports a problem that does not
exist in the data.

Sibling class: jump_rules._is_bad (#887) was fixed to guard with
`if not math.isfinite(value): return False`; three_turn_rules._is_bad
was missed in the same fix-up. This is the same false-positive contract
on a sibling function.

The fix (NOT applied in this RED repro — applied in the follow-up fix
commit on the same branch):
  - Add `import math` and `if not math.isfinite(value): return False`
    at the top of `three_turn_rules._is_bad`, matching the
    `jump_rules._is_bad` (#887) implementation.

These tests call `_is_bad` directly (the function the issue names) so
the test does not depend on the upstream Recommender entry-guard at
`recommender.py:63` — they lock the contract of the predicate itself.
They FAIL today because the predicate returns True for NaN. After the
fix, they pass because the predicate returns False (or a non-True
sentinel) for non-finite values.
"""

from __future__ import annotations

import inspect

import pytest

# --------------------------------------------------------------------------- #
# Observable 1: NaN value must NOT cause _is_bad to return True.
# --------------------------------------------------------------------------- #


def test_three_turn_is_bad_nan_returns_false_repro():
    """CORRECT behavior: `_is_bad(NaN, ref_range)` must NOT return True.
    A NaN value is "unknown", not "bad" — the rule must not fire on
    missing/corrupt data. NaN comparisons return False, so the chained
    `not (low <= nan <= high)` evaluates to True (false-positive rule
    trigger), and the downstream template renders literal "nan" in the
    user-facing Russian text.

    RED now: `_is_bad(NaN, (0.0, 1.0))` returns True (NaN comparison
    cascade + `not (and)` flips False to True). After the fix: the
    function returns False for any non-finite value (or raises — both
    prevent the false-positive rule trigger).
    """
    from src.analysis.rules.three_turn_rules import _is_bad

    nan = float("nan")
    result = _is_bad(nan, (0.0, 1.0))
    assert result is not True, (
        f"BUG: three_turn_rules._is_bad(NaN, (0.0, 1.0)) returned {result!r} — "
        f"NaN must not be classified as 'bad'. NaN is 'unknown', not 'bad'; "
        f"the rule must not fire on corrupt/missing data. The IEEE 754 NaN "
        f"comparison rule means `0.0 <= NaN` and `NaN <= 1.0` are both False, "
        f"so `not (False and False)` is True — a false-positive rule trigger. "
        f"Guard: add `if not math.isfinite(value): return False` (matches "
        f"jump_rules._is_bad #887)."
    )


def test_three_turn_is_bad_nan_in_actual_rule_range_returns_false_repro():
    """CORRECT behavior: `_is_bad(NaN, ref_range)` must return False for
    the actual reference ranges used by THREE_TURN_RULES
    (trunk_lean: (-10, 15), edge_change_smoothness, knee_angle,
    shoulder_stability). The bug fires for ANY ref_range — test multiple
    real ranges so the regression is locked at the rule-data level, not
    a synthetic (0, 1) check.

    RED now: all return True (NaN comparison cascade). After the fix:
    all return False.
    """
    from src.analysis.rules.three_turn_rules import _is_bad

    nan = float("nan")
    # trunk_lean reference range
    assert _is_bad(nan, (-10.0, 15.0)) is not True, (
        "BUG: three_turn_rules._is_bad(NaN, (-10.0, 15.0)) (trunk_lean range) "
        "must not be True. NaN cascades to True via the `not (and)` flip — "
        "false-positive rule trigger on missing data."
    )
    # edge_change_smoothness reference range (typical 0.0..1.0 score)
    assert _is_bad(nan, (0.0, 1.0)) is not True, (
        "BUG: three_turn_rules._is_bad(NaN, (0.0, 1.0)) (edge_change_smoothness) must not be True."
    )
    # knee_angle reference range (typical 90..170 deg)
    assert _is_bad(nan, (90.0, 170.0)) is not True, (
        "BUG: three_turn_rules._is_bad(NaN, (90.0, 170.0)) (knee_angle) must not be True."
    )


# --------------------------------------------------------------------------- #
# Observable 2: +inf / -inf must NOT cause _is_bad to return True either.
# (Catches the broader "non-finite" class, not just NaN — the
# math.isfinite guard covers both.)
# --------------------------------------------------------------------------- #


def test_three_turn_is_bad_inf_returns_false_repro():
    """CORRECT behavior: `_is_bad(+inf, ref_range)` and `_is_bad(-inf,
    ref_range)` must NOT return True. Non-finite values are "unknown",
    not "bad" — +inf above max would naively fire (the > is true for
    the upper bound comparison... actually +inf <= max is False, so the
    chain is False and `not False` is True), -inf below min also
    cascades to True. Same false-positive contract as NaN.

    RED now: both return True. After the fix: both return False
    (math.isfinite catches all three: NaN, +inf, -inf).
    """
    from src.analysis.rules.three_turn_rules import _is_bad

    pinf = float("inf")
    ninf = float("-inf")
    # +inf: `0.0 <= +inf` is True, `+inf <= 1.0` is False -> chain False -> not False = True
    assert _is_bad(pinf, (0.0, 1.0)) is not True, (
        "BUG: three_turn_rules._is_bad(+inf, (0.0, 1.0)) returned True — "
        "+inf is non-finite, must not be classified as 'bad'."
    )
    # -inf: `0.0 <= -inf` is False -> chain False -> not False = True
    assert _is_bad(ninf, (0.0, 1.0)) is not True, (
        "BUG: three_turn_rules._is_bad(-inf, (0.0, 1.0)) returned True — "
        "-inf is non-finite, must not be classified as 'bad'."
    )


# --------------------------------------------------------------------------- #
# Observable 3: regression guard — finite values still classify correctly.
# The NaN guard must not change the finite-value path.
# --------------------------------------------------------------------------- #


def test_three_turn_is_bad_finite_values_still_classify_correctly_repro():
    """Regression guard: finite values must still be classified
    correctly (outside the range -> True, inside the range -> False).
    The NaN guard must not change the finite-value path.

    RED now (and after fix): 0.5 in (0, 1) -> False, 2.0 in (0, 1) -> True,
    -1.0 in (0, 1) -> True. Confirms the fix is a guard, not a rewrite.
    """
    from src.analysis.rules.three_turn_rules import _is_bad

    # In-range finite -> False
    assert _is_bad(0.5, (0.0, 1.0)) is False, (
        "BUG (regression): three_turn_rules._is_bad(0.5, (0.0, 1.0)) should "
        "return False for an in-range finite value."
    )
    # Above max finite -> True
    assert _is_bad(2.0, (0.0, 1.0)) is True, (
        "BUG (regression): three_turn_rules._is_bad(2.0, (0.0, 1.0)) should "
        "return True for an above-max finite value."
    )
    # Below min finite -> True
    assert _is_bad(-1.0, (0.0, 1.0)) is True, (
        "BUG (regression): three_turn_rules._is_bad(-1.0, (0.0, 1.0)) should "
        "return True for a below-min finite value."
    )


# --------------------------------------------------------------------------- #
# Observable 4: source check — three_turn_rules._is_bad must guard against
# non-finite values (root cause locked). Mirrors the #887 jump_rules fix
# and prevents the unguarded pattern from re-appearing.
# --------------------------------------------------------------------------- #


def test_three_turn_is_bad_source_has_isfinite_guard_repro():
    """GREEN contract source check: the fix must add an `isfinite`
    (or `isnan`) guard at the top of `three_turn_rules._is_bad` so
    any non-finite `value` short-circuits to a False-equivalent
    sentinel. The `Recommender.recommend` entry-guard at
    `recommender.py:63` is the primary defense; the per-rule guard is
    defense-in-depth for any direct caller of `_is_bad` (jump_rules
    #887 sets this contract).

    Mirrors `jump_rules._is_bad` (#887) which already has the guard.
    """
    from src.analysis.rules.three_turn_rules import _is_bad

    src = inspect.getsource(_is_bad)
    assert "isfinite" in src or "isnan" in src, (
        "BUG: three_turn_rules._is_bad must guard non-finite values with "
        "`math.isfinite` (preferred, covers NaN + ±inf) or `math.isnan` "
        "(NaN only). Today, NaN/±inf fall through the chained comparison "
        "and `not (False and False)` flips to True — a false-positive rule "
        "trigger on missing data. The guard returns False for non-finite "
        "inputs. Mirror of jump_rules._is_bad (#887) which already has "
        "this guard. The Recommender.recommend entry-guard "
        "(recommender.py:63) is the primary defense; this guard is "
        "defense-in-depth for any direct caller of `_is_bad`."
    )


# --------------------------------------------------------------------------- #
# Observable 5: end-to-end — a NaN three-turn metric does NOT fire a
# rule via the rule's `condition` callable. THREE_TURN_RULES wires
# `condition=_is_bad` for every rule; verify a NaN value does not
# fire. This is the consumer chain the issue names: NaN metric -> rule
# condition -> false trigger -> Russian template with "nan" in text.
# --------------------------------------------------------------------------- #


def test_three_turn_rule_condition_nan_does_not_fire_repro():
    """End-to-end: a NaN metric value does NOT cause a three-turn rule
    to fire via its `condition` callable. This is the consumer chain
    the issue names — the false-positive rule trigger.

    RED now: rule.condition(NaN, range) is _is_bad(NaN, range) = True,
    rule fires, recommendation is produced with NaN. After the fix:
    rule.condition(NaN, range) = False, rule does not fire, no
    recommendation is produced for a corrupt metric.
    """
    from src.analysis.rules.three_turn_rules import THREE_TURN_RULES

    nan = float("nan")
    # trunk_lean rule with a NaN value in the actual ref range.
    # `RecommendationRule` has no `reference_range` attribute — the range
    # is supplied by the metric at the call site (recommender.py:81 passes
    # `metric.reference_range`). Use the actual range that trunk_lean
    # is evaluated against (-10, 15) per the recommender test
    # `test_recommend_three_turn_trunk_lean`.
    rule = next(r for r in THREE_TURN_RULES if r.metric_name == "trunk_lean")
    fired = rule.condition(nan, (-10.0, 15.0))  # type: ignore[arg-type]
    assert fired is not True, (
        f"BUG: three_turn rule 'trunk_lean' condition fired on NaN value "
        f"(condition returned {fired!r}). A non-finite metric must not "
        f"trigger a rule — the downstream template would render 'nan' "
        f"in the user-facing Russian text. The fix must guard "
        f"three_turn_rules._is_bad with `math.isfinite` (mirror of "
        f"jump_rules._is_bad #887)."
    )
