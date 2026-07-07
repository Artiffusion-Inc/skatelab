"""Regression test for #1248 — analyzer_save silently skips phase build
on NaN takeoff/landing.

Bug: `backend/app/services/analyzer_save.py:106-107` reads
`takeoff = _field("takeoff", 0) or 0`. The `or 0` default does NOT catch
NaN because `bool(NaN) = True` (NaN is truthy). NaN survives.

Then the chain `if not (start <= takeoff <= peak <= landing <= end):` —
any comparison with NaN returns False, so the chain returns False, the
guard is `not False = True`, and `phase_dicts = []`. Net effect:
NaN takeoff/landing silently produce an empty phase list AND a
`fallback_used=True` SessionPhase row — but the operator has no
signal WHY. The phase breakdown is empty and the source of the
corruption is invisible in logs.

Fix: at the phase-build site, add an explicit `math.isfinite(...)`
check on takeoff/landing/peak so a non-finite value is treated as
missing data, `phase_dicts` is cleared, and a WARNING-level log line
identifies the corruption source. Single source of truth: finite-check
in the shared function so all callers route through it.
"""

from __future__ import annotations

import importlib.util
import logging
import math
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------

_SRC_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "services" / "analyzer_save.py"


def test_analyzer_save_source_has_isfinite_phase_guard():
    """Source must contain an `isfinite` guard on takeoff/landing for #1248."""
    src = _SRC_FILE.read_text(encoding="utf-8")
    assert "#1248" in src, (
        "BUG #1248: analyzer_save.py has no #1248 reference — silent NaN "
        "phase skip is the documented bug site."
    )
    # The guard must be a finite-check, not just a truthy check.
    assert "isfinite" in src, (
        "BUG #1248: analyzer_save.py does not check `math.isfinite` on "
        "takeoff/landing. NaN is truthy so `or 0` does not catch it."
    )


# ---------------------------------------------------------------------------
# Runtime helpers
# ---------------------------------------------------------------------------


