"""RED repro — `Recommender.recommend` triggers a rule on a NaN metric value
instead of skipping it, emitting a generic recommendation as if the metric
were merely "off-target" — a NaN-silent false-trigger that hides missing data
behind actionable advice.

Root cause (ml/src/analysis/recommender.py + ml/src/analysis/rules/jump_rules.py):

  `_is_bad(value, ref_range)` (jump_rules.py:9-12):
      return not (ref_range[0] <= value <= ref_range[1])

  For `value = nan`:
    `ref_range[0] <= nan` → False
    `nan <= ref_range[1]` → False
    chained comparison `ref_range[0] <= nan <= ref_range[1]` → False
    `not False` → True  ← NaN is treated as "bad" (rule triggers)

  `_determine_severity(nan, ref_range)` (recommender.py:131-152):
    `nan < min_good` → False
    `nan > max_good` → False
    → "default"  ← generic template, no value shown

  So a NaN metric: (1) triggers the rule (`_is_bad` True), (2) selects the
  "default" template (severity), (3) emits a generic recommendation like
  "Проверь технику отталкивания." — indistinguishable from a real but-unhelpful
  recommendation. The user gets actionable-looking advice on a metric that has
  NO data (NaN), without any "data missing / metric unavailable" signal.

`Recommender.recommend` (recommender.py:23-67):
    for metric in metrics:
        for rule in element_rules:
            if rule.metric_name != metric.name: continue
            if rule.condition(metric.value, metric.reference_range):  # ← NaN triggers
                severity = self._determine_severity(...)               # ← "default"
                template = rule.templates.get(severity, ...)            # ← generic
                recommendation = template.format(value=metric.value, ...) # ← may leak "nan"

Consequences (prod impact — `recommend()` is the user-facing text report):
  1. A NaN metric (common when a keypoint is occluded — see BM/BN/BP/.../BX,
     all CoM-based metrics NaN-leak) triggers a rule and emits a generic
     recommendation. The user gets advice on a metric that has no data, with
     no signal that the metric is unavailable. This is misleading — the user
     may act on "Проверь технику отталкивания." when the real issue is
     "your landing knee was occluded, we couldn't measure airtime."
  2. For templates that interpolate `{value:.2f}`, a NaN value would emit
     "nan" in the Russian text (e.g. "Недостаточная высота прыжка (nan вместо
     0.30-1.50)."). The "default" templates (airtime, max_height,
     relative_jump_height, rotation_speed) avoid interpolation, but the
     "too_low"/"too_high" templates interpolate. A NaN that happens to fall
     on the "too_low" branch via a different reference_range would leak
     "nan" into user-facing text. (The current `_is_bad` + `_determine_severity`
     combo sends NaN to "default", but the contract is fragile — a NaN guard
     at the entry is the robust fix.)
  3. The bug composes with the CoM tranches: a NaN keypoint → NaN metric
     (BM-BX) → false recommendation here. The recommender is the LAST layer;
     it should be the NaN-safety net, not a NaN-silent pass-through.
  4. Existing tests miss it: `test_recommender*` feed all-valid metrics. No
     test feeds a NaN `MetricResult.value` through `recommend()` and asserts
     the rule does NOT fire / the recommendation signals missing data.

The fix (NOT applied — repro only):
  - guard the rule entry: `if not np.isfinite(metric.value): continue` (skip
    NaN/inf metrics — no recommendation for unavailable data); and/or
  - make `_is_bad` NaN-aware: `if not np.isfinite(value): return False`
    (NaN is not "bad", it is "unknown" — should not trigger); and/or
  - add a "no_data" template / recommendation: when a metric is NaN, emit
     "Данные недоступны для метрики X" instead of generic advice.
  - `_determine_severity` should also guard: `if not np.isfinite(value):
    return "no_data"`.

The correct contract: a NaN `MetricResult.value` must NOT trigger a rule and
must NOT emit actionable advice as if the metric were off-target. The
recommender must skip the metric (or emit an explicit "data unavailable"
signal), NOT a generic recommendation.

RED now: the observable assertions below describe the CORRECT behavior — a
NaN metric must NOT produce a recommendation (or must produce an explicit
no-data signal), NOT a generic actionable recommendation. They FAIL because
`_is_bad(nan) = True` triggers the rule and `_determine_severity(nan) =
"default"` selects the generic template. After the fix: NaN is guarded at
entry and no recommendation fires. The source-check test confirms the
`not (ref_range[0] <= value <= ref_range[1])` (NaN-unsafe comparison) line in
`_is_bad` and the unguarded `rule.condition(...)` call are present (root
cause locked).

Pure-Python (no GPU, no DB): `Recommender.recommend` and `_is_bad` are
pure-data functions over a MetricResult list.
"""

