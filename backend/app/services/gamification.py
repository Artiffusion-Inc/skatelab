"""Gamification service: XP, levels, skill unlock logic."""

import math
from datetime import UTC

from app.crud.skill_progress import get_or_create
from app.crud.user_level import add_xp
from sqlalchemy.ext.asyncio import AsyncSession


async def award_session_xp(db: AsyncSession, user_id: str, overall_score: float) -> dict:
    """Award XP based on session score.

    overall_score is on a 0..10 scale (compute_subscores.overall, multi_score.py:93;
    the only prod caller worker.py passes analyzer["overall_score"]). 1 XP per
    score point -> max 10 XP per session, consistent with check_skill_unlocks
    thresholds (bronze=5.0/silver=6.5/gold=8.0, same 0..10 scale) and the
    level/skill-reward economy (L2=100 XP, gold skill reward=300 XP). Old code
    used int(score*10), a 0..1-scale formula that inflated XP 10x (#437).
    """
    # #1235: round(NaN) raises ValueError ("cannot convert float NaN to integer").
    # Corrupt upstream metrics (missing references, gap-filled NaN scores) must
    # not crash the XP award path. Fall back to 0 XP — no award, no crash.
    if not math.isfinite(overall_score):
        overall_score = 0.0
    # #546: round() instead of int(). int(9.9) = 9 (truncates), but
    # round(9.9) = 10. Users lose 0-1 XP per session on a 0-10 scale
    # with decimal subscores. round() uses banker's rounding (half-to-even)
    # which is the Python default and acceptable for XP awards.
    xp_earned = round(overall_score)
    level = await add_xp(db, user_id, xp_earned)
    return {"xp_earned": xp_earned, "level": level}


async def check_skill_unlocks(db: AsyncSession, user_id: str, category: str, score: float) -> list:
    """Check and unlock skills based on score thresholds."""
    unlocked = []
    for tier, threshold in [("bronze", 5.0), ("silver", 6.5), ("gold", 8.0)]:
        skill_id = f"{category}_{tier}"
        progress = await get_or_create(db, user_id, skill_id)
        if not progress.unlocked and score >= threshold:
            progress.unlocked = True
            from datetime import datetime

            progress.unlocked_at = datetime.now(UTC)
            progress.best_score = max(progress.best_score, score)
            db.add(progress)
            unlocked.append(skill_id)
    await db.flush()
    return unlocked
