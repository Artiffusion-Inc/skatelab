"""GET /metrics/element-summary — batched endpoint for Progress L1."""

from __future__ import annotations

from typing import ClassVar

from litestar import Controller, get
from litestar.params import Parameter

from app.auth.deps import CurrentUser, DbDep


class ElementSummaryController(Controller):
    path = ""
    tags: ClassVar[list[str]] = ["metrics"]

    @get("/element-summary")
    async def get_element_summary(
        self,
        user: CurrentUser,
        db: DbDep,
        element: str = Parameter(description="Element type key"),
        period: str = Parameter(default="30d", description="7d/30d/90d/all"),
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
