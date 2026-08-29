"""RED repro — /trend route silently classifies NaN slope/r² as 'stable' (#1249).

backend/app/routes/metrics.py:154-163 — trend gate (BEFORE FIX):
    slope, r_sq = linear_regression(values)
    improving = (slope > 0) if mdef.direction == "higher" else (slope < 0)
    declining = (slope < 0) if mdef.direction == "higher" else (slope > 0)
    if improving and r_sq > R_SQUARED_TREND_THRESHOLD:   # NaN > 0.3 = False
        trend = "improving"
    elif declining and r_sq > R_SQUARED_TREND_THRESHOLD:  # NaN > 0.3 = False
        trend = "declining"
    # else: trend = "stable"

NaN comparisons in Python IEEE 754 are always False, so non-finite
slope/r² silently fall through to "stable" (NaN) or falsely classify as
"improving" (inf). linear_regression already filters NaN/inf at entry (#634),
but the route has no defense-in-depth guard — a future regression in the
underlying function (or a non-finite input that bypasses it) would silently
mis-classify.

Fix: add `math.isfinite(slope) and math.isfinite(r_sq)` guard before the
classification branches. On non-finite input, return trend="unknown" instead
of mis-classifying.

3/5 fail on master (RED), 2/5 pass (regression + happy-path).
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
METRICS_PATH = BACKEND_ROOT / "app" / "routes" / "metrics.py"


def _classify_trend(slope: float, r_sq: float, direction: str, threshold: float) -> str:
    """Execute the EXACT classification code from the /trend route source.

    We extract the classification block (improving/declining assignments +
    the if/elif/else chain + any guard) from metrics.py and exec it. The
    destructure `slope, r_sq = linear_regression(values)` is skipped — we
    pre-supply those values. This binds the test to the real route logic
    with no parallel implementation that could drift.
    """
    src = METRICS_PATH.read_text(encoding="utf-8")
    start = src.find("slope, r_sq = linear_regression(values)")
    assert start != -1, "expected the trend regression assignment in metrics.py"
    end = src.find("        # Current PR", start)
    assert end != -1, "expected the end of the trend block in metrics.py"
    # Walk to end of the destructure line, then take everything after.
    line_end = src.find("\n", start) + 1
    block = textwrap.dedent(src[line_end:end])
    ns: dict = {
        "slope": slope,
        "r_sq": r_sq,
        "direction": direction,
        "threshold": threshold,
        "trend": "stable",
        "math": __import__("math"),
        "R_SQUARED_TREND_THRESHOLD": threshold,
        "mdef": type("M", (), {"direction": direction})(),
    }
    exec(compile(block, "<trend-block>", "exec"), ns)  # noqa: S102  (test extracts & runs route source)
    return ns["trend"]


# ---------------------------------------------------------------------------
# 1) Source-level: trend block must guard non-finite slope/r².
# ---------------------------------------------------------------------------
def test_trend_block_uses_isfinite_guard():
    """Structural anchor: trend block must call math.isfinite on slope AND r_sq.

    This is the load-bearing test for #1249. It catches both the original
    silent-NaN→stable bug AND any future drift that removes the guard.
    """
    src = METRICS_PATH.read_text(encoding="utf-8")
    assert "import math" in src, (
        "backend/app/routes/metrics.py must top-level `import math` so the "
        "trend classifier can call math.isfinite (#1249)."
    )
    start = src.find("slope, r_sq = linear_regression(values)")
    assert start != -1
    # End at the next outer-scope comment (`        # Current PR` at 8 spaces).
    end = src.find("        # Current PR", start)
    if end == -1:
        end = start + 1500
    block = src[start:end]
    assert "math.isfinite" in block, (
        f"trend block must reference math.isfinite (#1249). Block:\n{block}"
    )
    assert re.search(r"math\.isfinite\(\s*slope\s*\)", block), (
        f"trend block must call math.isfinite(slope). Block:\n{block}"
    )
    assert re.search(r"math\.isfinite\(.*\br_sq\b", block), (
        f"trend block must call math.isfinite(r_sq). Block:\n{block}"
    )


# ---------------------------------------------------------------------------
# 2) Behavioral: NaN slope must NOT be classified as "stable".
# ---------------------------------------------------------------------------
def test_trend_with_nan_slope_is_not_silently_stable():
    """The route's classifier must short-circuit on non-finite, not silently
    emit "stable".

    Bug: NaN > anything is False, NaN < anything is False → both branches
    skip → trend = "stable". Fails on master, passes after isfinite guard.
    """
    result = _classify_trend(
        slope=float("nan"),
        r_sq=float("nan"),
        direction="higher",
        threshold=0.3,
    )
    assert result != "stable", (
        f"NaN slope/r² must NOT silently classify as 'stable' — #1249. Got trend={result!r}."
    )


# ---------------------------------------------------------------------------
# 3) Behavioral: ±inf slope must not falsely classify as a real trend.
# ---------------------------------------------------------------------------
def test_trend_with_inf_slope_does_not_falsely_classify():
    """inf has the same defect as NaN: it must NOT be reported as a real trend.

    Python's inf > 0.3 is True — without a guard, inf slope + inf r² produces
    trend='improving' for direction='higher'. A clearly corrupt series
    reported as a confident 'improving' is just as wrong as the silent-NaN
    case. The isfinite guard blocks both.
    """
    result = _classify_trend(
        slope=float("inf"),
        r_sq=float("inf"),
        direction="higher",
        threshold=0.3,
    )
    assert result != "improving", (
        f"±inf must not be reported as 'improving' — #1249. Got {result!r}."
    )
    assert result != "declining", (
        f"±inf must not be reported as 'declining' either. Got {result!r}."
    )


# ---------------------------------------------------------------------------
# 4) Regression: clean improving values still classify as 'improving'.
# ---------------------------------------------------------------------------
def test_trend_regression_clean_improving_still_improving():
    """Adding the isfinite guard must not break the happy path.

    direction='higher' + positive slope + r² > 0.3 → 'improving'.
    """
    result = _classify_trend(
        slope=0.05,
        r_sq=0.7,
        direction="higher",
        threshold=0.3,
    )
    assert result == "improving", (
        f"clean improving series must classify as 'improving'. Got {result!r}."
    )


# ---------------------------------------------------------------------------
# 5) Regression: clean declining values still classify as 'declining'.
# ---------------------------------------------------------------------------
def test_trend_regression_clean_declining_still_declining():
    """Adding the isfinite guard must not break the decline path.

    direction='higher' + negative slope + r² > 0.3 → 'declining'.
    """
    result = _classify_trend(
        slope=-0.04,
        r_sq=0.6,
        direction="higher",
        threshold=0.3,
    )
    assert result == "declining", (
        f"clean declining series must classify as 'declining'. Got {result!r}."
    )
