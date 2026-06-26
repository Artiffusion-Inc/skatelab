"""SessionMetric CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.session import Session, SessionMetric

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_current_best(
    db: AsyncSession,
    user_id: str,
    element_type: str,
    metric_name: str,
    direction: str = "higher",
) -> float | None:
    """Get the current best value for a user+element+metric combination.

    Only considers non-deleted sessions. For direction="higher", returns max.
    For direction="lower", returns min.
    """
    order_col = (
        SessionMetric.metric_value.desc()
        if direction == "higher"
        else SessionMetric.metric_value.asc()
    )
    query = (
        select(SessionMetric.metric_value)
        .join(Session)
        .where(
            Session.user_id == user_id,
            Session.element_type == element_type,
            SessionMetric.metric_name == metric_name,
            Session.status == "done",
        )
        .order_by(order_col)
        .limit(1)
    )
    result = await db.execute(query)
    row = result.scalar_one_or_none()
    return row


async def get_current_best_batch(
    db: AsyncSession,
    user_id: str,
    element_type: str | None,
    metric_names: list[str],
) -> dict[str, float]:
    """Get current best values for multiple metrics in a single query.

    Uses METRIC_REGISTRY to determine direction per metric.
    Higher-is-better -> max, lower-is-better -> min.
    Missing metrics (no data) are omitted from the dict.

    If element_type is None (session created during auto-detect, element not
    yet determined), there are no per-element bests to fetch -> return {}.
    """
    if not metric_names:
        return {}

    if element_type is None:
        return {}

    from sqlalchemy import func

    from app.metrics_registry import METRIC_REGISTRY

    def _metric_direction(name: str) -> str:
        mdef = METRIC_REGISTRY.get(name)
        return mdef.direction if mdef else "higher"

    higher_metrics = [n for n in metric_names if _metric_direction(n) == "higher"]
    lower_metrics = [n for n in metric_names if _metric_direction(n) == "lower"]

    bests: dict[str, float] = {}

    if higher_metrics:
        result = await db.execute(
            select(
                SessionMetric.metric_name,
                func.max(SessionMetric.metric_value).label("best_value"),
            )
            .join(Session)
            .where(
                Session.user_id == user_id,
                Session.element_type == element_type,
                SessionMetric.metric_name.in_(higher_metrics),
                Session.status == "done",
            )
            .group_by(SessionMetric.metric_name)
        )
        bests.update({row.metric_name: row.best_value for row in result.all()})

    if lower_metrics:
        result = await db.execute(
            select(
                SessionMetric.metric_name,
                func.min(SessionMetric.metric_value).label("best_value"),
            )
            .join(Session)
            .where(
                Session.user_id == user_id,
                Session.element_type == element_type,
                SessionMetric.metric_name.in_(lower_metrics),
                Session.status == "done",
            )
            .group_by(SessionMetric.metric_name)
        )
        bests.update({row.metric_name: row.best_value for row in result.all()})

    return bests


async def bulk_create(db: AsyncSession, metrics: list[dict]) -> None:
    """Insert multiple session metrics in one flush."""
    for m in metrics:
        db.add(SessionMetric(**m))
    await db.flush()
