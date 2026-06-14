"""Skill progress CRUD operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_progress import SkillProgress

SKILL_DEFINITIONS = [
    {"id": "jumps_bronze", "category": "jumps", "tier": "bronze", "xp_reward": 50},
    {"id": "jumps_silver", "category": "jumps", "tier": "silver", "xp_reward": 150},
    {"id": "jumps_gold", "category": "jumps", "tier": "gold", "xp_reward": 300},
    {"id": "spins_bronze", "category": "spins", "tier": "bronze", "xp_reward": 50},
    {"id": "spins_silver", "category": "spins", "tier": "silver", "xp_reward": 150},
    {"id": "spins_gold", "category": "spins", "tier": "gold", "xp_reward": 300},
    {"id": "control_bronze", "category": "control", "tier": "bronze", "xp_reward": 50},
    {"id": "control_silver", "category": "control", "tier": "silver", "xp_reward": 150},
    {"id": "control_gold", "category": "control", "tier": "gold", "xp_reward": 300},
]


async def list_by_user_id(db: AsyncSession, user_id: str) -> list[SkillProgress]:
    result = await db.execute(
        select(SkillProgress).where(SkillProgress.user_id == user_id)
    )
    return list(result.scalars().all())


async def get_or_create(db: AsyncSession, user_id: str, skill_id: str) -> SkillProgress:
    result = await db.execute(
        select(SkillProgress).where(SkillProgress.user_id == user_id, SkillProgress.skill_id == skill_id)
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        defn = next(s for s in SKILL_DEFINITIONS if s["id"] == skill_id)
        progress = SkillProgress(
            user_id=user_id,
            skill_id=defn["id"],
            category=defn["category"],
            tier=defn["tier"],
            xp_reward=defn["xp_reward"],
        )
        db.add(progress)
        await db.flush()
        await db.refresh(progress)
    return progress