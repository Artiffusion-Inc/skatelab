"""Adversarial re-audit RED repro: #445 made dict-phase path reachable,
#461 added a monotonicity guard, but `end == landing` slips through and
produces a negative-duration glide_out phase.

Bug: when `end == landing`, `landing_mid = landing + max(1, 0//2) = landing + 1`.
The glide_out phase gets `start_frame = landing + 1`, `end_frame = landing`,
i.e. `start_frame > end_frame` -> negative duration. The guard
`start <= takeoff <= peak <= landing <= end` accepts equality at every step,
so `end == landing` is NOT rejected.

Fix: the last inequality should be strict (`landing < end`) or the code should
clamp `landing_mid` to `end`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _stub_score() -> MagicMock:
    score = MagicMock()
    score.subscores = []
    score.overall = 0.5
    score.data_quality = "ok"
    score.skeleton_reliability = "ok"
    return score


@pytest.mark.asyncio
async def test_dict_phases_equal_end_landing_no_negative_glide_out() -> None:
    """When end == landing, glide_out must not have start_frame > end_frame.

    The monotonicity guard (`<=` at every step) accepts `end == landing`,
    but `landing_mid = landing + max(1, (end - landing)//2)` overflows to
    `landing + 1`, making glide_out negative-duration. This is a missed edge
    case in the #461 guard.
    """
    from app.services.analyzer_save import save_analyzer_results

    db = AsyncMock()
    phases = {
        "name": "waltz_jump",
        "start": 5,
        "takeoff": 30,
        "peak": 45,
        "landing": 60,
        "end": 60,  # EQUAL to landing — guard passes but math breaks
    }
    captured: dict = {}

    async def _fake_create_phase(
        _db, *, session_id, phases, overall_confidence, element_type, fallback_used
    ):
        captured["phases"] = phases
        captured["element_type"] = element_type
        captured["fallback_used"] = fallback_used
        return MagicMock()

    with (
        patch(
            "app.services.ml_bridge.compute_subscores_safe",
            return_value=_stub_score(),
        ),
        patch("app.crud.session_phase.create", new=_fake_create_phase),
        patch("app.crud.session_score.create", new_callable=AsyncMock),
    ):
        await save_analyzer_results(
            db,
            session_id="s1",
            metrics=[],
            phases=phases,
            fps=30.0,
        )

    phase_dicts = captured["phases"]
    for p in phase_dicts:
        assert p["end_frame"] >= p["start_frame"], (
            f"BUG: phase '{p['name']}' has reversed frames: "
            f"start={p['start_frame']} > end={p['end_frame']}. "
            f"end==landing ({phases['end']}) is accepted by the monotonicity "
            f"guard but produces landing_mid={phases['landing'] + 1}, which "
            f"exceeds end. The guard or landing_mid calc must handle this."
        )
        assert p["end_time"] >= p["start_time"], (
            f"BUG: phase '{p['name']}' has reversed time: "
            f"start_time={p['start_time']} > end_time={p['end_time']}."
        )
