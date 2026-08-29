"""Tests for gamification XP/skill-unlock scale consistency (#437)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_user_level(total_xp: int = 0):
    """Build a UserLevel-like object the gamification code mutates."""
    level = MagicMock()
    level.total_xp = total_xp
    level.level = 1
    level.xp_to_next = 100
    level.title = "Новичок"
    return level


@pytest.mark.asyncio
async def test_perfect_session_xp_not_10x_inflated():
    """A perfect-session overall_score (8.0, gold-level on the 0..10 scale that
    check_skill_unlocks uses) must award single-digit XP, not 80.

    check_skill_unlocks unlocks gold at score >= 8.0 (gamification.py:20),
    which only makes sense on a 0..10 scale. award_session_xp must be
    consistent with that same scale and the level/skill-reward economy
    (L2=100 XP, gold skill reward=300 XP). int(8.0*10)=80 XP/session let a
    user buy a bronze skill (50 XP) with one session and reach L5 "Эксперт"
    in ~19 sessions — 10x too fast. #437
    """
    from app.services.gamification import award_session_xp

    db = AsyncMock()
    fake_level = _fake_user_level(total_xp=0)

    with patch("app.services.gamification.add_xp", new_callable=AsyncMock) as mock_add:
        mock_add.return_value = fake_level
        result = await award_session_xp(db, user_id="user-1", overall_score=8.0)

    xp = result["xp_earned"]
    assert xp <= 10, (
        f"award_session_xp awarded {xp} XP for a single session at score=8.0 "
        "(the gold threshold check_skill_unlocks uses). int(score*10) assumes a "
        "0..1 scale, but the only prod caller passes compute_subscores overall "
        f"(0..10). At {xp} XP/session a user reaches L5 'Эксперт' (1500 XP) in "
        f"{1500 // xp if xp else '?'} sessions. Expected <=10 XP (consistent "
        "with the 0..10 scale check_skill_unlocks thresholds pin)."
    )


@pytest.mark.asyncio
async def test_award_xp_and_skill_unlocks_agree_on_score_scale():
    """award_session_xp and check_skill_unlocks receive the same overall_score
    in production (worker.py:936 + :942). They must interpret ONE consistent
    scale. At score=8.0 check_skill_unlocks unlocks gold (correct for 0..10),
    so award_session_xp must also treat 8.0 as the top of a 0..10 scale ->
    ~8 XP, not 80. #437
    """
    from app.services.gamification import award_session_xp, check_skill_unlocks

    db = AsyncMock()
    # AsyncSession.add is synchronous; keep this test double aligned with its contract.
    db.add = MagicMock()
    score = 8.0  # unlocks gold per check_skill_unlocks thresholds

    # award_session_xp
    fake_level = _fake_user_level(total_xp=0)
    with patch("app.services.gamification.add_xp", new_callable=AsyncMock) as mock_add:
        mock_add.return_value = fake_level
        xp_result = await award_session_xp(db, user_id="u", overall_score=score)

    # check_skill_unlocks calls get_or_create once per tier; each needs a fresh
    # unlocked=False progress object.
    def _fresh_progress(*_a, **_kw):
        p = MagicMock()
        p.unlocked = False
        p.best_score = 0.0
        return p

    with patch(
        "app.services.gamification.get_or_create",
        new_callable=AsyncMock,
        side_effect=_fresh_progress,
    ):
        unlocked = await check_skill_unlocks(db, user_id="u", category="jumps", score=score)

    assert "jumps_gold" in unlocked, (
        "sanity: check_skill_unlocks must unlock gold at score=8.0, pinning the "
        "score scale to 0..10"
    )
    assert xp_result["xp_earned"] <= score + 1, (
        f"scale mismatch: check_skill_unlocks treats score=8.0 as gold-tier "
        f"(0..10 scale) but award_session_xp returns {xp_result['xp_earned']} XP "
        f"(int(score*10), a 0..1-scale formula). Same score, two scales -> "
        "10x XP inflation."
    )
