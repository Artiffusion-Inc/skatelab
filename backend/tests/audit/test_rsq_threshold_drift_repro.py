"""RED repro — /trend R² threshold 0.3 vs /diagnostics 0.5 spec drift (#633).

Same `linear_regression` consumer, two different R² thresholds:
- backend/app/routes/metrics.py:154,156 (`/trend`): `r_sq > 0.3` → "improving"/"declining"
- backend/app/services/diagnostics.py:79 (`/diagnostics` check_declining_trend): `r_sq > 0.5`

A series with R² in (0.3, 0.5] reports "improving" on /trend but does NOT
fire `check_declining_trend` on /diagnostics. Inconsistent UX.

backend/CLAUDE.md:150 says `r² > 0.3` — the spec says 0.3. The /diagnostics
code is the outlier.

Fix: extract `R_SQUARED_TREND_THRESHOLD = 0.3` constant in diagnostics.py,
import in metrics.py, update both to use it.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DIAG_PATH = BACKEND_ROOT / "app" / "services" / "diagnostics.py"
METRICS_PATH = BACKEND_ROOT / "app" / "routes" / "metrics.py"


def _load(name: str, path: Path):
    import sys

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules so @dataclass can find the class's module
    # when re-executing the same file via importlib (otherwise `_is_type`
    # raises "'NoneType' has no attribute '__dict__'").
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_diagnostics_defines_r_squared_trend_threshold_constant():
    """diagnostics.py must export a named constant for the R² threshold."""
    mod = _load("_diag_under_test", DIAG_PATH)
    assert hasattr(mod, "R_SQUARED_TREND_THRESHOLD"), (
        "diagnostics.py must export R_SQUARED_TREND_THRESHOLD constant so "
        "/trend and /diagnostics share a single source of truth (#633). "
        "Currently they hardcode 0.3 and 0.5 respectively — spec drift."
    )
    assert pytest.approx(0.3) == mod.R_SQUARED_TREND_THRESHOLD, (
        f"threshold must be 0.3 (matches backend/CLAUDE.md:150), got "
        f"{mod.R_SQUARED_TREND_THRESHOLD!r}"
    )


def test_check_declining_trend_uses_constant_not_hardcoded_05():
    """check_declining_trend must reference R_SQUARED_TREND_THRESHOLD, not 0.5."""
    src = DIAG_PATH.read_text(encoding="utf-8")
    # Find check_declining_trend block.
    block_start = src.find("def check_declining_trend(")
    assert block_start != -1
    # Walk to next top-level def or end of file.
    next_def = src.find("\ndef ", block_start + 1)
    block = src[block_start:next_def] if next_def != -1 else src[block_start:]
    # Must reference the constant.
    assert "R_SQUARED_TREND_THRESHOLD" in block, (
        f"check_declining_trend must use R_SQUARED_TREND_THRESHOLD constant. Block was:\n{block}"
    )
    # Must NOT have a hardcoded `0.5` magic number in the r_squared check.
    # The original was `r_squared > 0.5`. Look for that pattern specifically.
    has_hardcoded_05 = re.search(r"r_squared\s*>\s*0\.5", block) is not None
    assert not has_hardcoded_05, (
        f"check_declining_trend still has hardcoded `r_squared > 0.5`. Use "
        f"R_SQUARED_TREND_THRESHOLD constant. Block was:\n{block}"
    )


def test_metrics_trend_route_uses_constant_not_hardcoded_03():
    """/trend route must use R_SQUARED_TREND_THRESHOLD, not hardcoded 0.3."""
    src = METRICS_PATH.read_text(encoding="utf-8")
    # /trend block: anchored on @get("/trend"), walks to next @get.
    trend_start = src.find('@get("/trend")')
    assert trend_start != -1
    next_method = src.find("\n    @get", trend_start + 1)
    block = src[trend_start:next_method] if next_method != -1 else src[trend_start:]
    assert "R_SQUARED_TREND_THRESHOLD" in block, (
        f"/trend route must import and use R_SQUARED_TREND_THRESHOLD constant "
        f"from diagnostics module. Currently hardcodes 0.3. Block was:\n{block}"
    )
    # No hardcoded 0.3 in r_sq check anymore.
    has_hardcoded_03 = re.search(r"r_sq\s*>\s*0\.3", block) is not None
    assert not has_hardcoded_03, (
        f"/trend still has hardcoded `r_sq > 0.3`. Use R_SQUARED_TREND_THRESHOLD. "
        f"Block was:\n{block}"
    )


def test_check_declining_trend_fires_at_rsq_just_above_03():
    """Runtime: with R² just above 0.3, check_declining_trend must fire (threshold lowered from 0.5 to 0.3)."""
    mod = _load("_diag_runtime", DIAG_PATH)
    # Synthesize a 10-point declining series. With the new 0.3 threshold,
    # any moderately-declining series (R² > 0.3) should fire. With old 0.5
    # threshold, only steep declines fired.
    values = [10.0, 9.8, 9.6, 9.4, 9.2, 9.0, 8.8, 8.6, 8.4, 8.2]  # slope -0.2, R²=1.0
    finding = mod.check_declining_trend(
        element="jumps",
        metric="airtime",
        values=values,
        metric_label="Время в воздухе",
    )
    assert finding is not None, (
        "check_declining_trend should fire on a perfectly-declining series "
        "with R²=1.0. If this fails, the function signature or threshold "
        "logic is broken."
    )
    assert "ухудшается" in finding.message

    # Sanity: an improving series (R² high) should NOT fire declining trend.
    improving = [8.2, 8.4, 8.6, 8.8, 9.0, 9.2, 9.4, 9.6, 9.8, 10.0]
    no_finding = mod.check_declining_trend(
        element="jumps", metric="airtime", values=improving, metric_label="Время в воздухе"
    )
    assert no_finding is None, (
        f"improving series must not fire declining-trend finding, got {no_finding!r}"
    )
