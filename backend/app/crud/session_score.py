"""Session score CRUD operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session_score import SessionScore


async def get_by_session_id(db: AsyncSession, session_id: str) -> SessionScore | None:
    result = await db.execute(
        select(SessionScore).where(SessionScore.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def create(db: AsyncSession, *, session_id: str, subscores: list, overall: float, data_quality: str = "good", skeleton_reliability: str = "reliable") -> SessionScore:
    score = SessionScore(
        session_id=session_id,
        subscores=[s.model_dump() if hasattr(s, "model_dump") else s for s in subscores],
        overall=overall,
        data_quality=data_quality,
        skeleton_reliability=skeleton_reliability,
    )
    db.add(score)
    await db.flush()
    await db.refresh(score)
    return score