import inspect

import numpy as np

from src.analysis.recommender import Recommender
from src.analysis.rules import jump_rules
from src.types import MetricResult


def _metric(name: str, value: float, ref: tuple[float, float] = (0.3, 1.5)) -> MetricResult:
    return MetricResult(name=name, value=value, unit="s", reference_range=ref, is_good=False)


# --------------------------------------------------------------------------- #
# Observable 1: a NaN metric must NOT produce a generic actionable
# recommendation (graceful skip / explicit no-data), NOT false-trigger.
# --------------------------------------------------------------------------- #


def test_nan_metric_does_not_trigger_recommendation_repro():
    """CORRECT behavior: a NaN `MetricResult.value` must NOT trigger a rule
    and must NOT emit a generic actionable recommendation (e.g. "Проверь
    технику отталкивания."). The recommender must skip the metric (no
    recommendation) or emit an explicit "data unavailable" signal — NOT
    advice on a metric that has no data.

    RED now: `MetricResult(value=nan)` → `_is_bad(nan, (0.3, 1.5))`:
    `not (0.3 <= nan <= 1.5)` → `not (False <= nan ...)` → chain is False
    (`nan <= x` is False, `x <= nan` is False) → `not False = True` → rule
    triggers → `_determine_severity(nan, (0.3, 1.5))`: `nan < 0.3` False,
    `nan > 1.5` False → "default" → generic template "Проверь технику
    отталкивания." A NaN metric emits actionable-looking advice with no
    signal that the data is missing. After the fix: NaN is guarded at entry
    and no recommendation fires (or an explicit no-data signal is emitted).
    """
    rec = Recommender()

    # Baseline: a valid low value triggers the "too_low" recommendation
    # (proves the rule fires for off-target values).
    recs_valid_low = rec.recommend([_metric("airtime", 0.1)], "waltz_jump")
    assert len(recs_valid_low) > 0 and "Недостаточное время полёта" in recs_valid_low[0], (
        f"test fixture broken: valid-low airtime (0.1, ref 0.3-1.5) did not "
        f"trigger the too_low recommendation ({recs_valid_low}). The rule "
        f"must fire for off-target values for the NaN contrast to be meaningful."
    )

    # NaN value — must NOT trigger a generic actionable recommendation.
    recs_nan = rec.recommend([_metric("airtime", float("nan"))], "waltz_jump")

    # CORRECT contract: NaN must produce NO recommendation (or an explicit
    # no-data signal), NOT a generic actionable one. The generic
    # "Проверь технику отталкивания." is the NaN-silent false-trigger.
    GENERIC_NAN_ADVICE = "Проверь технику отталкивания."
    assert recs_nan == [] or not any(GENERIC_NAN_ADVICE in r for r in recs_nan), (
        f"BUG: Recommender.recommend emitted a generic actionable recommendation "
        f"({recs_nan}) for a NaN `airtime` metric (value=nan, ref 0.3-1.5). "
        f"`_is_bad(nan, (0.3, 1.5))` = `not (0.3 <= nan <= 1.5)` = `not False` = "
        f"True — NaN triggers the rule. `_determine_severity(nan, ...)` = "
        f"'default' (nan < min is False, nan > max is False) → generic template "
        f"'{GENERIC_NAN_ADVICE}'. A NaN metric (common when a keypoint is "
        f"occluded — see CoM tranches BM-BX) emits actionable-looking advice "
        f"with NO signal that the data is missing. The user may act on advice "
        f"when the real issue is 'your landing knee was occluded, we couldn't "
        f"measure airtime.' The recommender should skip NaN metrics (or emit an "
        f"explicit 'data unavailable' signal), NOT a generic recommendation. "
        f"(Sanity: valid-low 0.1 → {recs_valid_low}.)"
    )


