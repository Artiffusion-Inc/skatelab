"""RED repro — `Recommender._determine_severity` silently maps NaN to 'default'.

Root cause (`ml/src/analysis/recommender.py:163-184`):

    def _determine_severity(self, value, reference_range):
        min_good, max_good = reference_range
        if value < min_good:           # NaN < x → False
            return "too_low"
        elif value > max_good:         # NaN > x → False
            return "too_high"
        else:
            return "default"           # ← NaN silently lands here

A NaN metric value (`float('nan')`) falls through both comparisons (NaN
comparisons return False) and silently returns "default" — the severity
for "metric is within range, no recommendation needed". This is the
OPPOSITE signal: "data missing" is rendered as "data fine". The shared
`Recommender.recommend` loop skips non-finite values at entry (#584), so
the severity function is currently only reachable from direct callers,
but the contract is fragile: any future caller that bypasses the entry
guard (refactor, test, debug print) re-introduces the silent
misclassification.

Consumer chain (same as tranches KF..KK): severity → Russian recommendation
text → coach dashboard → diagnosis. A silent "default" hides a missing
metric behind a "metric is fine" template.

The fix (NOT applied in this RED repro — applied in the follow-up fix
commit on the same branch):
  - Add `if not math.isfinite(value): return "no_data"` (or a similar
    sentinel) at the top of `_determine_severity`. The severity must
    distinguish "no data" from "in range, fine".
  - The entry guard in `recommend()` is the primary defense; the severity
    guard is defense-in-depth for direct callers of `_determine_severity`.

These tests call `_determine_severity` directly (the path the issue names)
so the test does not depend on the entry guard — it locks the contract
of the severity function itself. They FAIL today because the function
returns "default" for NaN. After the fix, they pass because the function
returns a non-"default" sentinel for non-finite values.
"""

import inspect

import pytest

from src.analysis.recommender import Recommender

# --------------------------------------------------------------------------- #
# Observable 1: NaN value must NOT silently map to "default".
# --------------------------------------------------------------------------- #


def test_determine_severity_nan_does_not_silently_return_default_repro():
    """CORRECT behavior: a NaN `value` passed to `_determine_severity` must
    NOT return "default". The "default" severity is reserved for "metric is
    within range, no recommendation needed" — NaN is "unknown" and must be
    distinguished. The function must return a non-"default" sentinel (e.g.
    "no_data") so callers can render an explicit "data unavailable" message
    instead of a generic "metric is fine" template.

    RED now: `_determine_severity(nan, (0.3, 1.5))`:
      `nan < 0.3` → False, `nan > 1.5` → False → "default". A NaN metric
    is silently classified as "in range, fine" — the same severity as a
    healthy value of 0.5. After the fix: the function returns a
    non-"default" sentinel (e.g. "no_data") for any non-finite value.
    """
    severity = Recommender()._determine_severity(float("nan"), (0.3, 1.5))
    assert severity != "default", (
        "BUG: _determine_severity(nan, (0.3, 1.5)) returned 'default' — "
        "NaN is silently mapped to the 'metric is fine' severity. NaN must "
        "not be confused with a healthy in-range value. The 'default' "
        "severity is reserved for values inside (min_good, max_good); a "
        "non-finite value is 'unknown' and must be classified as such "
        "(e.g. 'no_data' or raise). `_determine_severity(nan, ...)` is "
        "reachable from any direct caller (refactor, test, debug) — the "
        "Recommender.recommend entry guard is the primary defense (#584), "
        "this function must not silently misclassify non-finite inputs."
    )


# --------------------------------------------------------------------------- #
# Observable 2: finite values still classify correctly (regression guard).
# --------------------------------------------------------------------------- #


def test_determine_severity_finite_values_still_classify_correctly_repro():
    """Regression guard: a finite value outside the range must still return
    "too_low" or "too_high" (the numeric severities). The NaN guard must
    not change the finite-value path.

    RED now: 0.1 < 0.3 → "too_low" and 2.0 > 1.5 → "too_high". After the
    fix (NaN guard at entry): the finite path is unchanged.
    """
    assert Recommender()._determine_severity(0.1, (0.3, 1.5)) == "too_low", (
        "BUG (regression): _determine_severity(0.1, (0.3, 1.5)) should return "
        "'too_low' for a finite below-min value."
    )
    assert Recommender()._determine_severity(2.0, (0.3, 1.5)) == "too_high", (
        "BUG (regression): _determine_severity(2.0, (0.3, 1.5)) should return "
        "'too_high' for a finite above-max value."
    )
    # In-range finite → "default" (the real "metric is fine" case).
    assert Recommender()._determine_severity(0.5, (0.3, 1.5)) == "default", (
        "BUG (regression): _determine_severity(0.5, (0.3, 1.5)) should return "
        "'default' for a finite in-range value — the 'default' severity is "
        "reserved for this case, not for NaN."
    )


# --------------------------------------------------------------------------- #
# Observable 3: nan != in-range value (the semantic distinction the bug
# erases).
# --------------------------------------------------------------------------- #


def test_determine_severity_nan_distinguished_from_in_range_finite_repro():
    """Semantic check: `_determine_severity(nan, range)` and
    `_determine_severity(0.5, range)` (an in-range finite) must return
    DIFFERENT severity values. The "default" mapping for NaN erases this
    distinction — both return "default" — which is the bug.

    RED now: both return "default" — same severity, different semantics.
    After the fix: NaN returns a non-"default" sentinel (e.g. "no_data"),
    and the in-range value still returns "default".
    """
    sev_nan = Recommender()._determine_severity(float("nan"), (0.3, 1.5))
    sev_in_range = Recommender()._determine_severity(0.5, (0.3, 1.5))
    assert sev_nan != sev_in_range, (
        f"BUG: _determine_severity(nan, (0.3, 1.5)) returned {sev_nan!r}, "
        f"same as _determine_severity(0.5, (0.3, 1.5)) which returned "
        f"{sev_in_range!r}. NaN ('unknown') and 0.5 ('in range, fine') must "
        f"be classified differently — they are semantically distinct. The "
        f"silent 'default' mapping for NaN erases the distinction and lets "
        f"'data missing' render as 'data fine' in the user-facing text."
    )


# --------------------------------------------------------------------------- #
# Observable 4: the source must guard _determine_severity against non-finite
# values (root cause locked).
# --------------------------------------------------------------------------- #


def test_determine_severity_source_has_isfinite_guard_repro():
    """GREEN contract source check: the fix must add an `isfinite` guard at
    the top of `_determine_severity` so any non-finite `value` short-circuits
    to a non-"default" sentinel. The shared Recommender.recommend entry
    guard (#584) is the primary defense; this guard is defense-in-depth for
    direct callers.
    """
    src = inspect.getsource(Recommender._determine_severity)
    assert "isfinite" in src, (
        "BUG: _determine_severity must guard non-finite values with "
        "`math.isfinite` (or `numpy.isfinite`) at the top of the function. "
        "Today, NaN and ±inf fall through the chained `<` and `>` checks "
        "and silently return 'default' — same severity as a healthy "
        "in-range value. The guard returns a non-'default' sentinel (e.g. "
        "'no_data') for non-finite inputs."
    )
