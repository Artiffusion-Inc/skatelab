"""Tests for /v1 prefix router."""

import pytest
from litestar.testing import AsyncTestClient


@pytest.mark.asyncio
async def test_v1_prefix_routes_work(client: AsyncTestClient):
    """Routes under /v1 prefix return expected responses."""
    response = await client.get("/v1/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_v1_auth_routes_exist(client: AsyncTestClient):
    """JWT-excluded auth routes exist under /v1."""
    resp = await client.post("/v1/auth/login", json={"email": "x@x.com", "password": "12345678"})
    assert resp.status_code != 405
