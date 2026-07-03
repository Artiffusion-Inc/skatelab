"""RED repro — rotation_discrepancy emitted as bool but registry
ideal_range=(0,0) → 0 <= True(1) <= 0 → is_in_range=False → deflates
overall_score (perfect jump 0.9 not 1.0). #432-class + bool type-confusion.

BUG #2 (HIGH — rotation_discrepancy bool type-confusion deflates overall_score):
    backend/app/metrics_registry.py:264  rotation_discrepancy
        ideal_range=(0, 0), unit="score"
    ml/src/analysis/metrics.py:374,381,408  ML emits rotation_discrepancy
        as Python **bool** (`discrepancy > 0.5`).
    backend/app/services/session_saver.py:66  `0 <= value <= 0`
        → for True (==1): `0 <= 1 <= 0` → is_in_range=False.
    It's a REGISTERED metric (is_in_range not None) → enters overall_score
        denominator (session_saver.py:91).
    Perfect jump with rotation_discrepancy=True → overall_score=0.9 instead
        of 1.0. Downstream gamification XP/skill-unlock capped.

Existing test_save_score_mismatch.py (#432) tests UNREGISTERED metrics
(is_in_range=None). This is a REGISTERED metric with a degenerate range —
different angle, same #432 deflation class + bool type-confusion
(True==1 in a numeric range comparison).

This test asserts a perfect jump (9 in-range registry metrics +
rotation_discrepancy=True) reports overall_score == 1.0. It currently
reports 0.9 (rotation_discrepancy bool counted as out-of-range in the
denominator) → assert fails → RED.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class FakeMetricResult:
    name: str
    value: float


# Registry-covered jump metrics with ideal ranges (metrics_registry.py),
# values chosen inside the ideal range so is_in_range is True for each.
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


def _make_session():
    session = MagicMock()
    session.user_id = "user-1"
    session.element_type = "waltz_jump"
    return session


@pytest.mark.asyncio
async def test_perfect_jump_not_deflated_by_rotation_discrepancy_bool():
    """A jump where every registry-covered metric is inside its ideal range
    AND rotation_discrepancy=True (a registered metric ML emits as a Python
    bool) must report overall_score == 1.0, not 0.9.

    rotation_discrepancy is REGISTERED (metrics_registry.py:264
    ideal_range=(0,0)). session_saver.py:66 computes
    `0 <= value <= 0` → for True (==1): `0 <= 1 <= 0` → is_in_range=False.
    Because is_in_range is not None, the metric enters the overall_score
    denominator (session_saver.py:91): 9 in-range + 1 out-of-range over 10
    eligible = 0.9, deflating an otherwise perfect jump.

    bool type-confusion: True==1 in a numeric range comparison. Same
    deflation chain as #432 (overall_score denominator) + #437 (gamification
    XP capped) + inverted-scale class #421/#434.
    """
    from app.services.session_saver import save_analysis_results

    db = AsyncMock()
    session = _make_session()

    metrics = [FakeMetricResult(n, v) for n, v in _JUMP_IN_RANGE_METRICS]
    # ML emits rotation_discrepancy as a Python bool (metrics.py:381
    # `discrepancy > 0.5`). value=True is the production shape.
    metrics.append(FakeMetricResult("rotation_discrepancy", True))

    with (
        patch("app.services.session_saver.get_by_id", return_value=session),
        patch("app.services.session_saver.get_current_best_batch", return_value={}),
        patch("app.services.session_saver.bulk_create"),
        patch("app.services.session_saver.update") as mock_update,
    ):
        await save_analysis_results(
            db,
            session_id="sess-perfect-rd",
            metrics=metrics,
            phases=MagicMock(),
            recommendations=[],
        )

    overall = mock_update.call_args[1]["overall_score"]
    assert overall == 1.0, (
        f"perfect jump (9 registry metrics in range + rotation_discrepancy=True) "
        f"reports overall_score={overall}, expected 1.0. "
        f"rotation_discrepancy is REGISTERED (metrics_registry.py:264 "
        f"ideal_range=(0,0)) and ML emits it as a Python bool "
        f"(metrics.py:381 `discrepancy > 0.5`). session_saver.py:66 "
        f"`0 <= True(1) <= 0` → is_in_range=False → enters the denominator "
        f"as out-of-range (9/10 = 0.9). bool type-confusion + #432-class "
        f"deflation. Gamification XP/skill-unlock thresholds capped below "
        f"their intended max for an otherwise perfect session with an "
        f"under-rotated jump (rotation_discrepancy=True is common)."
    )
