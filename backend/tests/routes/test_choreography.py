"""Tests for choreography routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from litestar.testing import AsyncTestClient


@pytest.mark.anyio
async def test_elements_registry_returns_all_elements(client: AsyncTestClient) -> None:
    response = await client.get("/api/v1/choreography/elements/registry")
    assert response.status_code == 200
    data = response.json()
    assert len(data["elements"]) >= 30  # jumps + spins + sequences
    codes = [el["code"] for el in data["elements"]]
    assert "3Lz" in codes
    assert "CSp4" in codes
    assert "StSq4" in codes
    assert "ChSq1" in codes
    assert data["season"] == "2025_26"
    # Verify type strings are valid
    for el in data["elements"]:
        assert el["type"] in {"jump", "spin", "step_sequence", "choreo_sequence"}
        assert el["base_value"] > 0
