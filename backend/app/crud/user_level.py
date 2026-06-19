"""User level CRUD operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_level import UserLevel

LEVEL_THRESHOLDS = [
    (0, 1, 100, "Новичок"),
    (100, 2, 250, "Ученик"),
    (250, 3, 700, "Спортсмен"),
    (700, 4, 1500, "Мастер"),
    (1500, 5, 999999, "Эксперт"),
]


async def get_by_user_id(db: AsyncSession, user_id: str) -> UserLevel:
    result = await db.execute(select(UserLevel).where(UserLevel.user_id == user_id))
    level = result.scalar_one_or_none()
    if level is None:
        level = UserLevel(user_id=user_id, level=1, total_xp=0, xp_to_next=100, title="Новичок")
        db.add(level)
        await db.flush()
        await db.refresh(level)
    return level


async def add_xp(db: AsyncSession, user_id: str, xp: int) -> UserLevel:
    level = await get_by_user_id(db, user_id)
    level.total_xp += xp
    # Check level up
    for threshold, lvl, xp_next, title in LEVEL_THRESHOLDS:
        if level.total_xp >= threshold:
            level.level = lvl
            level.xp_to_next = xp_next
            level.title = title
    db.add(level)
    await db.flush()
    await db.refresh(level)
    return level
