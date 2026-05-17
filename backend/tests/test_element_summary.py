"""Tests for GET /metrics/element-summary batched endpoint."""

import pytest


async def test_element_summary_requires_auth(client):
    """Unauthenticated GET /metrics/element-summary returns 401."""
    response = await client.get("/api/v1/metrics/element-summary?element=axel")
    assert response.status_code == 401


async def test_element_summary_returns_structure(client, auth_headers):
    """When authenticated, returns the expected structure."""
    response = await client.get(
        "/api/v1/metrics/element-summary?element=axel&period=30d",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["element"] == "axel"
    assert data["period"] == "30d"
    assert "trend" in data
    assert "findings" in data
    assert "metric_defs" in data
    assert "personal_records" in data


async def test_element_summary_default_period(client, auth_headers):
    """Default period is 30d when not specified."""
    response = await client.get(
        "/api/v1/metrics/element-summary?element=lutz",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["period"] == "30d"
