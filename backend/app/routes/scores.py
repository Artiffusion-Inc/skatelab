"""Session score API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, get
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_404_NOT_FOUND

from app.auth.deps import CurrentUser, DbDep
from app.auth.ownership import assert_session_owned
from app.crud.session_score import get_by_session_id
from app.schemas import SessionScoreResponse

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
        score = await get_by_session_id(db, session_id)
        if not score:
            raise ClientException(status_code=HTTP_404_NOT_FOUND, detail="Session scores not found")
        return SessionScoreResponse.model_validate(score)
