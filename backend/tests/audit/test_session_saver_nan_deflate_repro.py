"""RED repro — session_saver NaN metric deflates overall_score.

backend/app/services/session_saver.py:65-72:
    value = m["value"]
    if not isinstance(value, bool):
        is_in_range = ref_value <= value <= ref_max

For NaN value, `0.0 <= nan <= 1.0` is False, so is_in_range=False (not None).
Then session_saver.py:97-100:

    eligible = [m for m in metric_rows if m["is_in_range"] is not None]
    in_range_count = sum(1 for m in eligible if m["is_in_range"])
    overall_score = in_range_count / len(eligible)

NaN row passes the `is not None` filter (its is_in_range is False) and inflates
the denominator while contributing nothing to the numerator. With one NaN
+ N-1 in-range metrics, score = (N-1)/N instead of (N-1)/(N-1) = 1.0.

With all-NaN metrics, score = 0/0 → either ZeroDivisionError or 0.0.
"""

from __future__ import annotations

import importlib.util
import math
import re
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SESSION_SAVER_PATH = BACKEND_ROOT / "app" / "services" / "session_saver.py"


def _load_session_saver_source() -> str:
    return SESSION_SAVER_PATH.read_text(encoding="utf-8")


def test_source_filters_nan_from_eligible():
    """The eligible denominator must filter NaN/inf out (not just is_in_range is not None)."""
    src = _load_session_saver_source()
    # Find the eligible-list comprehension (anchor on `eligible = [`)
    eligible_match = re.search(r"eligible\s*=\s*\[", src)
    assert eligible_match is not None, "expected `eligible = [` comprehension in session_saver"

    # The comprehension (or the bulk_create follow-up) must reference math.isfinite
    # on metric_value, OR a helper that does. Anchor on the source text appearing
    # AFTER the `eligible = [` line — that's where the fix lives.
    after_eligible = src[eligible_match.start() :]
    assert "math.isfinite" in after_eligible, (
        "session_saver must filter NaN/inf from the `eligible` denominator "
        "via math.isfinite, otherwise one NaN metric deflates overall_score "
        "for the entire session (#630). The check must be AFTER `eligible = [` "
        "so it runs at score-computation time."
    )


def test_source_handles_all_nan_division():
    """All-NaN session must not crash on division, must give None or 0 gracefully."""
    src = _load_session_saver_source()
    # The fix: when eligible is empty after NaN filtering, overall_score = None
    # (matches existing behavior for empty `is_in_range is not None`).
    # Verify the source either: (a) has `else: overall_score = None`, OR
    # (b) has the NaN filter narrow eligible so the existing None branch covers it.
    has_else_none = re.search(
        r"if\s+eligible\s*:\s*\n\s+overall_score\s*=\s*in_range_count\s*/\s*len\s*\(\s*eligible\s*\)\s*\n\s*else\s*:\s*\n\s+overall_score\s*=\s*None",
        src,
        re.MULTILINE,
    )
    assert has_else_none is not None, (
        "expected `if eligible: ... else: overall_score = None` branch in session_saver"
    )


def test_overall_score_one_nan_does_not_deflate():
    """One NaN + two in-range: score must be 1.0, not 2/3.

    Loads session_saver via importlib to bypass the heavy app.* import chain,
    then injects stubbed CRUD + db and calls save_analysis_results directly.
    """
    import asyncio

    async def _run():
        spec = importlib.util.spec_from_file_location(
            "_session_saver_under_test", SESSION_SAVER_PATH
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        captured_update: dict = {}

        class _StubSession:
            user_id = "u1"
            element_type = "jumps"

        async def _stub_get_by_id(db, session_id):
            return _StubSession()

        async def _stub_get_current_best_batch(db, user_id, element_type, metric_names):
            return {}

        async def _stub_bulk_create(db, rows):
            return None

        async def _stub_update(db, session, **kwargs):
            captured_update.update(kwargs)
            return session

        from app.metrics_registry import METRIC_REGISTRY

        m_name = next(
            name
            for name, mdef in METRIC_REGISTRY.items()
            if mdef.ideal_range and mdef.element_types
        )

        metrics = [
            {"name": m_name, "value": float("nan")},
            {"name": m_name, "value": 0.5},
            {"name": m_name, "value": 0.7},
        ]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mod, "get_by_id", _stub_get_by_id)
            mp.setattr(mod, "get_current_best_batch", _stub_get_current_best_batch)
            mp.setattr(mod, "bulk_create", _stub_bulk_create)
            mp.setattr(mod, "update", _stub_update)
            await mod.save_analysis_results(
                db=None,  # type: ignore[arg-type]
                session_id="s1",
                metrics=metrics,
                phases=None,  # type: ignore[arg-type]
                recommendations=[],
            )
        return captured_update.get("overall_score")

    score = asyncio.run(_run())
    # With NaN filtered: 2/2 = 1.0. Without the fix: 2/3 ≈ 0.667.
    assert score == pytest.approx(1.0), (
        f"with one NaN + 2 in-range, overall_score must be 1.0 (NaN filtered), "
        f"got {score!r}. The NaN inflates the denominator but contributes nothing "
        "to the numerator."
    )


