"""User API routes: profile and settings."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Sequence  # noqa: TC003
from typing import Annotated, ClassVar

from litestar import Controller, get, patch, post
from litestar.datastructures import UploadFile  # noqa: TC002
from litestar.enums import RequestEncodingType
from litestar.exceptions import ClientException
from litestar.params import Body
from litestar.status_codes import HTTP_409_CONFLICT, HTTP_422_UNPROCESSABLE_ENTITY

from app.auth.deps import CurrentUser, DbDep, VerifiedUser
from app.auth.staff import is_staff_email
from app.config import get_settings
from app.crud.user import update
from app.middleware import check_rate_limit
from app.schemas import (
    UpdateOnboardingRoleRequest,
    UpdateProfileRequest,
    UpdateSettingsRequest,
    UserResponse,
)
from app.storage import delete_object, get_object_url, upload_bytes

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB
# #747: magic bytes for allowed image types
_MAGIC_BYTES: dict[str, bytes] = {
    "image/png": b"\x89PNG",
    "image/jpeg": b"\xff\xd8\xff",
    "image/webp": b"RIFF",
}


class UsersController(Controller):
    path = "/me"
    tags: ClassVar[Sequence[str]] = ["users"]

    @get("")
    async def get_me(self, user: CurrentUser) -> UserResponse:
        """Get current user profile."""
        resp = UserResponse.model_validate(user)
        resp.is_staff = is_staff_email(user.email, get_settings().staff.emails)
        return resp

    @patch("")
    async def update_profile(
        self,
        data: UpdateProfileRequest,
        user: VerifiedUser,
        db: DbDep,
    ) -> UserResponse:
        """Update current user profile.

        #844: ``exclude_unset=True`` so an absent field is not forwarded (no
        change) while an explicit ``null`` is forwarded as a clear. crud.update
        (#547) applies ``None`` verbatim (only ``UNSET`` is skipped).
        """
        # #750: rate limit profile updates
        await check_rate_limit(f"profile:{user.id}", max_requests=20, window_seconds=300)
        updated = await update(db, user, **data.model_dump(exclude_unset=True))
        return UserResponse.model_validate(updated)

    @patch("/settings")
    async def update_settings(
        self,
        data: UpdateSettingsRequest,
        user: VerifiedUser,
        db: DbDep,
    ) -> UserResponse:
        """Update current user preferences."""
        from app.crud.session import UNSET

        updated = await update(
            db,
            user,
            language=data.language if data.language is not None else UNSET,
            timezone=data.timezone if data.timezone is not None else UNSET,
            theme=data.theme if data.theme is not None else UNSET,
            angular_unit=data.angular_unit if data.angular_unit is not None else UNSET,
        )
        return UserResponse.model_validate(updated)

    @patch("/onboarding")
    async def update_onboarding_role(
        self,
        data: UpdateOnboardingRoleRequest,
        user: VerifiedUser,
        db: DbDep,
    ) -> UserResponse:
        """Update user's onboarding role."""
        # #751: reject if onboarding_role already set
        if user.onboarding_role is not None:
            raise ClientException(
                status_code=HTTP_409_CONFLICT,
                detail="Onboarding role already set",
            )
        updated = await update(db, user, onboarding_role=data.onboarding_role)
        return UserResponse.model_validate(updated)

    @post("/avatar", status_code=200)
    async def upload_avatar(
        self,
        user: VerifiedUser,
        db: DbDep,
        data: Annotated[UploadFile, Body(media_type=RequestEncodingType.MULTI_PART)],
    ) -> UserResponse:
        """Upload a profile picture for the current user."""
        # #749: rate limit avatar uploads
        await check_rate_limit(f"avatar:{user.id}", max_requests=10, window_seconds=3600)

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

        # #747: verify actual content matches claimed content-type (magic bytes)
        magic = _MAGIC_BYTES.get(data.content_type, b"")
        if magic and not content.startswith(magic):
            raise ClientException(
                status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File content does not match the declared image type",
            )

        # #754: include content hash in key for cache-busting
        ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }[data.content_type]
        content_hash = hashlib.sha256(content).hexdigest()[:8]
        key = f"avatars/{user.id}/{content_hash}{ext}"

        # #748 + #753: upload S3, then update DB; rollback S3 on DB failure
        try:
            await asyncio.to_thread(upload_bytes, content, key)
        except Exception:
            logger.exception("S3 upload failed for avatar key %s", key)
            raise ClientException(
                status_code=503,
                detail="Storage temporarily unavailable",
            ) from None

        try:
            url = await asyncio.to_thread(get_object_url, key)
            updated = await update(db, user, avatar_url=url)
        except Exception:
            logger.exception("DB update failed after avatar upload for key %s", key)
            # #748: clean up orphaned S3 object
            try:
                await asyncio.to_thread(delete_object, key)
            except Exception:
                logger.warning("Failed to clean up S3 key %s after DB failure", key)
            raise ClientException(
                status_code=503,
                detail="Storage temporarily unavailable",
            ) from None

        return UserResponse.model_validate(updated)
