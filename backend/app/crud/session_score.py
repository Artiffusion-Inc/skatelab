"""Session score CRUD operations."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session_score import SessionScore


async def get_by_session_id(db: AsyncSession, session_id: str) -> SessionScore | None:
    result = await db.execute(select(SessionScore).where(SessionScore.session_id == session_id))
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession,
    *,
    session_id: str,
    subscores: list,
    overall: float,
    data_quality: str = "good",
    skeleton_reliability: str = "reliable",
) -> SessionScore:
    # #548: upsert via try/except IntegrityError. Pre-fix: db.add(score)
    # then db.flush() — second call hits unique constraint on
    # session_id, raises IntegrityError, unhandled 500 to the user.
    # The main metrics path uses update_session_analysis() (UPSERT via
    # UPDATE), but SessionScore/SessionPhase go through raw create() with
    # no upsert. Fix: try insert, on IntegrityError fetch the existing
    # row and update its fields in place.
    score = SessionScore(
        session_id=session_id,
        subscores=[s.model_dump() if hasattr(s, "model_dump") else s for s in subscores],
        overall=overall,
        data_quality=data_quality,
        skeleton_reliability=skeleton_reliability,
    )
    db.add(score)
    try:
        await db.flush()
    except IntegrityError:
        # Existing row for this session_id. Roll back the failed insert
        # and update the existing row instead.
        await db.rollback()
        existing = await get_by_session_id(db, session_id)
        if existing is not None:
            existing.subscores = [
                s.model_dump() if hasattr(s, "model_dump") else s for s in subscores
            ]
            existing.overall = overall
            existing.data_quality = data_quality
            existing.skeleton_reliability = skeleton_reliability
            await db.flush()
            await db.refresh(existing)
            return existing
        # If we can't find the existing row after rollback, re-raise.
        raise
    await db.refresh(score)
    return score
