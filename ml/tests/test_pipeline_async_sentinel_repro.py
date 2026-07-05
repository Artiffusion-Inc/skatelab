"""Regression test: analyze_async must preserve None sentinel for unscored reports.

Issue #620: analyze_async silently coerces None→0.0 for both
overall_score and dtw_distance. Sync analyze has the same coercion,
so fix BOTH paths to preserve None.

After fix, the AnalysisReport dataclass has Optional[float] for
overall_score and dtw_distance, and the no-element branch returns
None verbatim.
"""

import inspect

import pytest

from src.pipeline import AnalysisPipeline
from src.types import AnalysisReport, ElementPhase, MetricResult, VideoMeta


def test_analysis_report_overall_score_optional():
    """AnalysisReport.overall_score and dtw_distance must accept None."""
    phases = ElementPhase(name="unknown", start=0, takeoff=0, peak=0, landing=0, end=0)
    report = AnalysisReport(
        element_type="unknown",
        phases=phases,
        metrics=[],
        recommendations=[],
        overall_score=None,
        dtw_distance=None,
    )
    assert report.overall_score is None
    assert report.dtw_distance is None


def test_analyze_async_does_not_coerce_none_to_zero():
    """analyze_async return statement must NOT coerce None to 0.0."""
    src = inspect.getsource(AnalysisPipeline.analyze_async)
    assert "if overall_score is not None else 0.0" not in src, (
        "analyze_async must not coerce None→0.0 for overall_score (issue #620 sentinel collision)"
    )
    assert "if dtw_distance is not None else 0.0" not in src, (
        "analyze_async must not coerce None→0.0 for dtw_distance"
    )
    assert "profiling=self._profiler.to_dict()" in src, (
        "analyze_async must also include profiling= (issue #619)"
    )


def test_analyze_sync_does_not_coerce_none_to_zero():
    """Sync analyze return must also drop the None→0.0 coercion."""
    src = inspect.getsource(AnalysisPipeline.analyze)
    assert "if overall_score is not None else 0.0" not in src, (
        "sync analyze must not coerce None→0.0 for overall_score"
    )
    assert "if dtw_distance is not None else 0.0" not in src, (
        "sync analyze must not coerce None→0.0 for dtw_distance"
    )


def test_analysis_report_format_handles_none_scores():
    """format() must not crash when overall_score or dtw_distance is None."""
    phases = ElementPhase(name="unknown", start=0, takeoff=0, peak=0, landing=0, end=0)
    report = AnalysisReport(
        element_type="unknown",
        phases=phases,
        metrics=[],
        recommendations=[],
        overall_score=None,
        dtw_distance=None,
    )
    text = report.format()
    assert "н/д" in text or "n/a" in text.lower()
    # Must not raise TypeError on None
    assert "Общий балл" in text
    assert "DTW" in text
