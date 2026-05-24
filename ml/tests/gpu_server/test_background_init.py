"""Test _background_init works without R2 model download."""

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def mock_model_paths(tmp_path):
    """Create fake model files and patch paths."""
    mog = tmp_path / "moganet" / "moganet_b_ap2d_384x288.onnx"
    rf_detr = tmp_path / "rf_detr_nano.onnx"
    mog.parent.mkdir(parents=True, exist_ok=True)
    mog.write_bytes(b"fake-moganet")
    rf_detr.write_bytes(b"fake-rf-detr")
    return mog, rf_detr


@pytest.mark.asyncio
async def test_background_init_succeeds_when_models_exist(mock_model_paths):
    mog, rf_detr = mock_model_paths
    import gpu_server.server as srv

    with (
        patch.object(srv, "MOGANET_MODEL_PATH", mog),
        patch.object(srv, "RF_DETR_MODEL_PATH", rf_detr),
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
        patch.object(srv, "RF_DETR_MODEL_PATH", tmp_path / "also_missing.onnx"),
    ):
        await srv._background_init()
        assert srv._models_ready is False
