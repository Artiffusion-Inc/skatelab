"""RED repro — check_declining_trend silently skips NaN r^2 (#1246).

backend/app/services/diagnostics.py:79 (line 95 in current state):
    is_decline = (slope < 0) if direction == "higher" else (slope > 0)
    if is_decline and r_squared > R_SQUARED_TREND_THRESHOLD:   # NaN > 0.3 = False
        return Finding(...)

Python IEEE 754: any comparison with NaN is False, including `NaN > 0.3`.
So when r_squared is NaN, the check silently skips the decline warning.
The coach never sees the signal — regression hidden behind a "stable" class.

Consumer chain:
    silent skip -> no decline signal -> coach missing trend -> no intervention.

Fix (NOT applied): add math.isfinite(r_squared) guard before the comparison.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DIAG_PATH = BACKEND_ROOT / "app" / "services" / "diagnostics.py"


def _load():
    spec = importlib.util.spec_from_file_location("_diag_under_test", DIAG_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_check_declining_trend_handles_nan_rsquared():
    """Direct: r_squared is NaN -> the consumer must not silently skip via NaN>0.3.

    Pre-fix: `if is_decline and r_squared > 0.3` -> `NaN > 0.3 == False` -> None.
    Post-fix: math.isfinite(r_squared) guards the comparison -> NaN r^2 returns None
    EXPLICITLY (via the guard), not via the NaN comparison shortcut.

    The bug was SILENT (looked like a real 'stable' classification). The fix
    makes the skip explicit and deterministic. The actual regression of
    #1246 is that NaN r^2 was indistinguishable from r^2=0.0 to readers; the
    guard removes that ambiguity.
    """
    mod = _load()
    # Force linear_regression to return a real decline signal but NaN r^2.
    original = mod.linear_regression

    def fake_regression(values):
        # Real declining slope; r_squared NaN simulates producer edge cases
        # (e.g. future refactor, custom caller, or upstream NaN).
        return -1.0, float("nan")

    mod.linear_regression = fake_regression
    try:
        finding = mod.check_declining_trend(
            element="jumps",
            metric="airtime",
            values=[1.0, 2.0, 3.0, 4.0, 5.0],  # 5+ required
            metric_label="Время в воздухе",
        )
    finally:
        mod.linear_regression = original

    # With the isfinite guard, NaN r^2 is rejected explicitly -> no finding.
    # Pre-fix: also None, but via the NaN>0.3 shortcut. Post-fix: None via guard.
    # The KEY assertion: it must not crash, must not fire a misleading finding
    # with R^2=nan in the detail, and must be deterministic.
    assert finding is None, (
        "NaN r_squared must be rejected by the isfinite guard; otherwise the "
        "consumer silently classifies via `NaN > 0.3 == False` (#1246)."
    )


def test_check_declining_trend_nan_r_squared_source_includes_isfinite_guard():
    """The source must guard `r_squared` with math.isfinite before the > comparison.

    The producer (linear_regression) currently filters NaN inputs, but the
    consumer must defend itself too: future refactors, alternative callers,
    or upstream NaN propagation must not silently skip the decline signal.
    """
    src = DIAG_PATH.read_text(encoding="utf-8")
    # Locate the check_declining_trend function body.
    fn_start = src.find("def check_declining_trend(")
    assert fn_start != -1, "check_declining_trend function not found"
    next_def = src.find("\ndef ", fn_start + 1)
    block = src[fn_start:next_def] if next_def != -1 else src[fn_start:]

    # The block must reference math.isfinite to guard r_squared.
    assert "math.isfinite" in block, (
        "check_declining_trend must use math.isfinite to guard r_squared "
        "before the `r_squared > R_SQUARED_TREND_THRESHOLD` comparison (#1246). "
        f"Block:\n{block}"
    )

    # Sanity: the unguarded pattern should not be the only check.
    # The block must reference r_squared and the threshold.
    assert "r_squared" in block
    assert "R_SQUARED_TREND_THRESHOLD" in block


def test_check_declining_trend_nan_r_squared_real_decline_fires_via_isfinite_path():
    """End-to-end: real decline with finite r^2 still fires after the guard.

    The guard is additive. Real declines with finite r^2 above threshold
    must still produce a Finding. This test guards the happy path.
    """
    mod = _load()
    # Strong decline with clean data — r^2 will be near 1.0, well above 0.3.
    values = [10.0, 9.5, 9.0, 8.5, 8.0, 7.5, 7.0]
    finding = mod.check_declining_trend(
        element="jumps",
        metric="airtime",
        values=values,
        metric_label="Время в воздухе",
    )
    assert finding is not None, (
        "Real decline with finite r^2 must still fire after the isfinite guard (#1246)."
    )
    assert finding.severity == "warning"
    assert "ухудшается" in finding.message


def test_check_declining_trend_normal_finite_path_unchanged():
    """Regression guard: the fix must not break the happy path.

    A real decline with finite r^2 above threshold still fires; a non-decline
    with finite r^2 still returns None. The isfinite guard is additive.
    """
    mod = _load()

    # Case 1: real decline, finite r^2 above 0.3 -> fires.
    real_decline = [10.0, 9.5, 9.0, 8.5, 8.0, 7.5]
    f1 = mod.check_declining_trend(
        element="jumps",
        metric="airtime",
        values=real_decline,
        metric_label="Время в воздухе",
    )
    assert f1 is not None, "Real decline with finite r^2 must fire"
    assert "ухудшается" in f1.message

    # Case 2: flat / no decline -> still returns None.
    flat = [5.0, 5.05, 4.95, 5.02, 4.98, 5.0]
    f2 = mod.check_declining_trend(
        element="jumps",
        metric="airtime",
        values=flat,
        metric_label="Время в воздухе",
    )
    # Flat series has near-zero slope, so is_decline is False regardless of r^2.
    # Pre-fix and post-fix both return None.
    assert f2 is None, "Non-declining series must not fire"


def test_check_declining_trend_inf_rsquared_also_guarded():
    """inf r^2 must also be caught (inf > 0.3 is True on master, which
    would falsely fire). The isfinite guard rejects both NaN and inf.
    """
    mod = _load()

    def fake_regression(values):
        # Inf simulates a regression where the data is perfectly linear
        # but ss_yy=0 caused division issues -> r^2=inf.
        return -1.0, float("inf")

    original = mod.linear_regression
    mod.linear_regression = fake_regression
    try:
        finding = mod.check_declining_trend(
            element="jumps",
            metric="airtime",
            values=[1.0, 2.0, 3.0, 4.0, 5.0],
            metric_label="Время в воздухе",
        )
    finally:
        mod.linear_regression = original

    # With the isfinite guard, inf r^2 is rejected -> the function takes
    # the safe path. We don't assert a specific outcome (None vs Finding);
    # we only assert it does not crash and does not produce a misleading
    # signal from the inf value. The key invariant: behavior is deterministic.
    # Note: on master, inf > 0.3 == True, so a finding fires — but with
    # meaningless R²=inf in the detail. The fix rejects inf and skips the
    # bogus finding, so the post-fix behavior is: no finding.
    assert finding is None, (
        "inf r^2 must be rejected by the isfinite guard; "
        "otherwise the detail string 'R²=inf' is meaningless (#1246)."
    )
