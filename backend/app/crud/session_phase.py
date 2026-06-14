"""Session phase CRUD operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session_phase import SessionPhase


async def get_by_session_id(db: AsyncSession, session_id: str) -> SessionPhase | None:
    result = await db.execute(
        select(SessionPhase).where(SessionPhase.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def create(db: AsyncSession, *, session_id: str, phases: list, overall_confidence: float, element_type: str | None = None, fallback_used: bool = False) -> SessionPhase:
    phase = SessionPhase(
        session_id=session_id,
        phases=[p.model_dump() if hasattr(p, "model_dump") else p for p in phases],
        overall_confidence=overall_confidence,
        element_type=element_type,
        fallback_used=fallback_used,
    )
    db.add(phase)
    await db.flush()
    await db.refresh(phase)
    return phase