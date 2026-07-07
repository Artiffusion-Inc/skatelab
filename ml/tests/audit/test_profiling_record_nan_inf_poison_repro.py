"""RED repro for #1049: PipelineProfiler.record NaN/inf wall_time bypasses 0 guard.

Bug: `if wall_time_s < 0` is NaN-blind and inf-blind. NaN<0 and inf<0 are both
False, so NaN/inf pass the guard and poison `stage.wall_time_s`. Downstream
`to_dict()` then produces a dict that crashes `json.dumps(allow_nan=False)`
(strict JSON consumers like logging, /profiling endpoint, debug dump).

These tests assert the contract:
- record(NaN) raises ValueError (state not mutated)
- record(inf) raises ValueError (state not mutated)
- record(0) still rejected (existing contract regression)
- record(1.5) still works (normal happy path regression)
- Source contains isfinite guard at top of record (defense in depth)
"""

from __future__ import annotations

import contextlib
import inspect
import json
import math
import sys
from pathlib import Path

# Add ml/src to path so `from src.utils.profiling import ...` works
_ML_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_ML_SRC) not in sys.path:
    sys.path.insert(0, str(_ML_SRC))

from src.utils.profiling import PipelineProfiler  # noqa: E402


def _approx(a: float, b: float, rel: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=rel)


def test_record_nan_wall_time_raises_value_error_repro() -> None:
    """record(name, NaN) must raise ValueError, not poison state."""
    profiler = PipelineProfiler()

    raised = False
    try:
        profiler.record("stage_a", float("nan"))
    except ValueError:
        raised = True

    assert raised, "record(NaN) must raise ValueError (NaN<0 is False, guard bypassed)"

    # State must NOT be poisoned
    assert profiler.stages == [], f"state poisoned by NaN: {profiler.stages!r}"
    assert profiler.total_wall_time_s == 0.0


def test_record_inf_wall_time_raises_value_error_repro() -> None:
    """record(name, inf) must raise ValueError, not poison state."""
    profiler = PipelineProfiler()

    raised = False
    try:
        profiler.record("stage_a", float("inf"))
    except ValueError:
        raised = True

    assert raised, "record(inf) must raise ValueError (inf<0 is False, guard bypassed)"

    # State must NOT be poisoned
    assert profiler.stages == [], f"state poisoned by inf: {profiler.stages!r}"
    assert profiler.total_wall_time_s == 0.0


def test_to_dict_after_nan_poison_crash_strict_json_repro() -> None:
    """After record(NaN), to_dict() must remain JSON-serializable with allow_nan=False.

    This is the downstream symptom: strict consumers (logging, /profiling
    endpoint, debug dump) crash when to_dict() leaks NaN/inf.
    """
    profiler = PipelineProfiler()

    # Before fix: NaN passes guard, poisons stage.wall_time_s, breaks json.dumps(allow_nan=False)
    with contextlib.suppress(ValueError):
        profiler.record("stage_a", float("nan"))

    # Strict JSON must succeed (no NaN/inf leaked)
    dumped = json.dumps(profiler.to_dict(), allow_nan=False)
    assert "NaN" not in dumped
    assert "Infinity" not in dumped


def test_record_zero_passes_regression() -> None:
    """Regression: 0 is allowed (existing contract — current guard `wall_time_s < 0`
    is False for 0, so 0 currently passes). Pin current behavior."""
    profiler = PipelineProfiler()

    raised = False
    try:
        profiler.record("test", 0.0)
    except ValueError:
        raised = True

    # Current contract: 0 is allowed (only `< 0` rejected)
    assert not raised, "record(0) should still pass (existing contract)"

    assert len(profiler.stages) == 1
    assert profiler.stages[0].wall_time_s == 0.0


def test_record_valid_wall_time_unchanged_regression() -> None:
    """Regression: normal positive finite wall_time is recorded as before."""
    profiler = PipelineProfiler()

    profiler.record("pose_extraction", 1.23)
    profiler.record("analysis", 0.45)

    assert len(profiler.stages) == 2
    assert profiler.stages[0].wall_time_s == 1.23
    assert profiler.stages[1].wall_time_s == 0.45
    assert _approx(profiler.total_wall_time_s, 1.68)

    # Strict JSON serialization must work
    dumped = json.dumps(profiler.to_dict(), allow_nan=False)
    parsed = json.loads(dumped)
    assert _approx(parsed["total_wall_time_s"], 1.68)


def test_record_unguarded_nan_inf_source_repro() -> None:
    """Source check: `record` body must contain a math.isfinite guard.

    Prevents regression to NaN-blind `< 0` check.
    """
    from src.utils.profiling import PipelineProfiler as PP

    source = inspect.getsource(PP.record)
    assert "math.isfinite" in source, (
        "PipelineProfiler.record must guard with math.isfinite to reject NaN/inf. "
        f"Got source:\n{source}"
    )
