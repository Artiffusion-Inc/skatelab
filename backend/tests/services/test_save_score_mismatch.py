"""Repro tests for overall_score denominator bug (#432).

session_saver.save_analysis_results computed overall_score as
in_range_count / len(metric_rows). Unregistered ML metrics (is_in_range=None)
inflated the denominator without contributing to the numerator, deflating the
score for an otherwise perfect session. Fix: denominator = count of metrics
WITH a registry ideal range (is_in_range is not None).
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class FakeMetricResult:
    name: str
    value: float


# Registry-covered jump metrics with ideal ranges (metrics_registry.py), values
# chosen inside the ideal range so is_in_range is True for each.
_JUMP_IN_RANGE_METRICS = [
    ("airtime", 0.5),
    ("max_height", 0.3),
    ("relative_jump_height", 0.7),
    ("landing_knee_angle", 110.0),
    ("landing_knee_stability", 0.7),
    ("landing_trunk_recovery", 0.7),
    ("arm_position_score", 0.7),
    ("rotation_speed", 400.0),
    ("symmetry", 0.7),
]

# ML jump metrics NOT in METRIC_REGISTRY -> is_in_range=None, but still counted
# in len(metric_rows) under the buggy denominator.
_UNREGISTERED_ML_METRICS = [
    ("landing_com_velocity", 1.2),
    ("landing_smoothness", 0.6),
    ("hard_landing", 0.2),
    ("toe_assist_proxy", 0.0),
    ("approach_torso_lean", 12.0),
    ("approach_direction_change", 30.0),
    ("goe_score", 2.0),
]


def _make_session():
    session = MagicMock()
    session.user_id = "user-1"
    session.element_type = "waltz_jump"
    return session


@pytest.mark.asyncio
async def test_perfect_jump_overall_score_not_deflated_by_unregistered_metrics():
    """A jump where every registry-covered metric is inside its ideal range must
    report overall_score == 1.0, not a deflated fraction. Unregistered ML metrics
    must NOT penalize the score. #432"""
    from app.services.session_saver import save_analysis_results

    db = AsyncMock()
    session = _make_session()

    metrics = [FakeMetricResult(n, v) for n, v in _JUMP_IN_RANGE_METRICS]
    metrics += [FakeMetricResult(n, v) for n, v in _UNREGISTERED_ML_METRICS]

    with (
        patch("app.services.session_saver.get_by_id", return_value=session),
        patch("app.services.session_saver.get_current_best_batch", return_value={}),
        patch("app.services.session_saver.bulk_create"),
        patch("app.services.session_saver.update") as mock_update,
    ):
        await save_analysis_results(
            db,
            session_id="sess-perfect",
            metrics=metrics,
            phases=MagicMock(),
            recommendations=[],
        )

    overall = mock_update.call_args[1]["overall_score"]
    assert overall == 1.0, (
        f"perfect jump (all registry metrics in range) reports overall_score={overall}, "
        f"deflated by {len(_UNREGISTERED_ML_METRICS)} unregistered ML metrics in the "
        "denominator. Gamification XP and skill-unlock thresholds are capped below "
        "their intended max for an otherwise perfect session."
    )


@pytest.mark.asyncio
async def test_overall_score_denominator_excludes_metrics_without_ideal_range():
    """overall_score must be in_range / count(metrics WITH an ideal range), not
    in_range / count(all metrics). Mix: 1 in range, 1 out, 7 unregistered ->
    1/2 = 0.5 (buggy: 1/9 = 0.11). #432"""
    from app.services.session_saver import save_analysis_results

    db = AsyncMock()
    session = _make_session()

    metrics = [
        FakeMetricResult("airtime", 0.5),  # in range (0.3, 0.7)
        FakeMetricResult("rotation_speed", 200.0),  # out of range (300, 550)
    ]
    metrics += [FakeMetricResult(n, v) for n, v in _UNREGISTERED_ML_METRICS]

    with (
        patch("app.services.session_saver.get_by_id", return_value=session),
        patch("app.services.session_saver.get_current_best_batch", return_value={}),
        patch("app.services.session_saver.bulk_create"),
        patch("app.services.session_saver.update") as mock_update,
    ):
        await save_analysis_results(
            db,
            session_id="sess-mixed",
            metrics=metrics,
            phases=MagicMock(),
            recommendations=[],
        )

    overall = mock_update.call_args[1]["overall_score"]
    assert abs(overall - 0.5) < 1e-9, (
        f"mixed 1-in/1-out + 7 unregistered -> overall_score={overall}; "
        "expected 0.5 (in_range / count(metrics WITH ideal range)). "
        "Current code divides by all metric rows, deflating the score."
    )
