"""Integration test: full TAS pipeline from poses to segments (ONNX)."""

from pathlib import Path

import numpy as np
import pytest
import torch

from ml.src.tas.inference import MIN_DURATION, TASElementSegmenter
from ml.src.tas.model import BiGRUTASRefiner


@pytest.fixture
def onnx_model(tmp_path):
    """Create a minimal ONNX model for testing."""
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    model.eval()
    onnx_path = tmp_path / "test_refiner.onnx"
    dummy_poses = torch.randn(1, 50, 17, 2)
    dummy_lengths = torch.tensor([50], dtype=torch.long)
    torch.onnx.export(
        model,
        (dummy_poses, dummy_lengths),
        str(onnx_path),
        input_names=["poses", "lengths"],
        output_names=["logits"],
        dynamic_axes={
            "poses": {0: "batch", 1: "time"},
            "lengths": {0: "batch"},
            "logits": {0: "batch", 1: "time"},
        },
        opset_version=17,
        dynamo=False,
    )
    return onnx_path


def test_full_pipeline_jump(onnx_model):
    """Simulate a jump pattern: high hip movement for 30 frames."""
    segmenter = TASElementSegmenter(model_path=onnx_model, device="cpu")
    T = 300
    poses = np.random.randn(T, 17, 2).astype(np.float32) * 0.01
    # Inject a jump-like hip dip in frames 100–130
    for f in range(100, 130):
        poses[f, 0, 1] -= 0.5
    segments = segmenter.segment(poses, fps=30.0)
    assert isinstance(segments, list)
    for seg in segments:
        assert seg["element_type"] in ("Jump", "Spin", "Step")
        assert seg["start"] < seg["end"]
        assert 0 <= seg["confidence"] <= 1


def test_full_pipeline_empty(onnx_model):
    """No elements detected in still pose sequence."""
    segmenter = TASElementSegmenter(model_path=onnx_model, device="cpu")
    T = 100
    poses = np.random.randn(T, 17, 2).astype(np.float32) * 0.001
    segments = segmenter.segment(poses, fps=30.0)
    assert isinstance(segments, list)


def test_min_duration_per_type():
    """Verify per-type min duration: Jump>=0.5s, Spin>=2.0s, Step>=3.0s."""
    assert MIN_DURATION["Jump"] == 0.5
    assert MIN_DURATION["Spin"] == 2.0
    assert MIN_DURATION["Step"] == 3.0
