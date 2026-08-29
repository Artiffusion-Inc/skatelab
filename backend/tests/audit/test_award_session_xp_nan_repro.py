"""RED repro — award_session_xp crashes on NaN overall_score.

backend/app/services/gamification.py:24:
    xp_earned = round(overall_score)

`round(float('nan'))` returns NaN, and downstream `add_xp(db, user_id, NaN)`
either crashes (sqlalchemy binding NaN to an int column -> ValueError) or
inserts garbage XP. Either way the XP award path is corrupted when
upstream metrics are NaN (corrupt analyzer, missing references, etc.).

This is a hard CRASH in the consumer chain: XP award -> user level ->
session save (no XP credited, broken session).

Consumer chain evidence:
  worker.py:943 imports award_session_xp; worker.py:947 awaits it with
  overall_score from analyzer. If analyzer.overall_score is NaN,
  round(NaN) -> NaN propagates to add_xp, where asyncpg/SQLAlchemy raises
  "invalid input for query argument $N: nan" or similar ValueError.

Fix (per issue #1235): guard with `math.isfinite(overall_score)` before
calling round() — fall back to 0 XP for non-finite inputs (no award,
no crash). This matches the precedent set by:
  - backend/app/services/analyzer_save.py:78 (fps NaN guard)
  - backend/app/routes/metrics.py:163 (slope/r² NaN guard)
  - backend/app/routes/uploads.py:155 (NaN page-number guard)

No fix in this PR — RED repro only (issue #1235 tranche KR).
"""

from __future__ import annotations

import importlib.util
import inspect
import math
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GAMIFICATION_PATH = BACKEND_ROOT / "app" / "services" / "gamification.py"


def _load_gamification_source() -> str:
    return GAMIFICATION_PATH.read_text(encoding="utf-8")


def _load_gamification_module():
    spec = importlib.util.spec_from_file_location("_gamification_under_test_nan", GAMIFICATION_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_source_guards_nonfinite_overall_score():
    """Source must reject non-finite overall_score before int/round. RED if
    `round(overall_score)` (or `int(overall_score)`) is unguarded and
    NaN can flow into add_xp."""
    src = _load_gamification_source()
    assert "math.isfinite" in src, (
        "award_session_xp must guard non-finite overall_score with "
        "math.isfinite() before round()/int() (issue #1235). NaN/inf "
        "upstream causes ValueError on XP award (crashes session save)."
    )


def test_source_does_not_pass_nan_to_add_xp():
    """Defensive: NaN/inf must not be the xp argument to add_xp. The
    guard must short-circuit to a safe int (0) before add_xp is called."""
    src = _load_gamification_source()
    award_src = _load_gamification_module()
    src_text = inspect.getsource(award_src.award_session_xp)
    # The guard is in the function body
    assert "math.isfinite" in src_text, (
        f"award_session_xp body must call math.isfinite(overall_score) "
        f"to drop NaN/inf before round(); got:\n{src_text}"
    )


@pytest.mark.asyncio
async def test_award_session_xp_does_not_crash_on_nan(monkeypatch):
    """NaN overall_score must not raise. add_xp receives a real int (0)."""
    mod = _load_gamification_module()
    award = mod.award_session_xp

    captured: dict[str, object] = {}

    async def _fake_add_xp(db, user_id, xp):
        captured["xp"] = xp
        return object()

    monkeypatch.setattr(mod, "add_xp", _fake_add_xp)

    # Must not raise ValueError ("cannot convert float NaN to integer")
    # or any other exception. NaN upstream = no XP awarded (0).
    result = await award(db=None, user_id="u", overall_score=float("nan"))  # type: ignore[arg-type]

    assert "xp" in captured, "add_xp must be called even for NaN (so level state stays consistent)"
    xp_passed = captured["xp"]
    assert isinstance(xp_passed, int) and not isinstance(xp_passed, bool), (
        f"add_xp must receive a real int, got {xp_passed!r} (type {type(xp_passed).__name__}). "
        f"NaN/XP integer-cast is what crashes the worker."
    )
    assert xp_passed == 0, f"NaN overall_score must award 0 XP, got {xp_passed!r}"
    assert result["xp_earned"] == 0, (
        f"returned xp_earned must be 0 for NaN, got {result.get('xp_earned')!r}"
    )


@pytest.mark.asyncio
async def test_award_session_xp_does_not_crash_on_positive_infinity(monkeypatch):
    """+inf overall_score must not raise. XP clamped to a real int."""
    mod = _load_gamification_module()
    award = mod.award_session_xp

    captured: dict[str, object] = {}

    async def _fake_add_xp(db, user_id, xp):
        captured["xp"] = xp
        return object()

    monkeypatch.setattr(mod, "add_xp", _fake_add_xp)

    # +inf upstream must not raise. round(inf) = inf, which is not a
    # valid int — same crash as NaN.
    result = await award(db=None, user_id="u", overall_score=float("inf"))  # type: ignore[arg-type]

    xp_passed = captured.get("xp")
    assert isinstance(xp_passed, int) and not isinstance(xp_passed, bool), (
        f"add_xp must receive a real int for +inf input, got {xp_passed!r} "
        f"(type {type(xp_passed).__name__})."
    )
    assert result["xp_earned"] == xp_passed


@pytest.mark.asyncio
async def test_award_session_xp_normal_scores_still_work(monkeypatch):
    """Regression: finite scores round normally (9.9 -> 10, 0.4 -> 0)."""
    mod = _load_gamification_module()
    award = mod.award_session_xp

    captured: list[int] = []

    async def _fake_add_xp(db, user_id, xp):
        captured.append(xp)
        return object()

    monkeypatch.setattr(mod, "add_xp", _fake_add_xp)

    await award(db=None, user_id="u", overall_score=9.9)  # type: ignore[arg-type]
    await award(db=None, user_id="u", overall_score=0.4)  # type: ignore[arg-type]
    await award(db=None, user_id="u", overall_score=7.5)  # type: ignore[arg-type]

    assert captured == [10, 0, 8], (
        f"finite scores must round normally; got {captured!r} "
        f"(expected [10, 0, 8] for 9.9, 0.4, 7.5). "
        f"NaN guard must not break the happy path."
    )
    # And ensure math.isfinite is a true guard, not a silent rewriter of all inputs.
    assert all(isinstance(x, int) and not isinstance(x, bool) for x in captured), (
        f"all xp values must be real int; got {[type(x).__name__ for x in captured]}"
    )
    # Sanity: NaN/inf are not accidentally being collapsed to 0 silently
    # for finite inputs (none of the captured values should be NaN-like).
    for x in captured:
        assert math.isfinite(float(x)), f"xp must be finite int, got {x!r}"
