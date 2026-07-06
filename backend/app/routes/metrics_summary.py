"""GET /metrics/element-summary — batched endpoint for Progress L1."""

from __future__ import annotations

from typing import ClassVar, Literal

from litestar import Controller, get
from litestar.params import Parameter

from app.auth.deps import CurrentUser, DbDep

# #784: whitelist the period param. Description promised 7d/30d/90d/all but
# nothing enforced it — `999d`/`garbage`/empty were accepted. Once aggregation
# is wired, an unknown period would build a bad SQL interval or wrong window.
# Literal lets Litestar reject unknown values with 400 before the handler runs.
Period = Literal["7d", "30d", "90d", "all"]

# #783: whitelist the element param at the family level (Progress L1 cards are
# per element family, not per ISU code). `garbage`/`<script>`/empty were
# accepted and echoed back; once aggregation is wired, an unknown family would
# KeyError the metric registry or return a silent wrong empty response. Literal
# lets Litestar reject unknown values with 400 before the handler runs. The old
# `three_turn` slug was retired (turn metrics now live under `step`).
ElementFamily = Literal["jumps", "spins", "step", "choreo", "all"]


class ElementSummaryController(Controller):
    path = ""
    tags: ClassVar[list[str]] = ["metrics"]

    @get("/element-summary")
    async def get_element_summary(
        self,
        user: CurrentUser,
        db: DbDep,
        element: ElementFamily = Parameter(
            description="Element family: jumps/spins/step/choreo/all"
        ),  # noqa: B008
        period: Period = Parameter(default="30d", description="7d/30d/90d/all"),  # noqa: B008
    ) -> dict:
        """Batched endpoint: trend + diagnostics + registry + PRs for one element."""
        # For now, return a structured empty response — actual data aggregation
        # will be wired when Progress L1 cards are implemented (Phase 3)
        return {
            "element": element,
            "period": period,
            "trend": None,
            "findings": [],
            "metric_defs": {},
            "personal_records": {},
        }
