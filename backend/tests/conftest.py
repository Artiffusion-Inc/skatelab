"""Shared test fixtures for backend tests."""

from __future__ import annotations

import os
import sys
import types
from importlib.util import spec_from_loader
from pathlib import Path
from typing import TYPE_CHECKING

# Fix tqdm.__spec__ missing in CI pytest collection (ultralytics import).
# Must run BEFORE any import that transitively imports ultralytics.
try:
    import tqdm

    if getattr(tqdm, "__spec__", None) is None:
        tqdm.__spec__ = spec_from_loader("tqdm", None)
        tqdm.__spec__.origin = None
        tqdm.__spec__.submodule_search_locations = None
except (ImportError, ValueError):
    # Create a mock tqdm module with __spec__ so ultralytics can import it.
    _fake_tqdm = types.ModuleType("tqdm")
    _fake_tqdm.__spec__ = spec_from_loader("tqdm", None)
    _fake_tqdm.__spec__.origin = None
    _fake_tqdm.__spec__.submodule_search_locations = None

    def _tqdm(iterable=None, **_kwargs):
        if iterable is not None:
            return iterable
        return type(
            "_TqdmMock",
            (),
            {
                "update": lambda *_a: None,
                "close": lambda *_a: None,
                "__enter__": lambda s: s,
                "__exit__": lambda *_a: None,
            },
        )()

    _fake_tqdm.tqdm = _tqdm
    sys.modules["tqdm"] = _fake_tqdm

# Force SKIP_AUTH=false for all tests so auth logic is exercised.
# Must happen before any import of app.config (which caches settings via @lru_cache).
os.environ["APP_SKIP_AUTH"] = "false"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-backend-tests-32b"

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from app.auth.security import create_access_token, hash_password
from app.config import get_settings
from app.di import dependencies
from app.models import Base
from app.models.user import User
from litestar.di import Provide
from litestar.testing import AsyncTestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from litestar.config.app import AppConfig

