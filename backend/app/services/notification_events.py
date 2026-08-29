"""Business event producers for in-app notifications."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.crud.notifications import create, get_by_event_source
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from app.models.notifications import Notification
    from sqlalchemy.ext.asyncio import AsyncSession


async def _emit(
    db: AsyncSession,
    *,
    user_id: str,
    event_type: str,
    source_id: str,
    title: str,
    body: str,
    deep_link: str,
    payload: dict[str, object],
) -> Notification:
    """Create one event notification, returning an existing retry safely."""
    existing = await get_by_event_source(
        db,
        user_id=user_id,
        event_type=event_type,
        source_id=source_id,
    )
    if existing is not None:
        return existing

    try:
        return await create(
            db,
            user_id=user_id,
            event_type=event_type,
            source_id=source_id,
            title=title,
            body=body,
            deep_link=deep_link,
            payload=payload,
        )
    except IntegrityError:
        # The unique constraint closes the race between concurrent retries.
        await db.rollback()
        existing = await get_by_event_source(
            db,
            user_id=user_id,
            event_type=event_type,
            source_id=source_id,
        )
        if existing is None:
            raise
        return existing


async def analysis_completed(
    db: AsyncSession,
    *,
    user_id: str,
    session_id: str,
) -> Notification:
    """Notify an athlete that their analysis is ready."""
    return await _emit(
        db,
        user_id=user_id,
        event_type="analysis.completed",
        source_id=session_id,
        title="Анализ готов",
        body="Ваш анализ завершён",
        deep_link=f"skatelab://session/{session_id}",
        payload={"session_id": session_id},
    )


async def analysis_failed(
    db: AsyncSession,
    *,
    user_id: str,
    session_id: str,
) -> Notification:
    """Notify an athlete that analysis failed without claiming a result."""
    return await _emit(
        db,
        user_id=user_id,
        event_type="analysis.failed",
        source_id=session_id,
        title="Ошибка анализа",
        body="Попробуйте ещё раз",
        deep_link=f"skatelab://session/{session_id}",
        payload={"session_id": session_id},
    )


async def training_plan_generated(
    db: AsyncSession,
    *,
    user_id: str,
    plan_id: str,
) -> Notification:
    """Notify an athlete that a training plan is available."""
    return await _emit(
        db,
        user_id=user_id,
        event_type="training.assigned",
        source_id=plan_id,
        title="Новая тренировка",
        body="Откройте план",
        deep_link=f"skatelab://training/{plan_id}",
        payload={"training_plan_id": plan_id},
    )


async def export_ready(
    db: AsyncSession,
    *,
    user_id: str,
    export_id: str,
) -> Notification:
    """Notify an athlete that an exported report is ready."""
    return await _emit(
        db,
        user_id=user_id,
        event_type="export.ready",
        source_id=export_id,
        title="Экспорт готов",
        body="Скачайте отчёт",
        deep_link=f"skatelab://exports/{export_id}",
        payload={"export_id": export_id},
    )
