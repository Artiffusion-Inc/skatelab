"""RED repro — linear_regression silently masks NaN-polluted history (#634).

backend/app/services/diagnostics.py:21-39 `linear_regression`:
    mean = sum(values) / n   # NaN if any value is NaN
    ss_yy = sum((yi - mean) ** 2 for yi in values)  # NaN
    ...
    slope = ss_xy / ss_xx  # NaN
    r_sq = (ss_xy**2) / (ss_xx * ss_yy) if ss_yy > 0 else 0.0  # 0.0 (NaN > 0 is False)

Returns (NaN, 0.0). Downstream:
- check_declining_trend: `slope < 0` is False (NaN comparison) → no finding
- /trend route: same → "stable"
- Real regression hidden behind silently-stable classification.

Fix: filter NaN/inf at function entry, recompute n on filtered list,
return (0.0, 0.0) when n < 2.
"""

from __future__ import annotations

import importlib.util
import math
import re
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


def test_source_filters_nan_at_entry():
    """linear_regression must import math and filter NaN/inf at function entry."""
    src = DIAG_PATH.read_text(encoding="utf-8")
    # Top-level `import math` must exist in the file.
    assert "import math" in src, (
        "diagnostics.py must top-level `import math` so linear_regression "
        "can use math.isfinite to filter NaN/inf values (#634)."
    )
    # Find linear_regression block.
    block_start = src.find("def linear_regression(")
    assert block_start != -1
    next_def = src.find("\ndef ", block_start + 1)
    block = src[block_start:next_def] if next_def != -1 else src[block_start:]

    # Must reference math.isfinite.
    assert "math.isfinite" in block, (
        f"linear_regression must use math.isfinite to filter NaN/inf from input "
        f"values BEFORE computing mean/ss_yy/ss_xy. Block:\n{block}"
    )
    # The filter must iterate `values` and keep only finite entries.
    has_value_filter = bool(
        re.search(r"\w+\s*=\s*\[[^\]]*for[^\]]*values[^\]]*math\.isfinite", block)
    )
    assert has_value_filter, (
        f"linear_regression must filter `values` (input) by math.isfinite. Block:\n{block}"
    )


def test_linear_regression_one_nan_filters_properly():
    """One NaN in input must be filtered, slope/r² computed on the rest."""
    mod = _load()
    # Three finite + one NaN. NaN must be excluded; remaining three points
    # give a valid slope/r².
    slope, r_sq = mod.linear_regression([0.30, float("nan"), 0.35, 0.33])
    # With NaN filtered, the regression is on [0.30, 0.35, 0.33] — slope finite.
    assert math.isfinite(slope), f"slope must be finite after NaN filter, got {slope!r}"
    assert math.isfinite(r_sq), f"r_sq must be finite after NaN filter, got {r_sq!r}"
    # And the result should match the regression of just the finite values.
    slope_ref, r_sq_ref = mod.linear_regression([0.30, 0.35, 0.33])
    assert slope == pytest.approx(slope_ref), (
        f"NaN-filtered regression must equal the finite-only regression. "
        f"NaN-filtered slope={slope!r}, finite-only slope={slope_ref!r}"
    )
    assert r_sq == pytest.approx(r_sq_ref)


def test_linear_regression_all_nan_returns_zero_zero():
    """All-NaN input → (0.0, 0.0) (no crash, no NaN)."""
    mod = _load()
    slope, r_sq = mod.linear_regression([float("nan"), float("nan"), float("nan")])
    assert (slope, r_sq) == (0.0, 0.0), (
        f"all-NaN input must return (0.0, 0.0), got ({slope!r}, {r_sq!r})"
    )


def test_linear_regression_inf_filtered():
    """±inf must also be filtered (treated like NaN)."""
    mod = _load()
    slope, r_sq = mod.linear_regression([0.30, float("inf"), 0.35, 0.33])
    assert math.isfinite(slope), f"slope must be finite after inf filter, got {slope!r}"
    assert math.isfinite(r_sq), f"r_sq must be finite after inf filter, got {r_sq!r}"


def test_linear_regression_check_declining_trend_fires_with_nan_in_history():
    """End-to-end: a real decline with one NaN must still fire check_declining_trend.

    Pre-fix: NaN → slope=NaN → `slope < 0` False → no finding.
    Post-fix: NaN filtered → real slope → finding fires.
    """
    mod = _load()
    # 8 sessions: 7 clearly declining + 1 with a NaN (missing data).
    values = [10.0, 9.8, 9.6, 9.4, float("nan"), 9.0, 8.8, 8.6]
    finding = mod.check_declining_trend(
        element="jumps",
        metric="airtime",
        values=values,
        metric_label="Время в воздухе",
    )
    assert finding is not None, (
        "check_declining_trend must fire on a real decline even when one "
        "session has NaN data — the function should filter NaN, not classify "
        "the series as 'stable' (#634). Got None."
    )
    assert "ухудшается" in finding.message
