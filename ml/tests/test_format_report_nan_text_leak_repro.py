"""Repro for #981: format_report leaks literal "nan" into Russian text report.

When a metric value or dtw_distance is NaN/inf, the f-string `:.2f`/`:.3f`
format renders "nan"/"inf" into the user-facing Russian text. This repro
locks the contract: the user must never see raw "nan"/"inf" substrings.
"""

import inspect
import math

import pytest

from src.pipeline import AnalysisPipeline
from src.types import AnalysisReport, ElementPhase, MetricResult

NAUGHTY = ("nan", "inf", "NaN", "Inf", "-inf", "-nan")


def _report(
    *, value=0.5, ref_min=0.3, ref_max=0.7, dtw_distance=0.15, overall_score=7.5
) -> AnalysisReport:
    return AnalysisReport(
        element_type="test_element",
        phases=ElementPhase(name="test", start=0, takeoff=10, peak=20, landing=30, end=40),
        metrics=[
            MetricResult(
                name="test_metric",
                value=value,
                unit="s",
                is_good=True,
                reference_range=(ref_min, ref_max),
            )
        ],
        recommendations=["Test recommendation"],
        overall_score=overall_score,
        dtw_distance=dtw_distance,
    )


def _assert_no_leak(text: str) -> None:
    for bad in NAUGHTY:
        assert bad not in text, f"literal '{bad}' leaked into user-facing report: {text!r}"


def test_nan_metric_value_renders_placeholder_not_nan():
    pipeline = AnalysisPipeline()
    report = _report(value=float("nan"))
    formatted = pipeline.format_report(report)
    _assert_no_leak(formatted)


def test_inf_metric_value_renders_placeholder_not_inf():
    pipeline = AnalysisPipeline()
    report = _report(value=float("inf"))
    formatted = pipeline.format_report(report)
    _assert_no_leak(formatted)


def test_nan_reference_range_renders_placeholder():
    pipeline = AnalysisPipeline()
    report = _report(ref_min=float("nan"), ref_max=float("nan"))
    formatted = pipeline.format_report(report)
    _assert_no_leak(formatted)


def test_nan_dtw_distance_renders_placeholder():
    pipeline = AnalysisPipeline()
    report = _report(dtw_distance=float("nan"))
    formatted = pipeline.format_report(report)
    _assert_no_leak(formatted)


def test_finite_values_still_render_correctly():
    """Regression guard: finite values must still render with .2f/.3f."""
    pipeline = AnalysisPipeline()
    report = _report()  # all finite defaults
    formatted = pipeline.format_report(report)
    assert "0.50" in formatted  # metric value 0.5
    assert "0.30-0.70" in formatted  # reference range
    assert "0.150" in formatted  # dtw_distance 0.15
    assert "7.5" in formatted  # overall score
    _assert_no_leak(formatted)


def test_format_report_source_has_nan_guard():
    """Lock the root cause: source must use a NaN/inf guard."""
    src = inspect.getsource(AnalysisPipeline.format_report)
    assert ("isfinite" in src) or ("isnan" in src), (
        "format_report has no NaN/inf guard — fix must introduce np.isfinite "
        "or np.isnan at the trust boundary"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--no-cov"])
