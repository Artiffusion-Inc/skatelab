"""RED repro — gamification.award_session_xp uses int() instead of round().

backend/app/services/gamification.py:20:
    xp_earned = int(overall_score)

`int(9.9) == 9` (truncates), `round(9.9) == 10` (rounds). Users with
score 9.x are shortchanged by 1 XP per session; over many sessions this
slows skill unlocks and level progression.

Issue #546 documented the bug; #626 tracks the unfixed state in
current master. This test asserts the source contract (Rounding, not
truncation) and the runtime contract (9.9 → 10, 0.4 → 0).
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GAMIFICATION_PATH = BACKEND_ROOT / "app" / "services" / "gamification.py"


def _load_gamification_source() -> str:
    return GAMIFICATION_PATH.read_text(encoding="utf-8")


def test_source_uses_round_not_int():
    """Source must round(), not int(). RED if `int(overall_score)` is back."""
    src = _load_gamification_source()
    assert "round(overall_score)" in src, (
        "award_session_xp must use round(overall_score); int() truncates and "
        "shorts users with score 9.x by 1 XP per session (#546, #626)."
    )
    assert "int(overall_score)" not in src, (
        "int(overall_score) truncates 9.9 → 9, shorting user by 1 XP. "
        "Replace with round(overall_score)."
    )


@pytest.mark.asyncio
async def test_award_session_xp_rounds_9_9_to_10():
    """Runtime: 9.9 → 10 XP, not 9. Asserts both source state and outcome."""
    spec = importlib.util.spec_from_file_location("_gamification_under_test", GAMIFICATION_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    award = mod.award_session_xp

    # Verify the source code of the function uses round (defensive: catches
    # someone re-introducing int() in a refactor).
    src = inspect.getsource(award)
    assert "round(overall_score)" in src, f"award_session_xp source must call round(); got:\n{src}"
    assert "int(overall_score)" not in src, (
        f"award_session_xp must not call int() (truncates); got:\n{src}"
    )

    # The function is async (db.session). We can't call it without a real DB,
    # so we assert the contract by stubbing add_xp and capturing xp_earned.
    captured: dict[str, int] = {}

    async def _fake_add_xp(db, user_id, xp):
        captured["xp"] = xp
        # Minimal UserLevel-like object; downstream only returns it.
        return object()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mod, "add_xp", _fake_add_xp)
        result = await award(db=None, user_id="u", overall_score=9.9)  # type: ignore[arg-type]

    assert captured.get("xp") == 10, (
        f"9.9 must round to 10 XP, got {captured.get('xp')!r} (int() would give 9)."
    )
    assert result["xp_earned"] == 10, (
        f"returned xp_earned must be 10 for score 9.9, got {result.get('xp_earned')!r}"
    )


@pytest.mark.asyncio
async def test_award_session_xp_does_not_truncate_low_score():
    """0.4 → 0 (truncation == rounding for sub-1 scores, must not round up)."""
    spec = importlib.util.spec_from_file_location("_gamification_under_test_low", GAMIFICATION_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    award = mod.award_session_xp

    captured: dict[str, int] = {}

    async def _fake_add_xp(db, user_id, xp):
        captured["xp"] = xp
        return object()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mod, "add_xp", _fake_add_xp)
        await award(db=None, user_id="u", overall_score=0.4)  # type: ignore[arg-type]

    assert captured.get("xp") == 0, (
        f"0.4 → 0 XP (both int and round agree). Got {captured.get('xp')!r}."
    )
