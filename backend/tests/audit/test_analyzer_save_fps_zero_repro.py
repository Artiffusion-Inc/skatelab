"""Regression test for #647 — analyzer_save fps=0 ZeroDivisionError.

Bug: `save_analyzer_results` (analyzer_save.py:121-122) divides by
`fps` to compute `start_time` / `end_time` for each phase dict. When
`fps=0` (misconfigured, default override, corrupt config) the very
first phase dict construction raises `ZeroDivisionError`, crashing
the whole save with HTTP 500. Worker retries forever; phase data
never saved.

Fix: at the top of `save_analyzer_results`, validate `fps > 0` and
raise `ValueError` with a clear message. Single caller (worker) can
treat the value error as a misconfiguration signal and surface it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------

_SRC_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "services" / "analyzer_save.py"


def test_analyzer_save_source_validates_fps():
    """Source must contain a guard against fps <= 0 referencing #647."""
    src = _SRC_FILE.read_text(encoding="utf-8")
    assert "#647" in src, (
        "BUG #647: analyzer_save.py has no #647 reference — fps=0 "
        "ZeroDivisionError is the documented bug site."
    )
    # The guard should be at the top of save_analyzer_results.
    assert "fps <= 0" in src or "fps <=" in src, (
        "BUG #647: analyzer_save.py does not guard against fps <= 0. "
        "The first phase-dict `start / fps` raises ZeroDivisionError."
    )


# ---------------------------------------------------------------------------
# Runtime: function must raise ValueError on fps=0, not ZeroDivisionError
# ---------------------------------------------------------------------------


def _load_analyzer_save():
    """Load `app.services.analyzer_save` via importlib."""
    spec = importlib.util.spec_from_file_location("app.services.analyzer_save", _SRC_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.asyncio
async def test_save_analyzer_results_rejects_fps_zero():
    """fps=0.0 must raise ValueError, not ZeroDivisionError."""
    mod = _load_analyzer_save()
    db = AsyncMock()
    metrics = [{"name": "airtime", "value": 0.5}]
    phases = {
        "name": "jump_3A",
        "start": 0,
        "takeoff": 30,
        "peak": 50,
        "landing": 70,
        "end": 100,
    }
    with pytest.raises(ValueError, match="fps"):
        await mod.save_analyzer_results(
            db=db,
            session_id="test-session",
            metrics=metrics,
            phases=phases,
            fps=0.0,
        )


@pytest.mark.asyncio
async def test_save_analyzer_results_rejects_fps_negative():
    """fps < 0 must also raise ValueError (negative fps makes no sense)."""
    mod = _load_analyzer_save()
    db = AsyncMock()
    metrics = [{"name": "airtime", "value": 0.5}]
    phases = {
        "name": "jump_3A",
        "start": 0,
        "takeoff": 30,
        "peak": 50,
        "landing": 70,
        "end": 100,
    }
    with pytest.raises(ValueError, match="fps"):
        await mod.save_analyzer_results(
            db=db,
            session_id="test-session",
            metrics=metrics,
            phases=phases,
            fps=-1.0,
        )


@pytest.mark.asyncio
async def test_save_analyzer_results_rejects_fps_nan():
    """fps=NaN must also raise ValueError (NaN comparison always False)."""
    mod = _load_analyzer_save()
    db = AsyncMock()
    metrics = [{"name": "airtime", "value": 0.5}]
    phases = {
        "name": "jump_3A",
        "start": 0,
        "takeoff": 30,
        "peak": 50,
        "landing": 70,
        "end": 100,
    }
    with pytest.raises(ValueError, match="fps"):
        await mod.save_analyzer_results(
            db=db,
            session_id="test-session",
            metrics=metrics,
            phases=phases,
            fps=float("nan"),
        )


@pytest.mark.asyncio
async def test_save_analyzer_results_valid_fps_proceeds():
    """fps=30.0 (the default) must still work — no regression."""
    mod = _load_analyzer_save()
    db = AsyncMock()

    # Patch the create_score / create_phase to avoid real DB calls.
    with (
        patch("app.crud.session_score.create", new=AsyncMock()),
        patch("app.crud.session_phase.create", new=AsyncMock()),
    ):
        metrics = [{"name": "airtime", "value": 0.5}]
        phases = {
            "name": "jump_3A",
            "start": 0,
            "takeoff": 30,
            "peak": 50,
            "landing": 70,
            "end": 100,
        }
        result = await mod.save_analyzer_results(
            db=db,
            session_id="test-session",
            metrics=metrics,
            phases=phases,
            fps=30.0,
        )
    assert "overall_score" in result
