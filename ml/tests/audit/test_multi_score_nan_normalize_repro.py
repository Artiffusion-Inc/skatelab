"""Repro tests — multi_score._normalize clips NaN to 1.0 ceiling (#850).

``_normalize`` (multi_score.py:8-10) uses bare ``max(0.0, min(1.0, ...))``.
Python ``min(1.0, float('nan'))`` returns ``1.0`` (NaN comparison is always
False → non-NaN wins), then ``max(0.0, 1.0) = 1.0``. So a missing/failed
metric normalizes to the PERFECT score, not neutral 0.0. This inflates every
subscore and the overall to 10.0 for a session that produced zero valid
measurements — farmable XP / gold skills / fake PRs.

Fix (#850): treat NaN as missing → return 0.0 (neutral), not the ceiling.

Tests:
  - observable: _normalize(nan) == 0.0 (RED: 1.0).
  - observable: all-NaN metrics session → overall NOT 10.0 (RED: 10.0).
  - observable: one-NaN-metric does not inflate its subscore to ceiling.
  - source-asserting: _normalize source has a NaN guard.
"""

from __future__ import annotations

import pytest

from ml.src.analysis.multi_score import _normalize, compute_subscores


def test_normalize_nan_is_neutral_zero_repro():
    """#850: _normalize(float('nan')) must be 0.0 (missing = neutral), not 1.0."""
    val = _normalize(float("nan"))
    assert val == 0.0, (
        f"#850 RED: _normalize(nan)={val} — NaN clips to 1.0 (perfect), should be 0.0 (neutral)."
    )


def test_all_nan_metrics_not_perfect_repro():
    """#850: a session with all-NaN metrics must NOT score overall=10.0."""
    nan = float("nan")
    metrics = {
        "airtime": nan,
        "relative_jump_height": nan,
        "approach_direction_change": nan,
        "rotation_speed": nan,
        "total_rotation_deg": nan,
        "under_rotation_deg": nan,
        "arm_position_score": nan,
        "symmetry": nan,
        "landing_knee_angle": nan,
        "landing_knee_stability": nan,
        "landing_smoothness": nan,
        "hard_landing": nan,
        "landing_trunk_recovery": nan,
        "approach_torso_lean": nan,
        "trunk_lean": nan,
    }
    score = compute_subscores(metrics)
    assert score.overall < 10.0, (
        f"#850 RED: all-NaN metrics → overall={score.overall} (perfect 10.0) — "
        "broken session farms max XP + gold skills."
    )
    # And no subscore should be the ceiling 10.0 from NaN inflation.
    for s in score.subscores:
        assert s.value < 10.0, f"#850 RED: subscore {s.name}={s.value} — NaN clipped to 1.0 → 10.0."


def test_one_nan_metric_does_not_inflate_subscore_repro():
    """#850: a single NaN metric in a subscore's weighted sum must not push the
    whole subscore to the 10.0 ceiling via NaN→1.0 clipping."""
    nan = float("nan")
    # takeoff_power = _normalize(airtime/0.7*0.4 + height/1.0*0.4 + approach_term*0.2)
    # airtime=NaN propagates → sum=NaN → _normalize(NaN). Must not be 10.0.
    metrics = {
        "airtime": nan,
        "relative_jump_height": 0.4,
        "approach_direction_change": 5.0,
    }
    score = compute_subscores(metrics)
    takeoff = next(s for s in score.subscores if s.name == "takeoff_power")
    assert takeoff.value < 10.0, (
        f"#850 RED: takeoff_power={takeoff.value} — one NaN metric (airtime) "
        "inflated the whole subscore to 10.0 via NaN→1.0 clip."
    )


def test_normalize_source_has_nan_guard_repro():
    """#850 GREEN: _normalize source must guard NaN before the clamp."""
    import inspect

    src = inspect.getsource(_normalize)
    assert "isnan" in src or "math.isnan" in src, (
        "#850: _normalize has no NaN guard — NaN passes through min()/max() "
        "and clips to 1.0 (perfect). Add `if math.isnan(value): return 0.0`."
    )
