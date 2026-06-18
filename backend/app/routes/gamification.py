"""Gamification API routes — user level and skills."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, get

from app.auth.deps import DbDep
from app.crud.skill_progress import list_by_user_id
from app.crud.user_level import get_by_user_id
from app.schemas import SkillProgressResponse, UserLevelResponse

if TYPE_CHECKING:
    from collections.abc import Sequence


class GamificationController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["gamification"]

    @get("/{user_id:str}/level")
    async def get_user_level(self, user_id: str, db: DbDep) -> UserLevelResponse:
        level = await get_by_user_id(db, user_id)
        return UserLevelResponse.model_validate(level)

    @get("/{user_id:str}/skills")
    async def get_user_skills(self, user_id: str, db: DbDep) -> list[SkillProgressResponse]:
        skills = await list_by_user_id(db, user_id)
        return [SkillProgressResponse.model_validate(s) for s in skills]
