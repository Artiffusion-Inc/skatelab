"""Session phase API routes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, get
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_404_NOT_FOUND
from pydantic import ValidationError

from app.auth.deps import CurrentUser, DbDep
from app.auth.ownership import assert_session_owned
from app.crud.session_phase import get_by_session_id
from app.middleware import check_rate_limit
from app.schemas import SessionPhaseResponse

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence


class PhasesController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["phases"]

    @get("/{session_id:str}/phases")
    async def get_session_phases(
        self, session_id: str, user: CurrentUser, db: DbDep
    ) -> SessionPhaseResponse:
        await assert_session_owned(db, session_id, user)
        # #786: rate-limit the DB read — a flood of /phases requests hit the
        # session_phases table with no guard. Same 60/min per-user budget.
        await check_rate_limit(f"phases:{user.id}", max_requests=60, window_seconds=60)
        phase = await get_by_session_id(db, session_id)
        if not phase:
            raise ClientException(status_code=HTTP_404_NOT_FOUND, detail="Session phases not found")
        # #785: schema drift (NULL where required, type mismatch, dropped
        # column) raised ValidationError → 500. Wrap → clean 502.
        try:
            return SessionPhaseResponse.model_validate(phase)
        except ValidationError:
            logger.exception("phase_response_validation_failed session_id=%s", session_id)
            raise ClientException(
                status_code=502, detail="Phase response validation failed"
            ) from None
