"""Tests for backend/app/main.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litestar.testing import AsyncTestClient


@pytest.fixture
def app():
    """Build Litestar app with external dependencies mocked."""
    with patch("app.main.configure_logging"):
        with patch("app.lifespan.init_valkey_pool", new_callable=AsyncMock):
            with patch("app.lifespan.close_valkey_pool", new_callable=AsyncMock):
                with patch("app.lifespan.create_pool", new_callable=AsyncMock) as mock_create_pool:
                    mock_pool = AsyncMock()
                    mock_create_pool.return_value = mock_pool

                    with patch("app.main.get_settings") as mock_get:
                        settings = MagicMock()
                        settings.cors.origins = ["http://localhost:3000"]
                        settings.jwt.secret_key.get_secret_value.return_value = "test-secret"  # noqa: S105
                        settings.valkey.host = "localhost"
                        settings.valkey.port = 6379
                        settings.valkey.db = 0
                        settings.valkey.password.get_secret_value.return_value = ""
                        settings.valkey.build_url.return_value = "redis://localhost:6379/0"
                        settings.app.log_level = "INFO"
                        settings.app.skip_auth = False
                        mock_get.return_value = settings

                        from app.main import create_app

                        yield create_app()


@pytest.fixture
async def client(app):
    """Provide an AsyncTestClient for the Litestar app."""
    async with AsyncTestClient(app) as c:
        yield c


@pytest.mark.anyio
async def test_health_endpoint(client):
    """GET /api/v1/health returns 200 and status ok."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "valkey" in data


@pytest.mark.anyio
async def test_lifespan_initializes_arq_pool(client):
    """Lifespan context should have started without raising."""
    # If lifespan failed, AsyncTestClient context manager would have raised.
    # A simple successful request proves the app is up.
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


def test_default_jwt_secret_rejected():
    """App fails to start with default JWT secret unless SKIP_JWT_SECRET_CHECK=true."""
    from app.main import create_app

    mock_settings = MagicMock()
    mock_settings.jwt.secret_key.get_secret_value.return_value = "change-me-to-a-random-secret"
    mock_settings.app.log_level = "INFO"

    with patch("app.main.get_settings", return_value=mock_settings):
        with pytest.raises(RuntimeError, match="default value"):
            create_app()


def test_skip_jwt_secret_check_allows_default():
    """SKIP_JWT_SECRET_CHECK=true bypasses the secret check."""
    import os

    from app.main import create_app

    mock_settings = MagicMock()
    mock_settings.jwt.secret_key.get_secret_value.return_value = "change-me-to-a-random-secret"
    mock_settings.cors.origins = []
    mock_settings.app.log_level = "INFO"
    mock_settings.app.skip_auth = False

    with patch("app.main.get_settings", return_value=mock_settings):
        with patch.dict(os.environ, {"SKIP_JWT_SECRET_CHECK": "true"}):
            with patch("app.main.configure_logging"):
                with patch("app.lifespan.init_valkey_pool", new_callable=AsyncMock):
                    with patch("app.lifespan.close_valkey_pool", new_callable=AsyncMock):
                        with patch("app.lifespan.create_pool", new_callable=AsyncMock):
                            app = create_app()
                            assert app is not None
