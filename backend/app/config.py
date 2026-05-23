"""Application settings (single source of truth).

Uses pydantic-settings with nested config groups and env prefixes.
All services read configuration from one .env file.

Env Prefixes:
  VALKEY_     — queue / cache
  DATABASE_   — PostgreSQL
  JWT_        — authentication tokens
  CORS_       — cross-origin policy
  R2_         — Cloudflare R2 object storage
  VASTAI_     — remote GPU
  RESEND_     — transactional email
  SENTRY_     — error monitoring
  APP_        — general (host, port, dirs, logging)
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings as _BaseSettings
from pydantic_settings import SettingsConfigDict

# Look for .env in project root (one level up from backend/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class BaseSettings(_BaseSettings):
    """Shared model_config for all nested groups."""

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# ---------------------------------------------------------------------------
# Nested groups
# ---------------------------------------------------------------------------


class ValkeyConfig(BaseSettings):
    """Valkey / Redis queue settings."""

    url: str = ""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: SecretStr = SecretStr("")

    def build_url(self) -> str:
        if self.url:
            return self.url
        auth = f":{self.password.get_secret_value()}@" if self.password.get_secret_value() else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"

    class Config:
        env_prefix = "VALKEY_"


class DatabaseConfig(BaseSettings):
    """PostgreSQL connection settings."""

    url: str = "postgresql+asyncpg://skatelab:skatelab_dev@localhost:5432/skatelab"

    class Config:
        env_prefix = "DATABASE_"


class JWTConfig(BaseSettings):
    """JWT authentication settings."""

    secret_key: SecretStr = SecretStr("change-me-to-a-random-secret")
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    class Config:
        env_prefix = "JWT_"


class CORSConfig(BaseSettings):
    """Cross-origin resource sharing."""

    origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    class Config:
        env_prefix = "CORS_"


class R2Config(BaseSettings):
    """Cloudflare R2 object storage (S3-compatible)."""

    access_key_id: SecretStr = SecretStr("")
    secret_access_key: SecretStr = SecretStr("")
    bucket: str = "skatelab-pipeline"
    endpoint_url: str = ""
    presign_expires: int = 3600

    class Config:
        env_prefix = "R2_"


class VastAIConfig(BaseSettings):
    """Vast.ai Serverless GPU settings."""

    api_key: SecretStr = SecretStr("")
    endpoint_name: str = "skatelab-workers"

    class Config:
        env_prefix = "VASTAI_"


class ResendConfig(BaseSettings):
    """Resend email service settings."""

    api_key: SecretStr = SecretStr("")
    from_email: str = "noreply@skatelab.ru"
    from_name: str = "SkateLab"
    reset_url_template: str = "https://skatelab.ru/reset-password?token={token}"
    verify_url_template: str = "https://skatelab.ru/verify-email?token={token}"
    dashboard_url: str = "https://skatelab.ru/dashboard"

    class Config:
        env_prefix = "RESEND_"


class SentryConfig(BaseSettings):
    """Sentry error monitoring settings."""

    dsn: SecretStr = SecretStr("")
    environment: str = "development"
    traces_sample_rate: float = 0.1
    profiles_sample_rate: float = 0.1

    class Config:
        env_prefix = "SENTRY_"


class AppConfig(BaseSettings):
    """General application settings."""

    host: str = "127.0.0.1"
    port: int = 8000
    worker_max_jobs: int = 1  # For local GPU processing (removed). Use worker_max_jobs_remote.
    worker_max_jobs_remote: int = 5
    worker_retry_delays: list[int] = [30, 120]
    log_level: str = "INFO"
    omp_num_threads: int = 2
    task_ttl_seconds: int = 86400
    skip_auth: bool = False
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    class Config:
        env_prefix = "APP_"


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Application settings — single source of truth."""

    valkey: ValkeyConfig = Field(default_factory=ValkeyConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)
    cors: CORSConfig = Field(default_factory=CORSConfig)
    r2: R2Config = Field(default_factory=R2Config)
    vastai: VastAIConfig = Field(default_factory=VastAIConfig)
    resend: ResendConfig = Field(default_factory=ResendConfig)
    sentry: SentryConfig = Field(default_factory=SentryConfig)
    app: AppConfig = Field(default_factory=AppConfig)

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance (singleton)."""
    return Settings()


settings = get_settings()
