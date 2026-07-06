"""Training plan CRUD operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_plan import TrainingPlanModel


async def get_by_id(db: AsyncSession, plan_id: str) -> TrainingPlanModel | None:
    result = await db.execute(select(TrainingPlanModel).where(TrainingPlanModel.id == plan_id))
    return result.scalar_one_or_none()


async def get_for_session(
    db: AsyncSession, user_id: str, session_id: str
) -> TrainingPlanModel | None:
    """Load a user's existing plan for a session (#793 dedup).

    Used by ``generate_plan`` to make plan generation idempotent per
    ``(user_id, session_id)`` — repeated POSTs return the existing plan
    instead of polluting the table with duplicate rows.
    """
    result = await db.execute(
        select(TrainingPlanModel).where(
            TrainingPlanModel.user_id == user_id,
            TrainingPlanModel.session_id == session_id,
        )
    )
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession,
    *,
    user_id: str,
    session_id: str | None,
    items: list,
    focus_subscore: str | None = None,
) -> TrainingPlanModel:
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
