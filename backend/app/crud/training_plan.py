"""Training plan CRUD operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_plan import TrainingPlanModel


async def get_by_id(db: AsyncSession, plan_id: str) -> TrainingPlanModel | None:
    result = await db.execute(
        select(TrainingPlanModel).where(TrainingPlanModel.id == plan_id)
    )
    return result.scalar_one_or_none()


async def create(db: AsyncSession, *, user_id: str, session_id: str | None, items: list, focus_subscore: str | None = None) -> TrainingPlanModel:
    plan = TrainingPlanModel(
        user_id=user_id,
        session_id=session_id,
        items=[i.model_dump() if hasattr(i, "model_dump") else i for i in items],
        focus_subscore=focus_subscore,
    )
    db.add(plan)
    await db.flush()
    await db.refresh(plan)
    return plan