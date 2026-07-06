"""Gamification API routes — user level and skills."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, get
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_403_FORBIDDEN

from app.auth.deps import CurrentUser, DbDep
from app.crud.skill_progress import list_by_user_id
from app.crud.user_level import get_by_user_id
from app.middleware.rate_limit import check_rate_limit
from app.schemas import SkillProgressResponse, UserLevelResponse

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class GamificationController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["gamification"]

    @get("/{user_id:str}/level")
    async def get_user_level(self, user_id: str, db: DbDep, user: CurrentUser) -> UserLevelResponse:
        # #474: IDOR — path user_id is never compared to the requester. Fail
        # closed: only the owner may read their own level/skills.
        if user_id != user.id:
            raise ClientException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")
        # #779: rate limit gamification reads
        await check_rate_limit(f"gamification:{user.id}", max_requests=60, window_seconds=60)
        level = await get_by_user_id(db, user_id)
        # #780: handle schema drift gracefully
        try:
            return UserLevelResponse.model_validate(level)
        except Exception:
            logger.exception("gamification level schema drift for user %s", user_id)
            raise ClientException(
                status_code=502,
                detail="Level data unavailable",
            ) from None

    @get("/{user_id:str}/skills")
    async def get_user_skills(
        self, user_id: str, db: DbDep, user: CurrentUser
    ) -> list[SkillProgressResponse]:
        # #474: IDOR — see get_user_level.
        if user_id != user.id:
            raise ClientException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")
        # #779: rate limit gamification reads
        await check_rate_limit(f"gamification:{user.id}", max_requests=60, window_seconds=60)
        skills = await list_by_user_id(db, user_id)
        # #780: handle schema drift gracefully
        try:
            return [SkillProgressResponse.model_validate(s) for s in skills]
        except Exception:
            logger.exception("gamification skills schema drift for user %s", user_id)
            raise ClientException(
                status_code=502,
                detail="Skills data unavailable",
            ) from None