def _load_analyzer_save():
    """Load `app.services.analyzer_save` via importlib (avoids DB lifespan)."""
    spec = importlib.util.spec_from_file_location("app.services.analyzer_save", _SRC_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub_score() -> MagicMock:
    score = MagicMock()
    score.subscores = []
    score.overall = 0.5
    score.data_quality = "ok"
    score.skeleton_reliability = "ok"
    return score


async def _run_save(phases: dict, captured: dict) -> None:
    """Invoke `save_analyzer_results` with mocked DB + ml_bridge."""
    mod = _load_analyzer_save()

    async def _fake_create_phase(
        _db, *, session_id, phases, overall_confidence, element_type, fallback_used
    ):
        captured["phases"] = phases
        captured["element_type"] = element_type
        captured["fallback_used"] = fallback_used
        captured["overall_confidence"] = overall_confidence
        return MagicMock()

    with (
        patch(
            "app.services.ml_bridge.compute_subscores_safe",
            return_value=_stub_score(),
        ),
        patch("app.crud.session_phase.create", new=_fake_create_phase),
        patch("app.crud.session_score.create", new_callable=AsyncMock),
    ):
        await mod.save_analyzer_results(
            AsyncMock(),
            session_id="s1",
            metrics=[],
            phases=phases,
            fps=30.0,
        )


# ---------------------------------------------------------------------------
# RED tests — must FAIL on master, PASS after the fix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nan_takeoff_emits_warning_log(caplog: pytest.LogCaptureFixture) -> None:
    """NaN takeoff must emit a WARNING log line so the operator can
    trace the silent phase skip back to corrupted input.

    On master, NaN survives `_field("takeoff", 0) or 0` and silently
    empties `phase_dicts` with no log. The fix must log a warning at
    WARNING level naming the offending field.
    """
    phases = {
        "name": "jump_3A",
        "start": 0,
        "takeoff": float("nan"),
        "peak": 50,
        "landing": 70,
        "end": 100,
    }
    captured: dict = {}
    with caplog.at_level(logging.WARNING):
        await _run_save(phases, captured)

    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records, (
        "BUG #1248: NaN takeoff produces no WARNING log. The silent "
        "phase-skip has no operator-visible signal. Fix must log a "
        "WARNING naming the non-finite phase field."
    )
    # The log should mention the offending field so the operator can
    # trace the corruption source.
    log_text = " ".join(r.getMessage() for r in warning_records).lower()
    assert "takeoff" in log_text or "nan" in log_text or "non-finite" in log_text, (
        f"BUG #1248: warning logged but does not name the offending field. Got: {log_text!r}"
    )


@pytest.mark.asyncio
async def test_nan_landing_emits_warning_log(caplog: pytest.LogCaptureFixture) -> None:
    """NaN landing must emit a WARNING log line — same root cause
    as NaN takeoff. `bool(NaN)=True` keeps NaN through `or 0`,
    chain comparison returns False, guard empties phase_dicts.
    """
    phases = {
        "name": "jump_3A",
        "start": 0,
        "takeoff": 30,
        "peak": 50,
        "landing": float("nan"),
        "end": 100,
    }
    captured: dict = {}
    with caplog.at_level(logging.WARNING):
        await _run_save(phases, captured)

    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records, (
        "BUG #1248: NaN landing produces no WARNING log. Silent phase skip with no operator signal."
    )


@pytest.mark.asyncio
async def test_nan_peak_emits_warning_log(caplog: pytest.LogCaptureFixture) -> None:
    """NaN peak (the third field the chain check touches) must also
    produce a warning. The `isfinite` guard must cover all three
    takeoff/peak/landing fields, not just the first two.
    """
    phases = {
        "name": "jump_3A",
        "start": 0,
        "takeoff": 30,
        "peak": float("nan"),
        "landing": 70,
        "end": 100,
    }
    captured: dict = {}
    with caplog.at_level(logging.WARNING):
        await _run_save(phases, captured)

    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records, (
        "BUG #1248: NaN peak produces no WARNING log. The isfinite "
        "guard must cover takeoff/peak/landing."
    )


@pytest.mark.asyncio
async def test_inf_takeoff_treated_as_missing() -> None:
    """Inf takeoff (also non-finite) must be treated the same as NaN.

    The fix uses `math.isfinite` which returns False for both NaN and
    ±Inf, so both produce the empty phase + fallback behavior. Master
    code accepts `start <= Inf` (True) but `Inf <= peak` (False), so
    the chain guard fires — but inconsistently from the NaN path
    because `0 <= Inf` is True. The fix should normalize both via
    the same isfinite check.
    """
    phases = {
        "name": "jump_3A",
        "start": 0,
        "takeoff": float("inf"),
        "peak": 50,
        "landing": 70,
        "end": 100,
    }
    captured: dict = {}
    await _run_save(phases, captured)

    assert captured["phases"] == [], (
        f"BUG #1248: Inf takeoff must produce empty phase list, "
        f"got {len(captured['phases'])} phases. The isfinite guard "
        f"covers both NaN and Inf."
    )
    assert captured["fallback_used"] is True
    assert captured["overall_confidence"] == 0.0, (
        f"BUG #1248: Inf takeoff should clear overall_confidence, "
        f"got {captured['overall_confidence']}"
    )


@pytest.mark.asyncio
async def test_finite_phases_still_build_normally() -> None:
    """Regression guard: valid finite phase boundaries still produce
    the 5-phase breakdown. The fix must not over-clear on legitimate
    inputs.
    """
    phases = {
        "name": "jump_3A",
        "start": 0,
        "takeoff": 30,
        "peak": 50,
        "landing": 70,
        "end": 100,
    }
    captured: dict = {}
    await _run_save(phases, captured)

    phase_dicts = captured["phases"]
    assert len(phase_dicts) == 5, (
        f"REGRESSION: finite phase boundaries should produce 5 phases, "
        f"got {len(phase_dicts)}: {[p['name'] for p in phase_dicts]}"
    )
    assert captured["fallback_used"] is False
    assert [p["name"] for p in phase_dicts] == [
        "approach",
        "takeoff",
        "air",
        "landing",
        "glide_out",
    ]
    # Sanity: every frame is finite — the 5 phases built from clean
    # input must not accidentally include NaN.
    for p in phase_dicts:
        assert math.isfinite(p["start_frame"])
        assert math.isfinite(p["end_frame"])
        assert math.isfinite(p["start_time"])
        assert math.isfinite(p["end_time"])