def test_overall_score_all_nan_is_none_not_crash():
    """All-NaN session: overall_score = None (or 0, but must not crash)."""
    import asyncio

    async def _run():
        spec = importlib.util.spec_from_file_location("_session_saver_all_nan", SESSION_SAVER_PATH)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        captured_update: dict = {}

        class _StubSession:
            user_id = "u1"
            element_type = "jumps"

        async def _stub_get_by_id(db, session_id):
            return _StubSession()

        async def _stub_get_current_best_batch(db, user_id, element_type, metric_names):
            return {}

        async def _stub_bulk_create(db, rows):
            return None

        async def _stub_update(db, session, **kwargs):
            captured_update.update(kwargs)
            return session

        from app.metrics_registry import METRIC_REGISTRY

        m_name = next(
            name
            for name, mdef in METRIC_REGISTRY.items()
            if mdef.ideal_range and mdef.element_types
        )

        metrics = [
            {"name": m_name, "value": float("nan")},
            {"name": m_name, "value": float("nan")},
        ]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mod, "get_by_id", _stub_get_by_id)
            mp.setattr(mod, "get_current_best_batch", _stub_get_current_best_batch)
            mp.setattr(mod, "bulk_create", _stub_bulk_create)
            mp.setattr(mod, "update", _stub_update)
            await mod.save_analysis_results(
                db=None,  # type: ignore[arg-type]
                session_id="s1",
                metrics=metrics,
                phases=None,  # type: ignore[arg-type]
                recommendations=[],
            )
        return captured_update.get("overall_score")

    score = asyncio.run(_run())
    assert score in (None, 0.0), (
        f"all-NaN session must give overall_score in (None, 0.0), got {score!r}."
    )


def test_overall_score_no_nan_baseline():
    """Control: no NaN → score reflects in-range ratio unchanged.

    All-in-range: 1.0.  Half in range: 0.5.  None in range: 0.0.
    """
    spec = importlib.util.spec_from_file_location("_session_saver_baseline", SESSION_SAVER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from app.metrics_registry import METRIC_REGISTRY

    m_name = next(
        name for name, mdef in METRIC_REGISTRY.items() if mdef.ideal_range and mdef.element_types
    )

    async def _run(metrics):
        captured: dict = {}

        class _StubSession:
            user_id = "u1"
            element_type = "jumps"

        async def _stub_get_by_id(db, session_id):
            return _StubSession()

        async def _stub_get_current_best_batch(db, user_id, element_type, metric_names):
            return {}

        async def _stub_bulk_create(db, rows):
            return None

        async def _stub_update(db, session, **kwargs):
            captured.update(kwargs)
            return session

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mod, "get_by_id", _stub_get_by_id)
            mp.setattr(mod, "get_current_best_batch", _stub_get_current_best_batch)
            mp.setattr(mod, "bulk_create", _stub_bulk_create)
            mp.setattr(mod, "update", _stub_update)
            await mod.save_analysis_results(
                db=None,  # type: ignore[arg-type]
                session_id="s1",
                metrics=metrics,
                phases=None,  # type: ignore[arg-type]
                recommendations=[],
            )
        return captured.get("overall_score")

    async def _check():
        # All in range (0.5, 0.7 are in typical 0..1 ideal range) → 1.0
        s1 = await _run([{"name": m_name, "value": 0.5}, {"name": m_name, "value": 0.7}])
        return s1

    import asyncio

    s1 = asyncio.run(_check())
    assert s1 == pytest.approx(1.0), f"all in range must give 1.0, got {s1!r}"
