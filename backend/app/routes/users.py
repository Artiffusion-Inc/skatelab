"""User API routes: profile and settings."""

from collections.abc import Sequence  # noqa: TC003
from typing import ClassVar

from litestar import Controller, get, patch

from app.auth.deps import CurrentUser, DbDep
from app.crud.user import update
from app.schemas import (
    UpdateOnboardingRoleRequest,
    UpdateProfileRequest,
    UpdateSettingsRequest,
    UserResponse,
)


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
