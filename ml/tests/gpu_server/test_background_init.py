"""Test _background_init works without R2 model download."""

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def mock_model_paths(tmp_path):
    """Create fake model files and patch paths."""
    mog = tmp_path / "moganet" / "moganet_b_ap2d_384x288.onnx"
    yolo = tmp_path / "yolov8n.onnx"
    mog.parent.mkdir(parents=True, exist_ok=True)
    mog.write_bytes(b"fake-moganet")
    yolo.write_bytes(b"fake-yolo")
    return mog, yolo


@pytest.mark.asyncio
async def test_background_init_succeeds_when_models_exist(mock_model_paths):
    mog, yolo = mock_model_paths
    import gpu_server.server as srv

    with (
        patch.object(srv, "MOGANET_MODEL_PATH", mog),
        patch.object(srv, "YOLO_MODEL_PATH", yolo),
        patch("src.device.DeviceConfig") as MockDC,
    ):
        MockDC.default.return_value.is_cuda = False
        await srv._background_init()
        assert srv._models_ready is True


@pytest.mark.asyncio
async def test_background_init_fails_when_models_missing(tmp_path):
    missing = tmp_path / "nonexistent.onnx"
    import gpu_server.server as srv

    with (
        patch.object(srv, "MOGANET_MODEL_PATH", missing),
        patch.object(srv, "YOLO_MODEL_PATH", tmp_path / "also_missing.onnx"),
    ):
        await srv._background_init()
        assert srv._models_ready is False
