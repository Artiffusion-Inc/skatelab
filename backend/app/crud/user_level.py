"""User level CRUD operations."""

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    # #485: use pg_insert with on_conflict_do_nothing for race-safe create,
    # then re-read. Mirrors the #459 skill_progress fix. Also tolerate
    # legacy duplicate state by using .first() (instead of scalar_one_or_none)
    # so users already in the broken state recover without manual DB cleanup.
    stmt = (
        pg_insert(UserLevel)
        .values(
            user_id=user_id,
            level=1,
            total_xp=0,
            xp_to_next=100,
            title="Новичок",
        )
        .on_conflict_do_nothing(constraint="uq_user_level_user")
    )
    await db.execute(stmt)
    await db.flush()
    result = await db.execute(select(UserLevel).where(UserLevel.user_id == user_id))
    # Use .first() (not .scalar_one_or_none()) so users with legacy
    # duplicate rows (pre-#485) don't crash gamification permanently —
    # we return the first row, which is good enough for read-modify-write.
    return result.scalars().first()  # type: ignore[return-value]


async def add_xp(db: AsyncSession, user_id: str, xp: int) -> UserLevel:
    level = await get_by_user_id(db, user_id)
    if level is None:  # defensive: should not happen after pg_insert above
        raise RuntimeError(f"user_level row missing for user_id={user_id!r}")
    # Atomic SQL increment — the DB serializes the update so concurrent awards
    # cannot overwrite each other (no read-modify-write lost update).
    await db.execute(
        update(UserLevel)
        .where(UserLevel.user_id == user_id)
        .values(total_xp=UserLevel.total_xp + xp)
    )
    await db.flush()
    # Re-fetch the fresh total_xp for the level-up computation.
    await db.refresh(level)
    # Check level up against the post-increment total.
    for threshold, lvl, xp_next, title in LEVEL_THRESHOLDS:
        if level.total_xp >= threshold:
            level.level = lvl
            level.xp_to_next = xp_next
            level.title = title
    await db.flush()
    await db.refresh(level)
    return level