# --------------------------------------------------------------------------- #
# Regression guard: a NaN metric must NOT leak the literal "nan" into the
# recommendation text (templates that interpolate {value}).
# --------------------------------------------------------------------------- #


def test_nan_metric_does_not_leak_nan_string_repro():
    """Regression guard: a NaN `MetricResult.value` must NOT leak the literal
    string "nan" into a recommendation that interpolates `{value:.2f}` (e.g.
    "Недостаточная высота прыжка (nan вместо 0.30-1.50)."). The recommender
    must skip NaN metrics, NOT format "nan" into user-facing Russian text.

    This PASSES today only because `_determine_severity(nan) = "default"`
    routes NaN to the generic (no-interpolation) templates for these rules —
    so "nan" does not reach the text. The contract is FRAGILE: it relies on
    severity routing, not a NaN guard at entry. A future rule/template that
    interpolates `{value}` in the "default" branch, or a NaN that reaches
    "too_low"/"too_high", would leak "nan". This test locks the current
    no-leak behavior so a regression is caught. After a robust NaN-guard fix
    at entry, this still PASSES (NaN skipped → no text at all).
    """
    rec = Recommender()
    # Use a metric whose "default" template does NOT interpolate, but whose
    # "too_low" template does — to catch both the false-trigger and any "nan"
    # text leak across all rules that fire on the NaN value.
    metrics = [
        _metric("airtime", float("nan")),
        _metric("max_height", float("nan"), ref=(0.1, 0.5)),
        _metric("relative_jump_height", float("nan"), ref=(0.1, 0.5)),
        _metric("rotation_speed", float("nan"), ref=(100.0, 600.0)),
        _metric("landing_knee_angle", float("nan"), ref=(90.0, 170.0)),
    ]
    recs = rec.recommend(metrics, "waltz_jump")

    # CORRECT contract: NO recommendation should contain the literal "nan"
    # (NaN must be skipped or signaled, not formatted into text).
    nan_leaks = [r for r in recs if "nan" in r.lower()]
    assert not nan_leaks, (
        f"BUG: Recommender.recommend leaked the literal 'nan' into user-facing "
        f"recommendation text ({nan_leaks}) for NaN metric values. A NaN "
        f"`MetricResult.value` must be skipped (no recommendation) or signaled "
        f"as 'data unavailable', NOT formatted into Russian text. "
        f"`_is_bad(nan) = True` triggers the rule and `template.format(value=nan, "
        f"...)` emits 'nan' in the text. (All recs: {recs}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 3: NaN must NOT trigger MORE rules than a valid in-range value
# (NaN should be neutral, not "bad").
# --------------------------------------------------------------------------- #


def test_nan_metric_not_more_triggered_than_valid_in_range_repro():
    """CORRECT behavior: a NaN metric must NOT trigger a rule when a valid
    in-range value does NOT. NaN is "unknown", not "bad" — it must be neutral
    (skip), not trigger.

    RED now: a valid in-range airtime (0.5, ref 0.3-1.5) does NOT trigger
    (`_is_bad(0.5) = not (0.3 <= 0.5 <= 1.5) = not True = False`). A NaN
    airtime DOES trigger (`_is_bad(nan) = not False = True`). NaN triggers
    MORE than a valid in-range value — a false trigger on missing data.
    After the fix: NaN is skipped (neutral), same as or fewer than in-range.
    """
    rec = Recommender()
    recs_valid_good = rec.recommend([_metric("airtime", 0.5)], "waltz_jump")
    recs_nan = rec.recommend([_metric("airtime", float("nan"))], "waltz_jump")

    # In-range valid → no recommendation (rule does not fire).
    assert recs_valid_good == [], (
        f"test fixture broken: in-range airtime (0.5, ref 0.3-1.5) triggered a "
        f"recommendation ({recs_valid_good}); expected no trigger. The rule "
        f"must NOT fire for in-range values for the NaN contrast to be meaningful."
    )

    # CORRECT contract: NaN must NOT trigger MORE rules than in-range valid.
    # NaN is "unknown", not "bad" — it must be neutral (no trigger), not a
    # false trigger. The rule fires on NaN (`_is_bad(nan) = True`) but NOT
    # on in-range (0.5) — a false trigger on missing data.
    assert len(recs_nan) <= len(recs_valid_good), (
        f"BUG: NaN airtime triggered {len(recs_nan)} recommendation(s) "
        f"({recs_nan}), but a valid in-range airtime (0.5) triggered "
        f"{len(recs_valid_good)} (none). NaN is 'unknown', not 'bad' — it "
        f"must be neutral (skip / no trigger), not a false trigger. "
        f"`_is_bad(nan, (0.3, 1.5))` = `not (0.3 <= nan <= 1.5)` = `not False` "
        f"= True triggers the rule, while `_is_bad(0.5, ...)` = `not True` = "
        f"False does not. NaN triggers MORE than in-range — a false trigger on "
        f"missing data."
    )


# --------------------------------------------------------------------------- #
# Regression guard: a valid off-target value still triggers the correct
# recommendation.
# --------------------------------------------------------------------------- #


def test_valid_off_target_still_triggers_repro():
    """Regression guard: a valid off-target metric must still trigger the
    correct recommendation. The fix (NaN guard at entry / NaN-aware `_is_bad`)
    must not change the valid-value case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the valid off-target case.
    """
    rec = Recommender()
    # too_low (0.1 < 0.3)
    recs_low = rec.recommend([_metric("airtime", 0.1)], "waltz_jump")
    assert len(recs_low) > 0 and "Недостаточное время полёта" in recs_low[0], (
        f"BUG (regression): valid-low airtime (0.1, ref 0.3-1.5) did not trigger "
        f"the too_low recommendation ({recs_low}). The valid off-target case must "
        f"be unchanged by the NaN-aware fix."
    )
    # too_high (2.0 > 1.5)
    recs_high = rec.recommend([_metric("airtime", 2.0)], "waltz_jump")
    assert len(recs_high) > 0 and "Отличное время полёта" in recs_high[0], (
        f"BUG (regression): valid-high airtime (2.0, ref 0.3-1.5) did not trigger "
        f"the too_high recommendation ({recs_high}). The valid off-target case "
        f"must be unchanged by the NaN-aware fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — NaN-unsafe comparison in `_is_bad` +
# unguarded rule.condition call + unguarded _determine_severity.
# --------------------------------------------------------------------------- #


def test_recommender_nan_false_trigger_source_repro():
    """GREEN contract source check: the NaN false-trigger bug is fixed at the
    shared root.

    `_is_bad` (jump_rules.py) is NaN-aware — a non-finite value returns False
    (unknown, not bad), so a NaN metric cannot false-trigger a rule via the
    `not (low <= nan <= high) = True` trap. `Recommender.recommend` skips
    non-finite metrics at entry (#584) as the first line of defense.
    """
    # `_is_bad` is module-level in jump_rules.py — now NaN-aware.
    is_bad_src = inspect.getsource(jump_rules._is_bad)
    assert "not (ref_range[0] <= value <= ref_range[1])" in is_bad_src, (
        "BUG: _is_bad must still use the range comparison for the finite path."
    )
    assert "math.isfinite(value)" in is_bad_src, (
        "BUG: _is_bad must guard a non-finite value (return False) so the "
        "NaN-unsafe `not (low <= nan <= high) = True` comparison cannot "
        "false-trigger a rule on missing data (#887)."
    )

    # `recommend` skips non-finite metrics at entry — the first line of defense
    # (#584), so NaN never reaches `rule.condition`.
    rec_src = inspect.getsource(Recommender.recommend)
    assert "if not math.isfinite(metric.value):" in rec_src, (
        "BUG: Recommender.recommend must skip non-finite metric values at entry "
        "(#584) so NaN cannot false-trigger a rule."
    )
