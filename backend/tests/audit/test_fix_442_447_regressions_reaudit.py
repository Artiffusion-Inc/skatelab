"""Adversarial re-audit RED repro: fixes #442-#447 — gaps found in #445.

This test validates the degenerate-math-now-reachable hypothesis for #445:
- Fix #445 (ffa030c3) adds dict-phase reading, which is correct and necessary.
- But before the fix, `getattr` on a dict always returned default 0, so the guard
  `takeoff > 0 and landing > 0` was ALWAYS False, making the `landing_mid` and
  `phase_dicts` code unreachable.
- After the fix, dict phases with valid (positive) boundaries reach the guard.
- If the GPU server emits a dict with REVERSED boundaries (e.g. end < landing,
  or takeoff > landing), the guard passes but `landing_mid` and phase end_frames
  can produce NEGATIVE durations or backwards time ranges.

Specifically:
  landing_mid = landing + max(1, (end - landing) // 2)
  When end < landing, (end - landing) is negative, so max(1, negative) = 1.
  landing_mid = landing + 1. That's technically fine (a 1-frame landing phase).
  But when end == landing, landing_mid = landing + 1, and glide_out has
  start_frame=landing_mid, end_frame=end=landing, so glide_out starts AFTER it
  ends (start > end). The `end_time` < `start_time`.

More critically:
  When takeoff > landing (reversed), the approach phase has
  start_frame=start, end_frame=takeoff, but the air phase has
  start_frame=peak, end_frame=landing. If landing < takeoff, peak (which is
  between takeoff and landing) could be < takeoff, making the takeoff phase
  end_frame=peak < start_frame=takeoff. That's a negative-duration phase.

The GPU server is not guaranteed to emit monotonic phases — ML outputs can have
frame ordering noise, especially with low-confidence detections. The fix should
guard against this.

This test: pass a dict phases with end < landing (reversed) and assert the
function handles it safely (does NOT create negative-duration phases).
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
async def test_dict_phases_reversed_boundaries_no_negative_duration() -> None:
    """Dict phases with reversed boundaries (end < landing) must not produce
    negative-duration glide_out phase. The fix #445 makes dict-path reachable,
    so this degenerate-math bug is now EXPOSED.

    Current behavior (RED):
      landing=60, end=50  -> landing_mid = 60 + max(1, (50-60)//2) = 60 + 1 = 61
      glide_out phase: start_frame=61, end_frame=50  -> negative duration
      start_time=61/30=2.03, end_time=50/30=1.67  -> end_time < start_time
    """
    from app.services.analyzer_save import save_analyzer_results

    db = AsyncMock()
    phases = {
        "name": "waltz_jump",
        "start": 5,
        "takeoff": 30,
        "peak": 45,
        "landing": 60,
        "end": 50,  # REVERSED: end < landing
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
    assert phase_dicts != [], (
        "Fix #445 makes dict-path reachable — non-empty phase_dicts expected for "
        "valid dict input. If empty, the dict-path is still broken (regression)."
    )

    # Check NO phase has end_frame < start_frame (negative duration)
    for p in phase_dicts:
        assert p["end_frame"] >= p["start_frame"], (
            f"BUG: phase '{p['name']}' has reversed frames: "
            f"start={p['start_frame']} > end={p['end_frame']}. "
            "Fix #445 made dict-path reachable, exposing degenerate-math when "
            "GPU emits reversed boundaries. The code must guard against this."
        )

    # Check NO phase has end_time < start_time (negative time)
    for p in phase_dicts:
        assert p["end_time"] >= p["start_time"], (
            f"BUG: phase '{p['name']}' has reversed time: "
            f"start_time={p['start_time']} > end_time={p['end_time']}. "
            "Fix #445 made dict-path reachable, exposing degenerate-math."
        )
