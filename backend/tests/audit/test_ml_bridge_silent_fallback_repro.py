"""Regression test for #648 — ml_bridge silent 5.0/10 fallback.

Bug: `compute_subscores_safe` catches any Exception from
`src.analysis.multi_score.compute_subscores` and returns a hardcoded
5.0/10 fallback. The fallback is the exact middle of the 0-10 scale,
indistinguishable from a real ML result of 5.0. Downstream consumers
(training_plan, gamification, metrics) only look at `overall` and
treat 5.0 as a real value.

Fix: when ML fails, return a sentinel `MultiDimensionalScore` with
`overall=NaN`, `data_quality='failed'`,
`skeleton_reliability='unreliable'` — distinguishable from a real
"partial" / 5.0 result.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from contextlib import contextmanager
from pathlib import Path

# ---------------------------------------------------------------------------
# Source-level guard: top of file must contain a comment referencing #648
# and the function must raise/return None on the failure path (no
# hardcoded 5.0 fallback).
# ---------------------------------------------------------------------------

_SRC_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "services" / "ml_bridge.py"


def test_ml_bridge_source_has_fix_comment():
    """Source must mention #648 so future audits can find the fix site."""
    src = _SRC_FILE.read_text(encoding="utf-8")
    assert "#648" in src, (
        "BUG #648: ml_bridge.py has no #648 reference — silent 5.0/10 "
        "fallback is the documented bug site."
    )


def test_ml_bridge_no_silent_5_fallback():
    """compute_subscores_safe must NOT return a 5.0 fallback on failure.

    Either it raises, or it returns None. A literal 5.0 is the bug.
    """
    src = _SRC_FILE.read_text(encoding="utf-8")
    # The hardcoded fallback pattern (overall=5.0) inside an except
    # branch is the trap. After the fix the except branch must either
    # `raise` or `return None` — never silently substitute a fake score.
    assert "overall=5.0" not in src, (
        "BUG #648: ml_bridge still hardcodes overall=5.0 in the except "
        "branch — silent fallback indistinguishable from real 5.0."
    )


# ---------------------------------------------------------------------------
# Runtime check: force the failure path and confirm the result is
# distinguishable from a real 5.0.
# ---------------------------------------------------------------------------


def _load_ml_bridge():
    """Load `app.services.ml_bridge` via importlib (skip package chain)."""
    spec = importlib.util.spec_from_file_location("app.services.ml_bridge", _SRC_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def _failing_compute_subscores():
    """Monkey-patch `src.analysis.multi_score.compute_subscores` to raise
    on call. Restores the original after the context exits."""
    from src.analysis import multi_score  # real module

    original = multi_score.compute_subscores

    def _raise_compute_subscores(_metrics):
        raise RuntimeError("forced ML failure for #648 repro")

    multi_score.compute_subscores = _raise_compute_subscores
    try:
        yield
    finally:
        multi_score.compute_subscores = original


def test_ml_bridge_fallback_distinguishable_from_real_5():
    """When ML fails, the function result must NOT be the bug-pattern
    5.0/partial. The post-#648 contract: NaN overall, data_quality='failed'."""
    mod = _load_ml_bridge()
    metrics = {"airtime": float("nan"), "rotation_speed": 0.5}
    with _failing_compute_subscores():
        result = mod.compute_subscores_safe(metrics)
    # NaN overall is the discriminator — distinct from a real 5.0.
    assert math.isnan(result.overall), (
        f"BUG #648: ml_bridge fallback overall={result.overall!r} — must "
        f"be NaN so downstream consumers can detect the failure."
    )
    assert result.overall != 5.0, (
        "BUG #648: ml_bridge fallback returned overall=5.0 — "
        "indistinguishable from a real 5.0 score."
    )


def test_ml_bridge_fallback_uses_distinct_markers():
    """On ML failure, data_quality='failed' and
    skeleton_reliability='unreliable' (not 'partial' / 'uncertain')."""
    mod = _load_ml_bridge()
    metrics = {"airtime": float("nan"), "rotation_speed": 0.5}
    with _failing_compute_subscores():
        result = mod.compute_subscores_safe(metrics)
    assert result.data_quality == "failed", (
        f"BUG #648: on ML failure, data_quality must be 'failed' "
        f"(got {result.data_quality!r}) so consumers can detect the fallback."
    )
    assert result.skeleton_reliability == "unreliable", (
        f"BUG #648: on ML failure, skeleton_reliability must be "
        f"'unreliable' (got {result.skeleton_reliability!r})."
    )
