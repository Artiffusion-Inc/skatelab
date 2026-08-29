"""Tests for models route (list available ML models on disk)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest


@pytest.fixture
def fake_models_dir(tmp_path):
    """Create a temp directory with some model files present and some missing."""
    # Create files that "exist"
    (tmp_path / "depth_anything_v2_small.onnx").write_bytes(b"\x00" * (5 * 1024 * 1024))  # 5MB
    (tmp_path / "neuflowv2_mixed.onnx").write_bytes(
        b"\x00" * (12 * 1024 * 1024 + 500_000)
    )  # ~12.5MB

    # Create subdirectory for segment model
    sam2_dir = tmp_path / "sam2"
    sam2_dir.mkdir()
    (sam2_dir / "vision_encoder.onnx").write_bytes(b"\x00" * (45 * 1024 * 1024))  # 45MB

    # foot_tracker.onnx, rvm_mobilenetv3.onnx, lama_fp32.onnx are NOT created
    return tmp_path


@pytest.mark.asyncio
async def test_list_models_returns_six_entries(client, auth_headers, fake_models_dir: Path):
    """GET /models returns exactly 6 model entries (auth required)."""
    with patch("app.routes.models._get_models_dir", return_value=fake_models_dir):
        response = await client.get("/v1/models", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 6


@pytest.mark.asyncio
async def test_list_models_available_flags(client, auth_headers, fake_models_dir: Path):
    """GET /models correctly reports available=True/False based on file existence."""
    with patch("app.routes.models._get_models_dir", return_value=fake_models_dir):
        response = await client.get("/v1/models", headers=auth_headers)

    data = response.json()
    by_id = {m["id"]: m for m in data}

    # These files were created
    assert by_id["lift_3d"]["available"] is True
    assert by_id["optical_flow"]["available"] is True
    assert by_id["segment"]["available"] is True

    # These files were NOT created
    assert by_id["foot_track"]["available"] is False
    assert by_id["matting"]["available"] is False
    assert by_id["inpainting"]["available"] is False


@pytest.mark.asyncio
async def test_list_models_all_missing(client, auth_headers, tmp_path: Path):
    """GET /models with no files returns all available=False."""
    empty_dir = tmp_path / "empty_models"
    empty_dir.mkdir()

    with patch("app.routes.models._get_models_dir", return_value=empty_dir):
        response = await client.get("/v1/models", headers=auth_headers)

    data = response.json()
    assert len(data) == 6
    for model in data:
        assert model["available"] is False


@pytest.mark.asyncio
async def test_list_models_response_schema(client, auth_headers, fake_models_dir: Path):
    """GET /models response matches ModelStatus schema (id, available)."""
    with patch("app.routes.models._get_models_dir", return_value=fake_models_dir):
        response = await client.get("/v1/models", headers=auth_headers)

    data = response.json()
    for model in data:
        assert "id" in model
        assert "available" in model
        # #778: size_mb no longer in response
        assert "size_mb" not in model
        assert isinstance(model["available"], bool)


@pytest.mark.asyncio
async def test_list_models_requires_auth(client):
    """#775: GET /models requires authentication (removed from JWT exclude)."""
    response = await client.get("/v1/models")
    assert response.status_code == 401
