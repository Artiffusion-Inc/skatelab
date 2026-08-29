"""Session score API routes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, get
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_404_NOT_FOUND
from pydantic import ValidationError

from app.auth.deps import CurrentUser, DbDep
from app.auth.ownership import assert_session_owned
from app.crud.session_score import get_by_session_id
from app.middleware import check_rate_limit
from app.schemas import SessionScoreResponse

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence


class ScoresController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["scores"]

    @get("/{session_id:str}/scores")
    async def get_session_scores(
        self, session_id: str, user: CurrentUser, db: DbDep
    ) -> SessionScoreResponse:
        await assert_session_owned(db, session_id, user)
        # #788: rate-limit the DB read — a flood of /scores requests hit the
        # session_scores table with no guard. Same 60/min budget as gamification.
        await check_rate_limit(f"scores:{user.id}", max_requests=60, window_seconds=60)
        score = await get_by_session_id(db, session_id)
        if not score:
            raise ClientException(status_code=HTTP_404_NOT_FOUND, detail="Session scores not found")
        # #787: schema drift (NULL where required, type mismatch, dropped
        # column) raised ValidationError → 500. Wrap → clean 502.
        try:
            return SessionScoreResponse.model_validate(score)
        except ValidationError:
            logger.exception("score_response_validation_failed session_id=%s", session_id)
            raise ClientException(
                status_code=502, detail="Score response validation failed"
            ) from None
