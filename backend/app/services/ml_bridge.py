"""Bridge to ML analysis scoring. Pure-data function, no GPU/pipeline deps."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def compute_subscores_safe(metrics: dict[str, float]) -> Any:
    """Call ML compute_subscores with safe fallback.

    #648: the previous "safe" fallback returned a hardcoded 5.0/10 score
    on any failure — indistinguishable from a real ML result of 5.0.
    Downstream consumers (training_plan, gamification) only look at
    `overall` and silently treated the fallback as truth.

    New contract: on any failure (import error, NaN metrics, divide by
    zero, anything), return a sentinel `MultiDimensionalScore` with
    `overall=NaN`, `data_quality="failed"`,
    `skeleton_reliability="unreliable"`. The caller is responsible for
    checking these markers (e.g. `analyzer_save._build_subscores_dict`
    propagates them into the SessionScore row).

    Returns:
        MultiDimensionalScore dataclass, OR a sentinel "failed" instance
        on ML error. The `data_quality` field is the discriminator.
    """
    try:
        from src.analysis.multi_score import compute_subscores  # type: ignore[import-untyped]

        return compute_subscores(metrics)
    except Exception as exc:
        # #648: never silently substitute a fake 5.0 score. Surface the
        # failure with markers that downstream consumers can detect.
        log.warning(
            "ml_bridge.compute_subscores_safe: ML scoring failed (%s); "
            "returning sentinel failure marker.",
            exc,
        )
        from src.analysis.types import MultiDimensionalScore  # type: ignore[import-untyped]

        return MultiDimensionalScore(
            subscores=[],
            overall=float("nan"),
            data_quality="failed",
            skeleton_reliability="unreliable",
        )
