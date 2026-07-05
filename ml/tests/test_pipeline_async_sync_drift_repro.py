"""Regression test: analyze_async must populate profiling like sync analyze.

Issue #619: analyze_async silently drops profiling field — public API drift.
"""

import inspect

import pytest

from src.pipeline import AnalysisPipeline


def test_analyze_async_returns_profiling_field():
    """analyze_async must include profiling= in its AnalysisReport return.

    Source-level assertion: the async `analyze_async` return statement
    must pass `profiling=self._profiler.to_dict()`, matching sync `analyze`.
    """
    src = inspect.getsource(AnalysisPipeline.analyze_async)
    assert "profiling=" in src, (
        "analyze_async return must include profiling= field; "
        "sync analyze() includes it but async drops it (issue #619)"
    )
    assert "self._profiler.to_dict()" in src, (
        "analyze_async must pass profiling=self._profiler.to_dict()"
    )


def test_analyze_async_profiling_value_matches_profiler_dict():
    """analyze_async return contract: profiling field is a dict (not None)."""
    pipeline = AnalysisPipeline()
    pipeline._profiler.record("test_stage", 0.123)
    d = pipeline._profiler.to_dict()

    assert isinstance(d, dict)
    assert d
    assert "stages" in d
    stage_names = {s["name"] for s in d["stages"]}
    assert "test_stage" in stage_names
    recorded = next(s for s in d["stages"] if s["name"] == "test_stage")
    assert recorded["wall_time_s"] == pytest.approx(0.123)
