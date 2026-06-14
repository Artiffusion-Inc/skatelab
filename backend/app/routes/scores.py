"""Session score API routes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from litestar import Controller, get
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_404_NOT_FOUND

from app.auth.deps import CurrentUser, DbDep
from app.crud.session_score import get_by_session_id
from app.schemas import SessionScoreResponse


class ScoresController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["scores"]

    @get("/{session_id:str}/scores")
    async def get_session_scores(self, session_id: str, user: CurrentUser, db: DbDep) -> SessionScoreResponse:
        score = await get_by_session_id(db, session_id)
        if not score:
            raise ClientException(status_code=HTTP_404_NOT_FOUND, detail="Session scores not found")
        return SessionScoreResponse.model_validate(score)