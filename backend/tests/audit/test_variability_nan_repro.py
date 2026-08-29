"""RED repro — diagnostics variability NaN CV silently skips warning (#1229).

Tranche KO.

Root cause (backend/app/services/diagnostics.py:160-186):
    def check_high_variability(*, values: list[float], ...) -> Finding | None:
        finite = [v for v in values if math.isfinite(v)]   # filters NaN
        if len(finite) < 5:                                 # short-circuit
            return None
        mean = sum(finite) / len(finite)
        if mean == 0:
            return None
        variance = sum((v - mean) ** 2 for v in finite) / len(finite)
        std = variance ** 0.5
        cv = std / abs(mean)                                # NaN-risk
        if cv > 0.20:                                       # NaN > X == False
            return Finding(...variability...)

The `> 0.20` boolean guard is the silent-skip hazard. Although the upstream
`finite` filter catches most NaN paths, the comparison `cv > 0.20` itself
is not guarded with `math.isfinite(cv)`. If `cv` is ever NaN/inf (e.g. a
future code path that bypasses the filter, or an edge case where `abs(mean)`
underflows to 0.0 while the equality check on `mean` does not fire due to
floating-point representation), `NaN > 0.20 = False` and the warning is
silently skipped.

The pattern is inconsistent with `check_declining_trend` (line 95):
    if is_decline and math.isfinite(r_squared) and r_squared > THRESHOLD:
That function guards the comparison with `math.isfinite(...)`. The
variability check does not.

NaN CV is semantically different from a real CV:
    - cv = 0.30: "high variability, warn coach"
    - cv = NaN:  "I don't know, corrupt data"

The diagnosis must be observable as a data-quality signal, not silently
hidden as "no variability".

Consumer chain:
    silent skip  ->  no variability signal  ->
    coach dashboard misses inconsistency  ->  no intervention.

The fix (NOT applied here, per audit reglement): add `math.isfinite(cv)`
guard on the boolean threshold, or explicit `is_finite` check.

This test file (3/5 must fail on master, 2/5 are regression guards):
    1. source: `if cv > 0.20:` is the unguarded NaN-arg-order-hazard. (PASS: bug locked)
    2. source: `math.isfinite(cv)` guard is MISSING.             (FAIL: fix needed)
    3. source: pattern inconsistent with `check_declining_trend`. (FAIL: fix needed)
    4. behavioural: high CV still warns (regression guard).      (PASS: stays PASS)
    5. behavioural: mixed NaN+finite still warns (regression).   (PASS: stays PASS)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DIAG_PATH = BACKEND_ROOT / "app" / "services" / "diagnostics.py"


def _load_diag():
    spec = importlib.util.spec_from_file_location("_diag_under_test", DIAG_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _function_body(src: str, fn_name: str) -> str:
    """Extract the body of a top-level function from source."""
    start = src.find(f"def {fn_name}(")
    assert start != -1, f"{fn_name}() not found in diagnostics.py"
    next_def = src.find("\ndef ", start + 1)
    return src[start : next_def if next_def != -1 else len(src)]


# ---------------------------------------------------------------------------
# Source-level RED tests (must FAIL on master, PASS after fix).
# ---------------------------------------------------------------------------


def test_variability_source_lacks_isfinite_cv_guard():
    """Source check: `math.isfinite(cv)` guard is missing from
    `check_high_variability`.

    RED: this test FAILS on master — the guard is absent.
    GREEN: the guard appears, mirroring `check_declining_trend:95`
    (`math.isfinite(r_squared) and r_squared > THRESHOLD`).
    """
    src = DIAG_PATH.read_text(encoding="utf-8")
    body = _function_body(src, "check_high_variability")
    assert "isfinite(cv)" in body, (
        "BUG: `math.isfinite(cv)` guard missing from check_high_variability "
        "in diagnostics.py (#1229). The `if cv > 0.20:` comparison silently "
        "skips on NaN cv (Python IEEE 754: `NaN > 0.20 == False`). "
        "Mirror the pattern in `check_declining_trend` (line 95): "
        "`math.isfinite(r_squared) and r_squared > THRESHOLD`. "
        f"Function body:\n{body}"
    )


def test_variability_source_pattern_inconsistent_with_declining_trend():
    """Source check: the threshold comparison in `check_high_variability`
    must mirror the `math.isfinite(...) and X > THRESHOLD` pattern used by
    `check_declining_trend` (line 95).

    RED: this test FAILS on master — `check_high_variability` uses
    `if cv > 0.20:` without the `math.isfinite(cv) and ...` wrapper.
    GREEN: the wrapper is added.
    """
    src = DIAG_PATH.read_text(encoding="utf-8")
    var_body = _function_body(src, "check_high_variability")
    # Find the line with the threshold comparison. The bare `cv > 0.20`
    # may appear on a line that does or does not have the isfinite wrapper.
    # We check: the substring `math.isfinite(cv) and cv > 0.20` must be
    # present (or equivalent), and the bare pattern `if cv > 0.20:` (with
    # `if` immediately preceding) must NOT be present.
    wrapped = "math.isfinite(cv) and cv > 0.20" in var_body
    bare = var_body.find("if cv > 0.20")
    assert wrapped, (
        "BUG: `math.isfinite(cv) and cv > 0.20` short-circuit-AND pattern "
        "missing from check_high_variability (#1229). Mirror "
        "`check_declining_trend` line 95: "
        "`if is_decline and math.isfinite(r_squared) and "
        "r_squared > R_SQUARED_TREND_THRESHOLD:`. "
        f"Function body:\n{var_body}"
    )
    assert bare == -1, (
        "BUG: bare `if cv > 0.20:` (no isfinite wrapper) still present "
        "in check_high_variability (#1229). The bare `>` comparison "
        "silently skips on NaN cv. Function body:\n"
        f"{var_body}"
    )


def test_variability_source_does_not_silently_skip_on_nan_cv():
    """Source check: the boolean comparison `cv > 0.20` is the silent-skip
    hazard. After the fix, the comparison must NOT be a bare `>` on a
    possibly-NaN value.

    RED: `if cv > 0.20:` is bare (no isfinite wrapper) -> fails.
    GREEN: the comparison is guarded.
    """
    src = DIAG_PATH.read_text(encoding="utf-8")
    var_body = _function_body(src, "check_high_variability")
    # The bare pattern `if cv > 0.20` (with `if` immediately preceding,
    # no isfinite wrapper) must not appear. After the fix the comparison
    # is wrapped in `math.isfinite(cv) and ...`, so `if cv > 0.20` as a
    # bare prefix is gone.
    bare_pattern_idx = var_body.find("if cv > 0.20")
    assert bare_pattern_idx == -1, (
        "BUG: bare `if cv > 0.20` comparison present in check_high_variability "
        "without `math.isfinite(cv) and ...` short-circuit-AND wrapper "
        "(#1229). The bare `>` comparison silently skips on NaN cv. "
        f"Body excerpt: {var_body[max(0, bare_pattern_idx - 100) : bare_pattern_idx + 100]!r}"
    )


# ---------------------------------------------------------------------------
# Behavioural regression guards (PASS on master, must stay PASS after fix).
# ---------------------------------------------------------------------------


def test_variability_high_cv_still_warns_after_guard():
    """Regression: real high CV still produces a warning.

    Wide variation [1, 5, 1, 5, 1] -> CV ~0.6 -> VARIABILITY.
    The fix (isfinite guard) must not break the typical-case warning.
    """
    mod = _load_diag()
    result = mod.check_high_variability(
        element="jumps",
        metric="airtime",
        values=[1.0, 5.0, 1.0, 5.0, 1.0],
        metric_label="Время в воздухе",
    )
    assert result is not None, (
        "High CV [1,5,1,5,1] must produce variability warning (#1229). "
        "Got None — fix is over-aggressive and broke the happy path."
    )
    assert result.severity == "warning", (
        f"Variability finding must be severity='warning', got {result.severity!r}"
    )
    assert "nan" not in result.detail.lower(), (
        f"Variability detail must not contain 'NaN', got: {result.detail!r}"
    )


def test_variability_mixed_nan_finite_still_warns():
    """Regression: mixed NaN+finite values still produce a warning when
    the finite subset has high CV.

    [1, 5, 1, 5, 1, 5, NaN, NaN] -> finite=[1,5,1,5,1,5] (6 high-CV) -> warn.
    The fix must not silently skip due to NaN propagation.
    """
    mod = _load_diag()
    result = mod.check_high_variability(
        element="jumps",
        metric="airtime",
        values=[1.0, 5.0, 1.0, 5.0, 1.0, 5.0, float("nan"), float("nan")],
        metric_label="Время в воздухе",
    )
    assert result is not None, (
        "Mixed values with 6 finite high-CV entries must produce a warning "
        "(#1229). Got None — the `NaN > 0.20 == False` boolean guard is "
        "silently skipping the warning."
    )
    assert "nan" not in result.detail.lower(), (
        f"Variability detail must not contain 'nan', got: {result.detail!r}"
    )
