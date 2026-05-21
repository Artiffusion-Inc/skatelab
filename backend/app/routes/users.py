"""User API routes: profile and settings."""

import asyncio
from collections.abc import Sequence  # noqa: TC003
from typing import Annotated, ClassVar

from litestar import Controller, get, patch, post
from litestar.datastructures import UploadFile  # noqa: TC002
from litestar.enums import RequestEncodingType
from litestar.exceptions import ClientException
from litestar.params import Body
from litestar.status_codes import HTTP_422_UNPROCESSABLE_ENTITY

from app.auth.deps import CurrentUser, DbDep
from app.crud.user import update
from app.schemas import (
    UpdateOnboardingRoleRequest,
    UpdateProfileRequest,
    UpdateSettingsRequest,
    UserResponse,
)
from app.storage import get_object_url, upload_bytes

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB


class UsersController(Controller):
    path = "/me"
    tags: ClassVar[Sequence[str]] = ["users"]

    @get("")
    async def get_me(self, user: CurrentUser) -> UserResponse:
        """Get current user profile."""
        return UserResponse.model_validate(user)

    @patch("")
    async def update_profile(
        self,
        data: UpdateProfileRequest,
        user: CurrentUser,
        db: DbDep,
    ) -> UserResponse:
        """Update current user profile."""
        updated = await update(
            db,
            user,
            display_name=data.display_name,
            bio=data.bio,
            height_cm=data.height_cm,
            weight_kg=data.weight_kg,
        )
        return UserResponse.model_validate(updated)

    @patch("/settings")
    async def update_settings(
        self,
        data: UpdateSettingsRequest,
        user: CurrentUser,
        db: DbDep,
    ) -> UserResponse:
        """Update current user preferences."""
        updated = await update(
            db,
            user,
            language=data.language,
            timezone=data.timezone,
            theme=data.theme,
            angular_unit=data.angular_unit,
        )
        return UserResponse.model_validate(updated)

    @patch("/onboarding")
    async def update_onboarding_role(
        self,
        data: UpdateOnboardingRoleRequest,
        user: CurrentUser,
        db: DbDep,
    ) -> UserResponse:
        """Update user's onboarding role."""
        updated = await update(db, user, onboarding_role=data.onboarding_role)
        return UserResponse.model_validate(updated)

    @post("/avatar", status_code=200)
    async def upload_avatar(
        self,
        user: CurrentUser,
        db: DbDep,
        data: Annotated[UploadFile, Body(media_type=RequestEncodingType.MULTI_PART)],
    ) -> UserResponse:
        """Upload a profile picture for the current user."""
        if data.content_type not in ALLOWED_CONTENT_TYPES:
            raise ClientException(
                status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported image type: {data.content_type}. "
                f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
            )

        content = await data.read()
        if len(content) > MAX_AVATAR_SIZE:
            raise ClientException(
                status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Avatar too large: {len(content)} bytes. Max: {MAX_AVATAR_SIZE} bytes",
            )

        # Derive file extension from content type
        ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }[data.content_type]
        key = f"avatars/{user.id}{ext}"

        # Upload to R2 (sync boto3 — run in thread pool to avoid blocking)
        await asyncio.to_thread(upload_bytes, content, key)
        url = await asyncio.to_thread(get_object_url, key)

        updated = await update(db, user, avatar_url=url)
        return UserResponse.model_validate(updated)