# Clear cached settings so APP_SKIP_AUTH=false takes effect
get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_engine():
    """Create a test database engine (SQLite in-memory for unit tests)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def authed_user(db_session: AsyncSession) -> User:
    user = User(
        email="user@example.com",
        hashed_password=hash_password("pass"),
        display_name="Test User",
        bio="Skater",
        height_cm=175,
        weight_kg=70.0,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(authed_user: User):
    with patch("app.auth.security.get_settings") as mock_get:
        mock_get.return_value = MagicMock(
            jwt=MagicMock(
                secret_key=MagicMock(
                    get_secret_value=lambda: "test-secret-key-for-backend-tests-32b"
                ),
                access_token_expire_minutes=15,
            )
        )
        token = create_access_token(user_id=authed_user.id)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Litestar shared fixtures
# ---------------------------------------------------------------------------


class _FakeValkey:
    """Fake Valkey that never rate-limits (default for tests)."""

    async def ping(self):
        """PONG — pool validation check."""
        return True

    async def aclose(self):
        """No-op close for test fake."""

    def pipeline(self):
        class _Pipe:
            async def execute(self):
                return [1, 60]

            def incr(self, key):
                pass

            def ttl(self, key):
                return 60

        return _Pipe()

    async def expire(self, key, seconds):
        pass


@pytest.fixture
def app():
    """Build a Litestar app with external dependencies mocked."""
    from app.task_manager import _set_test_pool

    _set_test_pool(_FakeValkey())
    try:
        with patch("app.main.configure_logging"):
            with patch("app.lifespan.init_valkey_pool", new_callable=AsyncMock):
                with patch("app.lifespan.close_valkey_pool", new_callable=AsyncMock):
                    with patch(
                        "app.lifespan.create_pool", new_callable=AsyncMock
                    ) as mock_create_pool:
                        mock_pool = AsyncMock()
                        mock_create_pool.return_value = mock_pool

                        with patch("app.storage.get_s3_async_client", new_callable=AsyncMock):
                            with patch("app.storage.close_s3_clients", new_callable=AsyncMock):
                                with patch("app.main.get_settings") as mock_get:
                                    settings = MagicMock()
                                    settings.cors.origins = [
                                        "http://localhost:3000",
                                        "https://skatelab.ru",
                                    ]
                                    settings.jwt.secret_key.get_secret_value.return_value = (
                                        "test-secret-key-for-backend-tests-32b"
                                    )
                                    settings.valkey.host = "localhost"
                                    settings.valkey.port = 6379
                                    settings.valkey.db = 0
                                    settings.valkey.password.get_secret_value.return_value = ""
                                    settings.valkey.build_url.return_value = (
                                        "redis://localhost:6379/0"
                                    )
                                    settings.app.log_level = "INFO"
                                    settings.app.skip_auth = True
                                    settings.jwt.refresh_token_expire_days = 7
                                    mock_get.return_value = settings

                                    class DummyRateLimitMiddleware:
                                        def __init__(self, app):
                                            self.app = app

                                        async def __call__(self, scope, receive, send):
                                            await self.app(scope, receive, send)

                                    with patch("app.main.RateLimitConfig") as mock_rl_cls:
                                        mock_rl_cls.return_value = MagicMock(
                                            middleware=DummyRateLimitMiddleware
                                        )

                                        with patch("app.main.ResponseCacheConfig") as mock_rc:
                                            mock_rc.return_value = None

                                            from app.main import create_app

                                            litestar_app = create_app()
                                            litestar_app.state.arq_pool = AsyncMock()
                                            yield litestar_app
    finally:
        _set_test_pool(None)


@pytest.fixture
async def client(db_engine, db_session):
    """Provide an AsyncTestClient with the db dependency overridden to use the test session."""
    from collections.abc import AsyncGenerator
    from contextlib import ExitStack

    async def _provide_test_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def on_app_init(app_config: AppConfig) -> AppConfig:
        app_config.dependencies["db"] = Provide(_provide_test_db)
        return app_config

    from app.main import create_app
    from app.task_manager import _set_test_pool

    _set_test_pool(_FakeValkey())

    class DummyRateLimitMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)

    with ExitStack() as stack:
        stack.enter_context(patch("app.main.configure_logging"))
        stack.enter_context(patch("app.lifespan.init_valkey_pool", new_callable=AsyncMock))
        stack.enter_context(patch("app.lifespan.close_valkey_pool", new_callable=AsyncMock))
        mock_create_pool = stack.enter_context(
            patch("app.lifespan.create_pool", new_callable=AsyncMock)
        )
        mock_create_pool.return_value = AsyncMock()
        stack.enter_context(patch("app.storage.get_s3_async_client", new_callable=AsyncMock))
        stack.enter_context(patch("app.storage.close_s3_clients", new_callable=AsyncMock))

        mock_get = stack.enter_context(patch("app.main.get_settings"))
        settings = MagicMock()
        settings.cors.origins = ["http://localhost:3000", "https://skatelab.ru"]
        settings.jwt.secret_key.get_secret_value.return_value = (
            "test-secret-key-for-backend-tests-32b"
        )
        settings.valkey.host = "localhost"
        settings.valkey.port = 6379
        settings.valkey.db = 0
        settings.valkey.password.get_secret_value.return_value = ""
        settings.valkey.build_url.return_value = "redis://localhost:6379/0"
        settings.app.log_level = "INFO"
        settings.app.skip_auth = True
        settings.jwt.refresh_token_expire_days = 7
        mock_get.return_value = settings

        mock_rl_cls = stack.enter_context(patch("app.main.RateLimitConfig"))
        mock_rl_cls.return_value = MagicMock(middleware=DummyRateLimitMiddleware)

        mock_rc = stack.enter_context(patch("app.main.ResponseCacheConfig"))
        mock_rc.return_value = None

        test_app = create_app(on_app_init=[on_app_init])
        test_app.state.arq_pool = AsyncMock()
        test_app.state.test_db_session = db_session

        async with AsyncTestClient(test_app) as c:
            yield c

    _set_test_pool(None)
