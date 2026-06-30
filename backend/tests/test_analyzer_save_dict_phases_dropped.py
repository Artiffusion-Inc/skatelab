"""RED repro: save_analyzer_results drops ALL phase data in the prod Vast.ai path.

The only production caller (worker.py:494) passes ``vast_result.phases``. In the
Vast.ai Serverless path that backs this worker, the GPU server serializes phases
as ``phases.__dict__`` (ml/gpu_server/server.py:574) — a plain ``dict``::

    {"name": "waltz_jump", "start": 5, "takeoff": 30, "peak": 45,
     "landing": 60, "end": 70}

The backend VastResult holds that dict verbatim
(``VastResult.phases = result.get("phases")``, app/vastai/client.py:188) — it is
NOT reconstructed into an ElementPhase dataclass.

``save_analyzer_results`` (app/services/analyzer_save.py:85-93) reads phases with
attribute access::

    element_type = getattr(phases, "name", None)
    takeoff = getattr(phases, "takeoff", 0) or 0
    landing = getattr(phases, "landing", 0) or 0
    ...
    if takeoff > 0 and landing > 0:   # <-- phase-dict generation guard

On a ``dict``, ``getattr(d, "takeoff", 0)`` returns the default ``0`` for EVERY
field (dicts expose keys via ``d["takeoff"]``, not ``d.takeoff``). So in the prod
path the guard is ALWAYS ``0 > 0 and 0 > 0`` == False, and:

  - ``phase_dicts`` stays ``[]`` → ``create_phase`` is called with an empty list,
    so NO SessionPhase rows are ever written for Vast.ai-processed sessions.
  - ``element_type`` is ``None`` → the downstream ``compose_isu_element_type``
    (worker.py:507) gets ``None`` and the session's element_type is never
    derived from the detected phases.
  - ``fallback_used=phase_dicts == []`` is True → the phase row records a
    "fallback" even though the GPU returned valid, non-degenerate phases.

This silently drops all phase data for every session processed via Vast.ai
Serverless (the documented production GPU path, CLAUDE.md "Remote GPU
Processing"). The function's signature/docstring claim it takes an
``ElementPhase``, but the only prod caller passes a dict, so the attribute-style
access never reads the dict's keys.

The sibling ``_metrics_to_dict`` (same file, lines 11-19) handles BOTH shapes
(``isinstance(m, dict)`` branch vs ``m.name``), proving the codebase knows
metrics arrive as dicts from Vast.ai — phases were simply not given the same
dual-shape treatment.

Fix: read phases dict-style when ``isinstance(phases, dict)``
(``phases["takeoff"]``), or normalize the dict to ElementPhase at the
``VastResult`` boundary in ``app/vastai/client.py:188`` before it reaches the
saver (mirrors how ``_metrics_to_dict`` normalizes metrics).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _stub_score() -> MagicMock:
    """Stub compute_subscores_safe return so no ML import is needed."""
    score = MagicMock()
    score.subscores = []
    score.overall = 0.5
    score.data_quality = "ok"
    score.skeleton_reliability = "ok"
    return score


def _prod_phases_dict() -> dict:
    """The exact shape the GPU server emits via ``phases.__dict__``
    (ml/gpu_server/server.py:574) and the backend VastResult holds
    (app/vastai/client.py:188). Valid, non-degenerate boundaries."""
    return {
        "name": "waltz_jump",
        "start": 5,
        "takeoff": 30,
        "peak": 45,
        "landing": 60,
        "end": 70,
    }


@pytest.mark.asyncio
async def test_prod_dict_phases_not_silently_dropped() -> None:
    """Passing phases as a dict (the prod Vast.ai shape) must produce non-empty
    phase_dicts and a non-None element_type. Current code uses ``getattr`` on a
    dict → every field returns the default → guard False → phase_dicts == [] and
    element_type is None. Phase data is silently lost.
    """
    from app.services.analyzer_save import save_analyzer_results

    db = AsyncMock()
    phases = _prod_phases_dict()
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
        result = await save_analyzer_results(
            db,
            session_id="s1",
            metrics=[],
            phases=phases,
            fps=30.0,
        )

    # RED: with a dict, getattr returns defaults → phase_dicts == [] and
    # element_type is None. GREEN requires dict-aware reads.
    assert captured["phases"] != [], (
        f"save_analyzer_results wrote an EMPTY phase_dicts list for a dict phases "
        f"input with valid boundaries {phases}. In the prod Vast.ai path "
        f"(worker.py:494 -> vast_result.phases, serialized as phases.__dict__ on "
        f"the GPU server, server.py:574), phases is a dict, but analyzer_save.py:"
        f"85-91 reads it with getattr(phases, 'takeoff', 0) which returns the "
        f"default 0 for every field on a dict. The guard `takeoff>0 and landing>0` "
        f"(line 93) is therefore always False, so NO SessionPhase rows are written "
        f"and element_type is None. Phase data is silently dropped for every "
        f"Vast.ai-processed session."
    )
    assert captured["element_type"] == "waltz_jump", (
        f"save_analyzer_results set element_type={captured['element_type']!r}, "
        f"expected 'waltz_jump' from phases['name']. getattr(phases, 'name', None) "
        f"on a dict returns None (the default), so compose_isu_element_type "
        f"(worker.py:507) receives None and the session element_type is never "
        f"derived from the detected phases."
    )
    assert captured["fallback_used"] is False, (
        f"fallback_used={captured['fallback_used']!r} but the GPU returned valid "
        f"non-degenerate phases — this should not be recorded as a fallback."
    )
