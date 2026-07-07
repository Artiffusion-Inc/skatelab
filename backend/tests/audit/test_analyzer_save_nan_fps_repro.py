"""RED repro — #1251: `save_analyzer_results` silently produces NaN
phase times when `fps=NaN` (corrupt video metadata, missing cv2 metadata).

Sibling to #647 (fps=0 → ZeroDivisionError crash). NaN fps is the
silent-NaN counterpart — same user impact (no usable phase timeline),
different crash class (no exception, NaN propagates to DB rows).

Root cause (backend/app/services/analyzer_save.py:121-158):
    "start_time": start / fps,           # NaN / NaN = NaN
    "end_time": takeoff / fps,          # NaN / NaN = NaN
    ...
    "end_time": end / fps,              # NaN / NaN = NaN
    # ↑ fps = NaN → start / NaN = NaN, end / NaN = NaN
    #   All phase times become NaN.
    #   NO guard, NO log, NO error.

Verified empirically: `float('nan') / float('nan') == float('nan')`.

Consumer chain: silent corrupt → NaN phase times in DB
    → session detail broken → user sees no phase timeline.

These tests pin the contract: NaN fps must NOT silently propagate;
either raise ValueError (#647-style rejection) or treat as
default 30.0 (defensive). The current fix (master `df4c1a2d`) chose
the raise-value-error path — these tests verify it.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module loader (analyzer_save has no app.* deps in the guard path,
# so we can load it via importlib without full app context).
# ---------------------------------------------------------------------------

_SRC_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "services" / "analyzer_save.py"


def _load_analyzer_save():
    spec = importlib.util.spec_from_file_location("app.services.analyzer_save", _SRC_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _valid_phases() -> dict:
    return {
        "name": "jump_3A",
        "start": 0,
        "takeoff": 30,
        "peak": 50,
        "landing": 70,
        "end": 100,
    }


# ---------------------------------------------------------------------------
# Test 1 — Source-level: the guard must catch NaN fps.
# Mirror of #647 source test, but specifically for NaN.
# ---------------------------------------------------------------------------


def test_analyzer_save_source_guards_nan_fps():
    """Source must validate NaN fps at the trust boundary, not silently propagate."""
    src = _SRC_FILE.read_text(encoding="utf-8")
    # The guard must use math.isfinite (NaN-safe comparison).
    assert "isfinite" in src, (
        "BUG #1251: analyzer_save.py does not check math.isfinite(fps). "
        "NaN fps silently produces NaN phase times — frame / NaN = NaN."
    )
    # The guard must reference the fps=NaN silent-NaN scenario explicitly.
    assert "NaN" in src or "nan" in src, (
        "BUG #1251: analyzer_save.py does not mention NaN. "
        "NaN fps must be guarded (Python: NaN/NaN=NaN propagates silently)."
    )


# ---------------------------------------------------------------------------
# Test 2 — Runtime: fps=NaN must raise ValueError, not silently produce NaN.
# This is the primary contract.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_analyzer_results_raises_on_fps_nan():
    """fps=NaN must raise ValueError, NOT silently produce NaN phase times."""
    mod = _load_analyzer_save()
    db = AsyncMock()
    metrics = [{"name": "airtime", "value": 0.5}]

    with pytest.raises(ValueError, match="fps"):
        await mod.save_analyzer_results(
            db=db,
            session_id="test-session",
            metrics=metrics,
            phases=_valid_phases(),
            fps=float("nan"),
        )


# ---------------------------------------------------------------------------
# Test 3 — Runtime: fps=+inf must also raise (defensive — inf is not a
# real fps value, would silently produce 0.0 times if not caught).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_analyzer_results_raises_on_fps_inf():
    """fps=+inf must raise ValueError (defensive — infinite fps is not real)."""
    mod = _load_analyzer_save()
    db = AsyncMock()
    metrics = [{"name": "airtime", "value": 0.5}]

    with pytest.raises(ValueError, match="fps"):
        await mod.save_analyzer_results(
            db=db,
            session_id="test-session",
            metrics=metrics,
            phases=_valid_phases(),
            fps=float("inf"),
        )


# ---------------------------------------------------------------------------
# Test 4 — Empirical: prove that the *unguarded* arithmetic
# `start / fps` produces NaN when fps is NaN. Documents the bug
# shape so the fix is justified.
# ---------------------------------------------------------------------------


def test_nan_fps_arithmetic_is_nan_silent():
    """Pin: with no guard, NaN/NaN silently produces NaN. This is the bug."""
    # python>=3.5: math.nan is float('nan')
    assert math.isnan(math.nan / math.nan)
    # And: NaN passed as denominator yields NaN result for any numerator.
    assert math.isnan(30 / math.nan)
    assert math.isnan(0 / math.nan)
    assert math.isnan(100 / math.nan)
    # NaN comparison always False — so plain `<= 0` guard does NOT catch NaN.
    # ruff: noqa: PLW0177 — these assertions deliberately compare against NaN
    # to pin the IEEE 754 semantics that motivate the isfinite guard.
    assert not (math.nan <= 0)  # noqa: PLW0177
    assert not (math.nan > 0)  # noqa: PLW0177
    # isfinite is the only NaN-safe comparison.
    assert not math.isfinite(math.nan)
    assert not math.isfinite(float("inf"))


# ---------------------------------------------------------------------------
# Test 5 — Regression: valid fps still works after the guard.
# Mirrors #647 valid-fps test for NaN-fps fix.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_analyzer_results_valid_fps_still_works():
    """fps=30.0 (default) must still work — no regression from NaN-fps guard."""
    mod = _load_analyzer_save()
    db = AsyncMock()

    with (
        patch("app.crud.session_score.create", new=AsyncMock()),
        patch("app.crud.session_phase.create", new=AsyncMock()),
    ):
        result = await mod.save_analyzer_results(
            db=db,
            session_id="test-session",
            metrics=[{"name": "airtime", "value": 0.5}],
            phases=_valid_phases(),
            fps=30.0,
        )
    assert "overall_score" in result
