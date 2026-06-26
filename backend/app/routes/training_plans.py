"""Training plan API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, get, post
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_201_CREATED, HTTP_404_NOT_FOUND

from app.auth.deps import CurrentUser, DbDep, VerifiedUser
from app.auth.ownership import assert_plan_owned, assert_session_owned
from app.crud.session_score import get_by_session_id
from app.crud.training_plan import create as create_plan
from app.schemas import GenerateTrainingPlanRequest, SubScoreSchema, TrainingPlanResponse
from app.services.training_plan import generate_training_plan

if TYPE_CHECKING:
    from collections.abc import Sequence


class TrainingPlansController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["training-plans"]

    @post("/generate", status_code=HTTP_201_CREATED)
    async def generate_plan(
        self, data: GenerateTrainingPlanRequest, user: VerifiedUser, db: DbDep
    ) -> TrainingPlanResponse:
        await assert_session_owned(db, data.session_id, user)
        score = await get_by_session_id(db, data.session_id)
        if not score:
            raise ClientException(status_code=HTTP_404_NOT_FOUND, detail="Session scores not found")
        subscores = [SubScoreSchema(**s) if isinstance(s, dict) else s for s in score.subscores]
        items = generate_training_plan(subscores, session_id=data.session_id)
        plan = await create_plan(
            db,
            user_id=user.id,
            session_id=data.session_id,
            items=items,
            focus_subscore=items[0].label_ru if items else None,
        )
        return TrainingPlanResponse.model_validate(plan)

    @get("/{plan_id:str}")
    async def get_plan(self, plan_id: str, user: CurrentUser, db: DbDep) -> TrainingPlanResponse:
        plan = await assert_plan_owned(db, plan_id, user)
        return TrainingPlanResponse.model_validate(plan)
