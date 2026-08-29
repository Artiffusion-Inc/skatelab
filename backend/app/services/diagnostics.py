"""Automatic diagnostic rules engine.

Runs simple statistical checks on session_metrics to surface patterns
for coaches: declining trends, stagnation, instability, PRs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Finding:
    severity: str  # "warning" or "info"
    element: str
    metric: str
    message: str
    detail: str


# #633: single source of truth for the R² threshold used by both /trend
# (backend/app/routes/metrics.py) and check_declining_trend below. Matches
# backend/CLAUDE.md:150 — was 0.3 in /trend, 0.5 in /diagnostics (drift).
R_SQUARED_TREND_THRESHOLD = 0.3


def linear_regression(values: list[float]) -> tuple[float, float]:
    """Return (slope, r_squared) for a simple linear regression.

    #634: filter NaN/inf from `values` at the entry. Without this, one NaN
    poisons the mean → ss_yy → ss_xy → slope (all NaN) and r² falls back
    to 0.0 (NaN > 0 is False, takes the else branch). Downstream consumers
    then classify the series as 'stable' for any R² < threshold, silently
    hiding real regressions in data with even one missing-frame session.
    """
    # Drop NaN/inf so they don't poison the mean and sum-of-squares.
    finite = [v for v in values if math.isfinite(v)]
    n = len(finite)
    if n < 2:
        return 0.0, 0.0
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(finite) / n

    ss_xx = sum((xi - x_mean) ** 2 for xi in x)
    ss_xy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, finite, strict=False))
    ss_yy = sum((yi - y_mean) ** 2 for yi in finite)

    if ss_xx == 0:
        return 0.0, 0.0

    slope = ss_xy / ss_xx
    r_squared = (ss_xy**2) / (ss_xx * ss_yy) if ss_yy > 0 else 0.0
    return slope, r_squared


def check_consistently_below_range(
    *,
    element: str,
    metric: str,
    in_range_flags: list[bool],
    metric_label: str,
    ref_range: tuple[float, float],
) -> Finding | None:
    """Warning when >60% of values are out of ideal range."""
    if len(in_range_flags) < 3:
        return None
    below_count = sum(1 for f in in_range_flags if not f)
    total = len(in_range_flags)
    if below_count / total > 0.6:
        return Finding(
            severity="warning",
            element=element,
            metric=metric,
            message=f"{metric_label}: ниже нормы в {below_count} из {total} последних сессий",
            detail=f"Норма: {ref_range[0]}–{ref_range[1]}",
        )
    return None


def check_declining_trend(
    *,
    element: str,
    metric: str,
    values: list[float],
    metric_label: str,
    direction: str = "higher",
) -> Finding | None:
    """Warning when linear regression shows decline with R² above threshold."""
    if len(values) < 5:
        return None
    slope, r_squared = linear_regression(values)
    is_decline = (slope < 0) if direction == "higher" else (slope > 0)
    if is_decline and math.isfinite(r_squared) and r_squared > R_SQUARED_TREND_THRESHOLD:
        return Finding(
            severity="warning",
            element=element,
            metric=metric,
            message=f"{metric_label}: ухудшается",
            detail=f"Тренд: declining (R²={r_squared:.2f})",
        )
    return None


def check_stagnation(
    *,
    element: str,
    metric: str,
    values: list[float],
    metric_label: str,
) -> Finding | None:
    """Info when standard deviation < 5% of mean."""
    # #692: filter NaN/inf before computing mean
    finite = [v for v in values if math.isfinite(v)]
    if len(finite) < 5:
        return None
    mean = sum(finite) / len(finite)
    if mean == 0:
        return None
    variance = sum((v - mean) ** 2 for v in finite) / len(finite)
    std = variance**0.5
    cv = std / abs(mean)
    if math.isfinite(cv) and cv < 0.05:
        return Finding(
            severity="info",
            element=element,
            metric=metric,
            message=f"{metric_label}: нет улучшений за {len(finite)} сессий",
            detail=f"Среднее: {mean:.3f}, CV: {cv:.1%}",
        )
    return None


def check_new_pr(
    *,
    element: str,
    metric: str,
    is_latest_pr: bool,
    metric_label: str,
    latest_value: float,
    prev_best: float | None,
) -> Finding | None:
    """Info when the most recent session is a PR."""
    if not is_latest_pr:
        return None
    # #693: NaN latest_value renders as "NaN" in UI — skip it
    if not math.isfinite(latest_value):
        return None
    prev_str = f"{prev_best:.3f}" if prev_best is not None else "—"
    return Finding(
        severity="info",
        element=element,
        metric=metric,
        message=f"Новый PR по {metric_label}!",
        detail=f"{latest_value:.3f} (предыдущий: {prev_str})",
    )


def check_high_variability(
    *,
    element: str,
    metric: str,
    values: list[float],
    metric_label: str,
) -> Finding | None:
    """Warning when coefficient of variation > 20%."""
    # #692: filter NaN/inf before computing mean
    finite = [v for v in values if math.isfinite(v)]
    if len(finite) < 5:
        return None
    mean = sum(finite) / len(finite)
    if mean == 0:
        return None
    variance = sum((v - mean) ** 2 for v in finite) / len(finite)
    std = variance**0.5
    cv = std / abs(mean)
    # #1229: NaN-comparison hazard — `NaN > 0.20 == False` silently
    # skips the warning. Guard with isfinite so a corrupt cv is observable
    # (skipped explicitly via the short-circuit), never silent.
    if math.isfinite(cv) and cv > 0.20:
        return Finding(
            severity="warning",
            element=element,
            metric=metric,
            message=f"{metric_label}: сильно колеблется",
            detail=f"CV: {cv:.1%}, среднее: {mean:.3f}",
        )
    return None
