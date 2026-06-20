"""Save ML pipeline results to Postgres.

Called after successful video processing to persist sessions and metrics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.crud.session import get_by_id, update
from app.crud.session_metric import bulk_create, get_current_best_batch
from app.metrics_registry import METRIC_REGISTRY
from app.services.pr_tracker import check_pr

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def save_analysis_results(
    db: AsyncSession,
    session_id: str,
    metrics: list[Any],  # list[MetricResult]
    phases: Any,  # ElementPhase
    recommendations: list[str],
    goe_grade: dict[str, Any] | None = None,
) -> None:
    """Save analysis results to Postgres.

    Args:
        db: Async database session.
        session_id: ID of the Session row (created at upload time).
        metrics: List of MetricResult from BiomechanicsAnalyzer.
        phases: Detected ElementPhase.
        recommendations: Russian recommendation strings.
    """
    session = await get_by_id(db, session_id)
    if not session:
        return

    # Vast.ai delivers metrics as a list of dicts {"name", "value", ...}; local
    # pipeline produces MetricResult dataclasses with .name/.value. Normalize to a
    # list of dicts so this saver works with either shape.
    metric_items = [
        m if isinstance(m, dict) else {"name": m.name, "value": m.value} for m in metrics
    ]

    # Build metric rows with PR tracking
    metric_rows = []

    # Batch-fetch all current bests in one query (N+1 fix)
    metric_names = [m["name"] for m in metric_items]
    bests = await get_current_best_batch(
        db,
        user_id=session.user_id,
        element_type=session.element_type,
        metric_names=metric_names,
    )

    for m in metric_items:
        mdef = METRIC_REGISTRY.get(m["name"])
        ref_value = mdef.ideal_range[0] if mdef else None
        ref_max = mdef.ideal_range[1] if mdef else None

        is_in_range = None
        if mdef and ref_value is not None and ref_max is not None:
            is_in_range = ref_value <= m["value"] <= ref_max

        # Check PR using batch-fetched best
        current_best = bests.get(m["name"])
        direction = mdef.direction if mdef else "higher"
        is_pr, prev_best = check_pr(direction, current_best, m["value"])

        metric_rows.append(
            {
                "session_id": session_id,
                "metric_name": m["name"],
                "metric_value": m["value"],
                "is_pr": is_pr,
                "prev_best": prev_best,
                "reference_value": ref_value,
                "is_in_range": is_in_range,
            }
        )

    await bulk_create(db, metric_rows)

    # Compute overall_score
    in_range_count = sum(1 for m in metric_rows if m["is_in_range"])
    overall_score = in_range_count / len(metric_rows) if metric_rows else None

    # Update session with GOE grade if present
    update_kwargs: dict[str, Any] = {
        "status": "done",
        "overall_score": overall_score,
        "recommendations": recommendations,
    }
    if goe_grade is not None:
        update_kwargs["goe_grade"] = goe_grade

    await update(db, session, **update_kwargs)
