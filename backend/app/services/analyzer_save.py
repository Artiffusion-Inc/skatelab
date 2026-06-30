"""Save skating analyzer results (scores + phases) to DB from VastResult metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _metrics_to_dict(metrics: list[Any]) -> dict[str, float]:
    """Convert list of MetricResult (with .name/.value) or dicts to a dict."""
    result: dict[str, float] = {}
    for m in metrics:
        if isinstance(m, dict):
            result[m["name"]] = float(m["value"])
        else:
            result[m.name] = float(m.value)
    return result


def _build_subscores_dict(metrics_dict: dict[str, float]) -> tuple[list[dict], float, str, str]:
    """Compute subscores and return as list of plain dicts for JSONB storage.

    Returns:
        (subscores_list, overall, data_quality, skeleton_reliability)
    """
    from app.services.ml_bridge import compute_subscores_safe

    score = compute_subscores_safe(metrics_dict)
    subscores = [
        {
            "name": s.name,
            "label_ru": s.label_ru,
            "value": round(s.value, 2),
            "confidence": s.confidence,
            "contributing_metrics": s.contributing_metrics,
        }
        for s in score.subscores
    ]
    return subscores, score.overall, score.data_quality, score.skeleton_reliability


async def save_analyzer_results(
    db: AsyncSession,
    session_id: str,
    metrics: list[Any],
    phases: Any,
    fps: float = 30.0,
    total_frames: int = 0,
    rotations: int | None = None,
) -> dict[str, Any]:
    """Compute multi-dimensional score and save SessionScore + SessionPhase.

    Args:
        db: Async session.
        session_id: Session ID.
        metrics: List of MetricResult from analysis.
        phases: ElementPhase (old 3-phase model) or None.
        fps: Frame rate for time conversion.
        total_frames: Total frame count for phase coverage calc.

    Returns:
        Dict with overall_score, element_type, and rotations for gamification.
    """
    from app.crud.session_phase import create as create_phase
    from app.crud.session_score import create as create_score

    metrics_dict = _metrics_to_dict(metrics)
    subscores, overall, data_quality, skeleton_reliability = _build_subscores_dict(metrics_dict)

    # Save score
    await create_score(
        db,
        session_id=session_id,
        subscores=subscores,
        overall=overall,
        data_quality=data_quality,
        skeleton_reliability=skeleton_reliability,
    )

    # Convert old ElementPhase (3-phase) to extended PhaseExtended list (5-phase)
    phase_dicts: list[dict] = []
    element_type: str | None = None
    if phases is not None:
        # The prod Vast.ai path delivers phases as a plain dict (phases.__dict__,
        # ml/gpu_server/server.py:574) — NOT an ElementPhase dataclass. getattr on a dict
        # returns the default for every field, so read dict-style when it's a dict. #445.
        def _field(key: str, default: Any = 0) -> Any:
            if isinstance(phases, dict):
                return phases.get(key, default)
            return getattr(phases, key, default)

        element_type = _field("name", None)
        start = _field("start", 0) or 0
        takeoff = _field("takeoff", 0) or 0
        peak = _field("peak", 0) or 0
        landing = _field("landing", 0) or 0
        end = _field("end", 0) or 0

        # #461: monotonicity guard. The dict-path (#445) made degenerate
        # boundaries reachable — if end < landing, landing_mid = landing +
        # max(1, (end-landing)//2) yields a landing phase end beyond `end`,
        # and the glide_out phase gets start_frame > end_frame (negative
        # duration SessionPhase row). Reject any non-monotonic ordering; the
        # caller records fallback_used=True and no SessionPhase rows instead.
        if not (start <= takeoff <= peak <= landing <= end):
            phase_dicts = []
        elif takeoff > 0 and landing > 0:
            # #472: clamp landing_mid to end. When end == landing the
            # max(1, ...) overflows to landing+1, making glide_out
            # start_frame > end_frame (negative duration). Clamping keeps
            # the valid approach/takeoff/air phases and makes the trailing
            # landing/glide_out zero-duration instead of reversed.
            landing_mid = min(landing + max(1, (end - landing) // 2), end)
            phase_dicts = [
                {
                    "name": "approach",
                    "start_frame": start,
                    "end_frame": takeoff,
                    "start_time": start / fps,
                    "end_time": takeoff / fps,
                    "confidence": 0.7,
                    "detection_method": "heuristic",
                },
                {
                    "name": "takeoff",
                    "start_frame": takeoff,
                    "end_frame": peak,
                    "start_time": takeoff / fps,
                    "end_time": peak / fps,
                    "confidence": 0.85,
                    "detection_method": "com_parabola",
                },
                {
                    "name": "air",
                    "start_frame": peak,
                    "end_frame": landing,
                    "start_time": peak / fps,
                    "end_time": landing / fps,
                    "confidence": 0.85,
                    "detection_method": "com_parabola",
                },
                {
                    "name": "landing",
                    "start_frame": landing,
                    "end_frame": landing_mid,
                    "start_time": landing / fps,
                    "end_time": landing_mid / fps,
                    "confidence": 0.8,
                    "detection_method": "com_parabola",
                },
                {
                    "name": "glide_out",
                    "start_frame": landing_mid,
                    "end_frame": end,
                    "start_time": landing_mid / fps,
                    "end_time": end / fps,
                    "confidence": 0.6,
                    "detection_method": "heuristic",
                },
            ]

    overall_conf = 0.7 if phase_dicts else 0.0
    await create_phase(
        db,
        session_id=session_id,
        phases=phase_dicts,
        overall_confidence=overall_conf,
        element_type=element_type,
        fallback_used=phase_dicts == [],
    )

    return {"overall_score": overall, "element_type": element_type, "rotations": rotations}
