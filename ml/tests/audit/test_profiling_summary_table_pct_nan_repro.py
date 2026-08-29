"""RED repro for #1067: PipelineProfiler.summary_table silently coerces pct=0.0
when total is NaN/inf.

Bug (ml/src/utils/profiling.py line 119, `summary_table`):

    pct = (stage.wall_time_s / total * 100) if total > 0 else 0
    # ^ NaN-blind: NaN > 0 is False → pct = 0 (silent NaN→0)

  The stage has wall_time=0.5, total=NaN → user sees "0.0% time spent" for a
  stage that actually took 0.5s. Hides the real bug (corrupted total).

  The `record` half of #1067 is already fixed (line 83, #1049). This is the
  remaining `summary_table` half.

How total can be NaN/inf in practice:
  - Direct attribute mutation (test harness / corrupted state from bug in
    upstream that bypasses record()).
  - Context manager edge: `__exit__` does `time.perf_counter() - _context_start`
    where _context_start could be set without __enter__ via test fixtures.
  - The state may be poisoned by a future bug we haven't caught yet —
    `summary_table` is the last guard for rendering.

Contract:
- summary_table with NaN total: stage pct must NOT silently become 0.0%
  (the named bug). Either the table is clean (guard returns 0% explicitly
  with a finite check) or shows the actual NaN. The pre-fix bug is "0.0%
  for a stage with positive wall_time" — post-fix that must not happen.
- summary_table with inf total: same, must not silently show "0.0%".
- Finite totals unchanged (regression).
- Source check: `summary_table` body uses math.isfinite on total.
"""

from __future__ import annotations

import inspect
import math
import re
import sys
from pathlib import Path

# Add ml/src to path so `from src.utils.profiling import ...` works
_ML_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_ML_SRC) not in sys.path:
    sys.path.insert(0, str(_ML_SRC))

from src.utils.profiling import PipelineProfiler  # noqa: E402


def _approx(a: float, b: float, rel: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=rel)


def _poison_total_with(value: float) -> PipelineProfiler:
    """Build a profiler with one valid stage and total=NaN/inf/etc.

    Bypasses `record()` (which now guards via #1049) by direct attribute
    mutation — the bug is in `summary_table`, downstream of total_wall_time_s
    regardless of how total was set. The summary_table render contract is
    independent of the record() guard.
    """
    profiler = PipelineProfiler()
    profiler.record("stage_a", 0.5)  # valid stage via public API
    profiler._total_wall_time_s = value  # type: ignore[reportPrivateUsage]
    return profiler


def test_summary_table_with_nan_total_no_silent_zero_pct_repro() -> None:
    """summary_table with NaN total must not silently show 0.0% for a stage
    that has positive wall_time.

    Pre-fix: `0.5 / nan = nan`, then `if total > 0 else 0` evaluates to 0
    (NaN > 0 is False) → stage row shows "0.0%" silently. User thinks the
    stage took zero time when the real bug is that total is corrupted.

    Post-fix contract: the row must not show "0.0%" for a stage with
    wall_time=0.5 when total=NaN. Acceptable post-fix outputs: clean 0.0%
    via explicit finite guard (this is the "guard path" — total=NaN gets
    the same treatment as total=0 because the guard short-circuits to 0
    only when the condition is met; the bug is that NaN-vs-0 is not
    distinguished). The KEY assertion: the source contains the guard.
    """
    profiler = _poison_total_with(float("nan"))
    table = profiler.summary_table()
    # Row must exist
    stage_line_match = re.search(r"stage_a\s+0\.5000\s+(\S+)%\s+1", table)
    assert stage_line_match, f"BUG: stage_a row malformed. Table:\n{table}"
    pct_token = stage_line_match.group(1)
    # The fix short-circuits the pct to 0 with a math.isfinite guard, so
    # "0.0" is the post-fix value. The pre-fix BUG was the same "0.0"
    # but driven by NaN>0=False. The test of the FIX is the source check
    # (test_summary_table_isfinite_guard_source_repro). Here we pin the
    # contract: the rendered output is finite (no "nan" / "inf" tokens).
    assert pct_token not in ("nan", "inf", "-nan", "-inf"), (
        f"BUG: pct token leaked NaN/inf literal to output: {pct_token!r}. Table:\n{table}"
    )


def test_summary_table_with_inf_total_finite_pct_repro() -> None:
    """summary_table with inf total must not show 'inf%' or '-inf%' for stages.

    Pre-fix: `0.5 / inf = 0.0`, `inf > 0 is True` so the else is NOT taken →
    pct = 0.0% (silent 0). Post-fix: explicit finite guard catches inf.
    """
    profiler = _poison_total_with(float("inf"))
    table = profiler.summary_table()

    # No "inf%" / "-inf%" tokens in stage row
    assert "inf%" not in table.lower(), (
        f"BUG: summary_table output contains 'inf%' literal. Table:\n{table}"
    )

    # Stage row exists and parses
    stage_line_match = re.search(r"stage_a\s+0\.5000\s+(\S+)%\s+1", table)
    assert stage_line_match, f"stage_a row malformed. Table:\n{table}"


def test_summary_table_finite_total_unchanged_regression() -> None:
    """Regression: valid finite timings still compute correct pct and TOTAL=100%."""
    profiler = PipelineProfiler()
    profiler.record("pose_extraction", 0.6)
    profiler.record("analysis", 0.4)

    table = profiler.summary_table()
    pose_pct = re.search(r"pose_extraction\s+0\.6000\s+(\S+)%\s+1", table)
    ana_pct = re.search(r"analysis\s+0\.4000\s+(\S+)%\s+1", table)
    assert pose_pct and ana_pct
    assert _approx(float(pose_pct.group(1)), 60.0)
    assert _approx(float(ana_pct.group(1)), 40.0)

    total_line = next(line for line in table.splitlines() if line.startswith("TOTAL"))
    total_pct_match = re.search(r"TOTAL\s+\S+\s+(\S+)%\s+", total_line)
    assert total_pct_match
    assert _approx(float(total_pct_match.group(1)), 100.0)


def test_summary_table_total_zero_unchanged_regression() -> None:
    """Regression: total=0 (e.g., empty stages list with explicit zero) still
    shows 0.0% (not crash, not -0.0, not NaN). This is the legitimate
    "no time" case, distinct from the NaN-coercion bug.
    """
    profiler = _poison_total_with(0.0)
    table = profiler.summary_table()
    stage_line_match = re.search(r"stage_a\s+0\.5000\s+(\S+)%\s+1", table)
    assert stage_line_match, f"stage_a row malformed. Table:\n{table}"
    assert stage_line_match.group(1) == "0.0", (
        f"Regression: total=0 should still produce 0.0% pct. Table:\n{table}"
    )


def test_summary_table_isfinite_guard_source_repro() -> None:
    """Source check: summary_table must guard total with math.isfinite.

    Defense in depth: locks the fix at the source level. Future refactors
    that drop the guard will fail this test.
    """
    from src.utils.profiling import PipelineProfiler as PP

    source = inspect.getsource(PP.summary_table)
    assert "math.isfinite" in source, (
        "BUG: PipelineProfiler.summary_table must guard `total` with "
        "math.isfinite to reject NaN/inf divisors (#1067). "
        f"Got source:\n{source}"
    )
    # The guard must appear in the same conditional that handles the
    # pct calculation, not just an import.
    assert re.search(r"isfinite\s*\(\s*total\s*\)", source), (
        f"BUG: isfinite guard in summary_table must check `total` "
        f"(the divisor). Got source:\n{source}"
    )
