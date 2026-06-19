"""Session phase API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, get
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_404_NOT_FOUND

from app.auth.deps import CurrentUser, DbDep
from app.crud.session_phase import get_by_session_id
from app.schemas import SessionPhaseResponse

if TYPE_CHECKING:
    from collections.abc import Sequence


class PhasesController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["phases"]

    @get("/{session_id:str}/phases")
    async def get_session_phases(
        self, session_id: str, user: CurrentUser, db: DbDep
    ) -> SessionPhaseResponse:
        phase = await get_by_session_id(db, session_id)
        if not phase:
            raise ClientException(status_code=HTTP_404_NOT_FOUND, detail="Session phases not found")
        return SessionPhaseResponse.model_validate(phase)
