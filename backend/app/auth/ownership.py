"""Ownership-check helpers for IDOR protection.

Mirrors the canonical ownership pattern at `routes/sessions.py:186-204`
(`get_session`: load by id, compare `user_id`, allow coaching override,
403 otherwise) and the task-state pattern at `routes/process.py:123-126`
but tightened to fail-closed (missing `user_id` -> 403, not open).

Two repeating patterns + one singleton:
  - DB-row ownership (Session-anchored resources): `assert_session_owned`,
    `assert_plan_owned`.
  - Task-state ownership (Valkey-stored dict): `assert_task_owned`.
The S3-key prefix check (uploads /complete) is a single call site kept
inline in `routes/uploads.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from app.crud.connection import is_connected_as
from app.crud.session import get_by_id as get_session_by_id
from app.crud.training_plan import get_by_id as get_plan_by_id
from app.models.connection import ConnectionType
from app.task_manager import get_task_state

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.session import Session
    from app.models.training_plan import TrainingPlanModel
    from app.models.user import User


async def assert_session_owned(
    db: AsyncSession,
    session_id: str,
    user: User,
    *,
    allow_coach: bool = True,
) -> Session:
    """Load a session and verify the requester owns it (or coaches the owner).

    Mirrors `routes/sessions.py:186-204`: 404 when missing, 403 when the
    requester is neither the owner nor (when `allow_coach`) an active
    coaching connection to the owner. Returns the session on success.
    """
    session = await get_session_by_id(db, session_id)
    if session is None:
        raise ClientException(status_code=HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user.id and not (
        allow_coach
        and await is_connected_as(
            db,
            from_user_id=user.id,
            to_user_id=session.user_id,
            connection_type=ConnectionType.COACHING,
        )
    ):
        raise ClientException(status_code=HTTP_403_FORBIDDEN, detail="Not authorized")
    return session


async def assert_plan_owned(db: AsyncSession, plan_id: str, user: User) -> TrainingPlanModel:
    """Load a training plan and verify the requester owns it (strict).

    No coaching override: plans are personal artifacts derived from a
    score (`TrainingPlanModel.user_id` is checked directly). 404 when
    missing, 403 when the requester is not the owner. Returns the plan.
    """
    plan = await get_plan_by_id(db, plan_id)
    if plan is None:
        raise ClientException(status_code=HTTP_404_NOT_FOUND, detail="Training plan not found")
    if plan.user_id != user.id:
        raise ClientException(status_code=HTTP_403_FORBIDDEN, detail="Not authorized")
    return plan


async def assert_task_owned(task_id: str, user: User) -> dict:
    """Load Valkey task state and verify the requester owns it (fail-closed).

    404 when state is missing. 403 when `user_id` is absent/None OR does not
    match `user.id` — fail-closed so legacy/unattributed tasks are denied
    rather than readable by any authenticated user. Returns the state dict.
    """
    state = await get_task_state(task_id)
    if state is None:
        raise ClientException(status_code=HTTP_404_NOT_FOUND, detail="Task not found")
    task_user_id = state.get("user_id")
    if task_user_id is None or str(task_user_id) != str(user.id):
        raise ClientException(
            status_code=HTTP_403_FORBIDDEN, detail="Not authorized to view this task"
        )
    return state
