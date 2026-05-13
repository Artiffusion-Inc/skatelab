"""Tests for choreography routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.models.choreography import MusicAnalysis

if TYPE_CHECKING:
    from litestar.testing import AsyncTestClient
    from sqlalchemy.ext.asyncio import AsyncSession


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


@pytest.mark.anyio
async def test_create_program_persists_music_analysis_id(
    client: AsyncTestClient,
    auth_headers: dict,
    db_session: AsyncSession,
) -> None:
    music = MusicAnalysis(
        user_id="test-user-id",
        filename="test.mp3",
        audio_url="https://example.com/test.mp3",
        duration_sec=120.0,
    )
    db_session.add(music)
    await db_session.flush()
    await db_session.refresh(music)

    response = await client.post(
        "/api/v1/choreography/programs",
        json={
            "discipline": "mens_singles",
            "segment": "free_skate",
            "music_analysis_id": music.id,
            "title": "Test Program",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["music_analysis_id"] == music.id
