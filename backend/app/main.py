"""Litestar application for SkateLab."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sentry_sdk
import structlog
from litestar import Litestar, Router
from litestar.config.compression import CompressionConfig
from litestar.config.cors import CORSConfig
from litestar.config.response_cache import ResponseCacheConfig
from litestar.exceptions import HTTPException
from litestar.middleware import DefineMiddleware
from litestar.middleware.rate_limit import RateLimitConfig
from litestar.security.jwt import JWTAuth
from sentry_sdk.integrations.litestar import LitestarIntegration

if TYPE_CHECKING:
    from collections.abc import Callable

    from litestar.config.app import AppConfig

from app.auth.deps import retrieve_user_handler
from app.config import get_settings
from app.di import dependencies
from app.exceptions import http_exception_handler
from app.lifespan import app_lifespan
from app.logging_config import configure_logging
from app.middleware.cookie_auth import CookieToHeaderMiddleware
from app.middleware.posthog_context import PostHogContextMiddleware
from app.models.user import User
from app.routes import (
    auth,
    choreography,
    connections,
    detect,
    metrics,
    misc,
    models,
    process,
    sessions,
    training_plans,
    uploads,
    users,
    workspaces,
)


def init_sentry() -> None:
    settings = get_settings()
    dsn = settings.sentry.dsn.get_secret_value()
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry.environment,
        traces_sample_rate=settings.sentry.traces_sample_rate,
        profiles_sample_rate=settings.sentry.profiles_sample_rate,
        send_default_pii=False,
        integrations=[LitestarIntegration()],
    )


init_sentry()
configure_logging()
logger = structlog.get_logger()


def create_app(
    *,
    on_app_init: Callable[[AppConfig], AppConfig]
    | list[Callable[[AppConfig], AppConfig]]
    | None = None,
) -> Litestar:
    """Build and return the Litestar application."""
    from os import environ

    settings = get_settings()

    if (
        environ.get("SKIP_JWT_SECRET_CHECK") != "true"
        and settings.jwt.secret_key.get_secret_value() == "change-me-to-a-random-secret"
    ):
        raise RuntimeError(
            "JWT secret key is using the default value. "
            "Set JWT_SECRET_KEY environment variable to a secure random string. "
            "Set SKIP_JWT_SECRET_CHECK=true to bypass (dev only)."
        )

    # Assemble router under /v1
    api_v1 = Router(
        path="/v1",
        route_handlers=[
            auth,
            users,
            detect,
            models,
            process,
            misc,
            sessions,
            metrics,
            connections,
            uploads,
            choreography,
            workspaces,
            training_plans,
        ],
    )

    cors_config = CORSConfig(
        allow_origins=settings.cors.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    rate_limit_config = RateLimitConfig(
        rate_limit=("minute", 60),
        exclude=[
            "/v1/health",
            "/v1/docs",
            "/v1/redoc",
            "/v1/openapi.json",
        ],
    )

    jwt_auth = JWTAuth[User](
        token_secret=settings.jwt.secret_key.get_secret_value(),
        retrieve_user_handler=retrieve_user_handler,
        algorithm="HS256",  # noqa: S106
        exclude=[
            "/v1/auth/register",
            "/v1/auth/login",
            "/v1/auth/refresh",
            "/v1/auth/logout",
            "/v1/auth/forgot-password",
            "/v1/auth/reset-password",
            "/v1/auth/verify-email",
            "/v1/auth/resend-verification",
            "/v1/health",
            "/v1/metrics/registry",
            "/v1/metrics/elements",
            "/v1/choreography/elements/registry",
            "/v1/docs",
            "/v1/redoc",
            "/v1/openapi.json",
        ],
    )

    def _inject_cookie_middleware(app_config: AppConfig) -> AppConfig:
        """Insert CookieToHeaderMiddleware at position 0 (before JWTAuth) so it runs first on request."""
        app_config.middleware.insert(0, DefineMiddleware(CookieToHeaderMiddleware))
        app_config.middleware.insert(0, DefineMiddleware(PostHogContextMiddleware))
        return app_config

    # jwt_auth.on_app_init inserts JWTAuth at position 0.
    # Our callback must run AFTER so we can insert at position 0 to push ourselves ahead.
    init_handlers: list[Callable[[AppConfig], AppConfig]] = [
        jwt_auth.on_app_init,
        _inject_cookie_middleware,
    ]
    if on_app_init:
        init_handlers.extend(on_app_init if isinstance(on_app_init, list) else [on_app_init])

    return Litestar(
        route_handlers=[api_v1],
        lifespan=[app_lifespan],
        cors_config=cors_config,
        compression_config=CompressionConfig(backend="gzip"),
        response_cache_config=ResponseCacheConfig(default_expiration=60),
        middleware=[rate_limit_config.middleware],
        exception_handlers={HTTPException: http_exception_handler},
        debug=settings.app.log_level == "DEBUG",
        on_app_init=init_handlers,
        dependencies=dependencies,
    )


# Importable ASGI application
app = create_app()
