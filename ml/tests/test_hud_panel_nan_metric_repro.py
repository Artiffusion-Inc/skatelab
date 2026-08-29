"""Repro for #963: HUD metrics panel leaks literal "nan"/"inf" into Russian overlay.

`_format_metric` (ml/src/visualization/hud/coach_panel.py) formats
`metric.value` via f-string format spec (`:.2f`, `:.0f`), which renders
NaN/inf as "nan"/"inf" without raising. The Russian HUD overlay then
burns "Высота: nan ✗" into the annotated video. This repro locks the
contract: the user must never see raw "nan"/"inf" substrings in the
formatted metric value.
"""

import inspect
import math

import pytest

from src.types import MetricResult
from src.visualization.hud.coach_panel import _format_metric

NAUGHTY = ("nan", "inf", "NaN", "Inf", "-inf", "-nan")


def _metric(*, value: float, unit: str = "s") -> MetricResult:
    return MetricResult(
        name="airtime",
        value=value,
        unit=unit,
        is_good=False,
        reference_range=(0.3, 0.7),
    )


def _assert_no_leak(value_str: str) -> None:
    for bad in NAUGHTY:
        assert bad not in value_str, (
            f"literal '{bad}' leaked into formatted metric value: {value_str!r}"
        )


def test_nan_metric_value_renders_placeholder_not_nan():
    _name_ru, value_str, _is_good = _format_metric(_metric(value=float("nan")))
    _assert_no_leak(value_str)


def test_inf_metric_value_renders_placeholder_not_inf():
    _name_ru, value_str, _is_good = _format_metric(_metric(value=float("inf")))
    _assert_no_leak(value_str)


def test_neg_inf_metric_value_renders_placeholder():
    _name_ru, value_str, _is_good = _format_metric(_metric(value=float("-inf")))
    _assert_no_leak(value_str)


def test_finite_values_still_render_correctly():
    """Regression guard: finite values keep .2f/.0f formatting per unit."""
    _, s_sec, _ = _format_metric(_metric(value=0.45, unit="s"))
    assert "0.45" in s_sec and "с" in s_sec

    _, deg_str, _ = _format_metric(_metric(value=90.0, unit="deg"))
    assert "90" in deg_str and "°" in deg_str

    _, norm_str, _ = _format_metric(_metric(value=0.5, unit="norm"))
    assert "0.50" in norm_str

    for s in (s_sec, deg_str, norm_str):
        _assert_no_leak(s)


def test_format_metric_source_has_nan_guard():
    """Lock the root cause: source must use a NaN/inf guard."""
    src = inspect.getsource(_format_metric)
    assert ("isfinite" in src) or ("isnan" in src), (
        "_format_metric has no NaN/inf guard — fix must introduce a "
        "finite-check at the trust boundary (metric dict -> panel text)"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--no-cov"])
