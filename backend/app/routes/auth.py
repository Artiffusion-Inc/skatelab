"""Auth API routes: register, login, refresh, logout."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Sequence  # noqa: TC003
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from litestar import Controller, Request, post
from litestar.exceptions import ClientException
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED, HTTP_204_NO_CONTENT

from app.auth.deps import DbDep
from app.auth.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.config import get_settings
from app.crud.password_reset_token import (
    create as create_password_reset_token_crud,
)
from app.crud.password_reset_token import (
    get_by_hash as get_password_reset_by_hash,
)
from app.crud.password_reset_token import (
    mark_used as mark_password_reset_used,
)
from app.crud.refresh_token import create as create_refresh_token_crud
from app.crud.refresh_token import get_active_by_hash, mark_used, revoke, revoke_family
from app.crud.user import create as create_user
from app.crud.user import get_by_email
from app.crud.user import get_by_id as get_user_by_id
from app.crud.verification_token import (
    create as create_verification_token_crud,
)
from app.crud.verification_token import (
    get_by_hash as get_verification_by_hash,
)
from app.crud.verification_token import (
    mark_used as mark_verification_used,
)
from app.middleware import check_rate_limit
from app.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.services.email import EmailService

settings = get_settings()


class AuthController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["auth"]

    async def _issue_token_pair(
        self, db: DbDep, user_id: str, family_id: str | None = None
    ) -> TokenResponse:
        """Create and persist a new access + refresh token pair."""
        access = create_access_token(user_id=user_id)
        refresh_str = create_refresh_token()
        fam = family_id or str(uuid.uuid4())
        await create_refresh_token_crud(
            db,
            user_id=user_id,
            token_hash=hash_token(refresh_str),
            family_id=fam,
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt.refresh_token_expire_days),
        )
        return TokenResponse(access_token=access, refresh_token=refresh_str)

    @post("/register", status_code=HTTP_201_CREATED)
    async def register(self, request: Request, db: DbDep, data: RegisterRequest) -> TokenResponse:
        """Register a new user."""
        ip = request.client.host if request.client else "unknown"
        await check_rate_limit(f"register_ip:{ip}", max_requests=5, window_seconds=60)
        await check_rate_limit(f"register_email:{data.email}", max_requests=3, window_seconds=3600)

        existing = await get_by_email(db, data.email)
        if existing:
            raise ClientException(
                status_code=409,
                detail="Email already registered",
            )

        user = await create_user(
            db,
            email=data.email,
            hashed_password=hash_password(data.password),
            display_name=data.display_name,
        )
        return await self._issue_token_pair(db, user.id)

    @post("/login", status_code=HTTP_200_OK)
    async def login(self, request: Request, db: DbDep, data: LoginRequest) -> TokenResponse:
        """Authenticate and return tokens."""
        ip = request.client.host if request.client else "unknown"
        await check_rate_limit(f"login_ip:{ip}", max_requests=10, window_seconds=60)
        await check_rate_limit(f"login_email:{data.email}", max_requests=5, window_seconds=300)

        user = await get_by_email(db, data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise ClientException(
                status_code=401,
                detail="Invalid email or password",
            )
        return await self._issue_token_pair(db, user.id)

    @post("/refresh", status_code=HTTP_200_OK)
    async def refresh(self, request: Request, db: DbDep, data: RefreshRequest) -> TokenResponse:
        """Rotate refresh token and issue new token pair."""
        ip = request.client.host if request.client else "unknown"
        await check_rate_limit(f"refresh_ip:{ip}", max_requests=20, window_seconds=60)

        token_hash = hash_token(data.refresh_token)
        existing = await get_active_by_hash(db, token_hash)
        if not existing:
            raise ClientException(
                status_code=401,
                detail="Invalid or expired refresh token",
            )

        # Reuse detection: if already used, assume theft → revoke entire family
        if existing.last_used_at is not None:
            await revoke_family(db, existing.family_id)
            raise ClientException(
                status_code=401,
                detail="Token reuse detected. All sessions revoked.",
            )

        await mark_used(db, existing)
        return await self._issue_token_pair(db, existing.user_id, family_id=existing.family_id)

    @post("/forgot-password", status_code=HTTP_200_OK)
    async def forgot_password(
        self, request: Request, db: DbDep, data: ForgotPasswordRequest
    ) -> MessageResponse:
        """Request a password-reset email."""
        ip = request.client.host if request.client else "unknown"
        await check_rate_limit(f"forgot_ip:{ip}", max_requests=3, window_seconds=3600)

        user = await get_by_email(db, data.email)
        if not user:
            return MessageResponse(message="If email exists, reset link sent")

        raw_token = create_password_reset_token()
        token_hash = hash_token(raw_token)
        await create_password_reset_token_crud(
            db,
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        email_svc = EmailService()
        with contextlib.suppress(Exception):
            await email_svc.send_password_reset(
                to=data.email, token=raw_token, locale=user.language
            )

        return MessageResponse(message="If email exists, reset link sent")

    @post("/reset-password", status_code=HTTP_200_OK)
    async def reset_password(
        self, request: Request, db: DbDep, data: ResetPasswordRequest
    ) -> MessageResponse:
        """Reset password using a valid reset token."""
        ip = request.client.host if request.client else "unknown"
        await check_rate_limit(f"reset_ip:{ip}", max_requests=5, window_seconds=3600)

        token_hash = hash_token(data.token)
        existing = await get_password_reset_by_hash(db, token_hash)
        if not existing:
            raise ClientException(
                status_code=400,
                detail="Invalid or expired reset token",
            )

        user = await get_user_by_id(db, existing.user_id)
        if not user:
            raise ClientException(
                status_code=400,
                detail="Invalid or expired reset token",
            )

        user.hashed_password = hash_password(data.password)
        db.add(user)
        await mark_password_reset_used(db, existing)
        await db.flush()

        return MessageResponse(message="Password reset successfully")

    @post("/logout", status_code=HTTP_204_NO_CONTENT)
    async def logout(self, db: DbDep, data: RefreshRequest) -> None:
        """Revoke a refresh token (client should also discard access token)."""
        token_hash = hash_token(data.refresh_token)
        existing = await get_active_by_hash(db, token_hash)
        if existing:
            await revoke(db, existing)

    @post("/verify-email", status_code=HTTP_200_OK)
    async def verify_email(
        self, request: Request, db: DbDep, data: VerifyEmailRequest
    ) -> MessageResponse:
        """Verify user email with token from verification link."""
        ip = request.client.host if request.client else "unknown"
        await check_rate_limit(f"verify_ip:{ip}", max_requests=10, window_seconds=300)

        token_hash = hash_token(data.token)
        existing = await get_verification_by_hash(db, token_hash)
        if not existing:
            raise ClientException(
                status_code=400,
                detail="Invalid or expired verification token",
            )

        user = await get_user_by_id(db, existing.user_id)
        if not user:
            raise ClientException(
                status_code=400,
                detail="Invalid or expired verification token",
            )

        user.is_verified = True
        db.add(user)
        await mark_verification_used(db, existing)
        await db.flush()

        return MessageResponse(message="Email verified successfully")

    @post("/resend-verification", status_code=HTTP_200_OK)
    async def resend_verification(
        self, request: Request, db: DbDep, data: ResendVerificationRequest
    ) -> MessageResponse:
        """Resend email verification link."""
        ip = request.client.host if request.client else "unknown"
        await check_rate_limit(f"resend_ip:{ip}", max_requests=3, window_seconds=3600)

        user = await get_by_email(db, data.email)
        if not user or user.is_verified:
            return MessageResponse(message="If email exists and unverified, verification sent")

        raw_token = create_password_reset_token()
        token_hash = hash_token(raw_token)
        await create_verification_token_crud(
            db,
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )

        email_svc = EmailService()
        with contextlib.suppress(Exception):
            await email_svc.send_email_verification(
                to=data.email, token=raw_token, locale=user.language
            )

        return MessageResponse(message="If email exists and unverified, verification sent")
