"""Litestar application for SkateLab."""

from __future__ import annotations

import sentry_sdk
import structlog
from litestar import Litestar, Router
from litestar.config.compression import CompressionConfig
from litestar.config.cors import CORSConfig
from litestar.config.response_cache import ResponseCacheConfig
from litestar.exceptions import HTTPException
from litestar.middleware.rate_limit import RateLimitConfig
from litestar.security.jwt import JWTAuth
from sentry_sdk.integrations.litestar import LitestarIntegration

from app.auth.deps import retrieve_user_handler
from app.config import get_settings
from app.di import dependencies
from app.exceptions import http_exception_handler
from app.lifespan import app_lifespan
from app.logging_config import configure_logging
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


def create_app() -> Litestar:
    """Build and return the Litestar application."""
    settings = get_settings()

    # Assemble routers under /api/v1
    api_v1 = Router(
        path="/api/v1",
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
        exclude=["/api/v1/health", "/api/v1/docs", "/api/v1/redoc", "/api/v1/openapi.json"],
    )

    jwt_auth = JWTAuth[User](
        token_secret=settings.jwt.secret_key.get_secret_value(),
        retrieve_user_handler=retrieve_user_handler,
        algorithm="HS256",  # noqa: S106
        exclude=[
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/auth/forgot-password",
            "/api/v1/auth/reset-password",
            "/api/v1/auth/verify-email",
            "/api/v1/auth/resend-verification",
            "/api/v1/health",
            "/api/v1/models",
            "/api/v1/outputs",
            "/api/v1/metrics/registry",
            "/api/v1/choreography/elements/registry",
            "/api/v1/docs",
            "/api/v1/redoc",
            "/api/v1/openapi.json",
        ],
    )

    return Litestar(
        route_handlers=[api_v1],
        lifespan=[app_lifespan],
        cors_config=cors_config,
        compression_config=CompressionConfig(backend="gzip"),
        response_cache_config=ResponseCacheConfig(default_expiration=60),
        middleware=[rate_limit_config.middleware],
        exception_handlers={HTTPException: http_exception_handler},
        debug=settings.app.log_level == "DEBUG",
        on_app_init=[jwt_auth.on_app_init],
        dependencies=dependencies,
    )


# Importable ASGI application
app = create_app()
