"""Training plan API routes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, get, post
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_201_CREATED, HTTP_404_NOT_FOUND
from pydantic import ValidationError

from app.auth.deps import CurrentUser, DbDep, VerifiedUser
from app.auth.ownership import assert_plan_owned, assert_session_owned
from app.crud.session_score import get_by_session_id
from app.crud.training_plan import create as create_plan
from app.crud.training_plan import get_for_session
from app.middleware.rate_limit import check_rate_limit
from app.schemas import GenerateTrainingPlanRequest, SubScoreSchema, TrainingPlanResponse
from app.services.notification_events import training_plan_generated
from app.services.training_plan import generate_training_plan

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class TrainingPlansController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["training-plans"]

    @post("/generate", status_code=HTTP_201_CREATED)
    async def generate_plan(
        self, data: GenerateTrainingPlanRequest, user: VerifiedUser, db: DbDep
    ) -> TrainingPlanResponse:
        # #792: plan generation is expensive (service CPU + DB write); cap to
        # 5 plans/hour per user to bound abuse.
        await check_rate_limit(f"plan_generate:{user.id}", max_requests=5, window_seconds=3600)

        await assert_session_owned(db, data.session_id, user)
        score = await get_by_session_id(db, data.session_id)
        if not score:
            raise ClientException(status_code=HTTP_404_NOT_FOUND, detail="Session scores not found")

        # #793: idempotent per (user_id, session_id) — return the existing plan
        # instead of creating duplicate rows on repeated POSTs (table pollution).
        existing = await get_for_session(db, user_id=user.id, session_id=data.session_id)
        if existing is not None:
            # #791: schema drift on the existing row → 502, not 500.
            try:
                return TrainingPlanResponse.model_validate(existing)
            except ValidationError as e:
                logger.exception("training_plan_response_validation_failed plan_id=%s", existing.id)
                raise ClientException(
                    status_code=502, detail="Training plan response validation failed"
                ) from e

        # #789: validate every subscore; skip non-dict/non-schema garbage
        # (legacy row, worker bug, manual DB edit) instead of passing it
        # through to the generator where it crashes on `.label_ru`/`.value`.
        coerced: list[SubScoreSchema] = []
        for s in score.subscores:
            if isinstance(s, SubScoreSchema):
                coerced.append(s)
            elif isinstance(s, dict):
                try:
                    coerced.append(SubScoreSchema(**s))
                except (ValidationError, TypeError, ValueError) as e:
                    logger.warning(
                        "invalid subscore dict skipped session_id=%s err=%s", data.session_id, e
                    )
                    continue
            else:
                logger.warning(
                    "invalid subscore type skipped session_id=%s type=%s",
                    data.session_id,
                    type(s).__name__,
                )
                continue

        # #790: guard the service call — corrupt/edge subscores crash the
        # generator (AttributeError/TypeError/ValueError); surface as 502.
        try:
            items = generate_training_plan(coerced, session_id=data.session_id, lang=user.language)
        except (AttributeError, TypeError, ValueError) as e:
            logger.exception("training_plan_generation_failed session_id=%s", data.session_id)
            raise ClientException(status_code=502, detail="Plan generation failed") from e

        plan = await create_plan(
            db,
            user_id=user.id,
            session_id=data.session_id,
            items=items,
            focus_subscore=items[0].label_ru if items else None,
        )
        await training_plan_generated(db, user_id=user.id, plan_id=plan.id)
        # #791: schema drift on the freshly created row → 502, not 500.
        try:
            return TrainingPlanResponse.model_validate(plan)
        except ValidationError as e:
            logger.exception("training_plan_response_validation_failed plan_id=%s", plan.id)
            raise ClientException(
                status_code=502, detail="Training plan response validation failed"
            ) from e

    @get("/{plan_id:str}")
    async def get_plan(self, plan_id: str, user: CurrentUser, db: DbDep) -> TrainingPlanResponse:
        # #794: bound DB read flood — 60 reads/min per user.
        await check_rate_limit(f"plan_get:{user.id}", max_requests=60, window_seconds=60)

        plan = await assert_plan_owned(db, plan_id, user)
        # #791: schema drift → 502, not 500.
        try:
            return TrainingPlanResponse.model_validate(plan)
        except ValidationError as e:
            logger.exception("training_plan_response_validation_failed plan_id=%s", plan.id)
            raise ClientException(
                status_code=502, detail="Training plan response validation failed"
            ) from e
