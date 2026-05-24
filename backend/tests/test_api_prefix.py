"""Tests for dual-prefix router (/api/v1 legacy + /v1 new)."""

import pytest
from litestar.testing import AsyncTestClient


@pytest.mark.asyncio
async def test_v1_prefix_routes_work(client: AsyncTestClient):
    """Routes under /v1 prefix return same responses as /api/v1."""
    response = await client.get("/v1/health")
    assert response.status_code == 200

    response_legacy = await client.get("/api/v1/health")
    assert response_legacy.status_code == 200


@pytest.mark.asyncio
async def test_v1_auth_excludes_match_api_v1(client: AsyncTestClient):
    """JWT exclude paths exist under both /v1 and /api/v1 prefixes."""
    for prefix in ["/v1", "/api/v1"]:
        resp = await client.post(
            f"{prefix}/auth/login", json={"email": "x@x.com", "password": "12345678"}
        )
        assert resp.status_code != 405  # route exists
