"""Tests for TAS inference pipeline."""

from pathlib import Path

import numpy as np
import pytest
import torch

from src.tas.model import BiGRUTASRefiner

try:
    from ml.src.tas.inference import TASElementSegmenter
except ImportError:
    import sys
    from pathlib import Path as Path2

    sys.path.insert(0, str(Path2(__file__).parent.parent.parent / "src"))
    from tas.inference import TASElementSegmenter


def _export_onnx(model: torch.nn.Module, path: str) -> None:
    """Export a BiGRUTASRefiner model to ONNX (legacy exporter for pack_padded_sequence compat)."""
    model.eval()
    dummy_poses = torch.randn(1, 50, 17, 2)
    dummy_lengths = torch.tensor([50], dtype=torch.long)
    torch.onnx.export(
        model,
        (dummy_poses, dummy_lengths),
        path,
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


def test_tas_inference_onnx():
    """TASElementSegmenter loads ONNX model and produces segments."""
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    onnx_path = "/tmp/test_tas_refiner.onnx"
    _export_onnx(model, onnx_path)

    segmenter = TASElementSegmenter(
        model_path=Path(onnx_path),
        classifier_path=None,
        device="cpu",
    )
    poses = np.random.randn(100, 17, 2).astype(np.float32)
    segments = segmenter.segment(poses, fps=30.0)
    assert isinstance(segments, list)
    for seg in segments:
        assert seg["element_type"] in ("Jump", "Spin", "Step", "None")
        assert seg["start"] <= seg["end"]
        assert 0 <= seg["confidence"] <= 1


def test_tas_min_duration_filter():
    """Segments shorter than element-type minimum duration are filtered."""
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    model.eval()
    # Force all-Jump by biasing classifier
    with torch.no_grad():
        model.refiner.classifier.bias.zero_()
        model.refiner.classifier.bias[1] = 10.0  # Jump class
    onnx_path = "/tmp/test_tas_min_dur.onnx"
    _export_onnx(model, onnx_path)

    segmenter = TASElementSegmenter(
        model_path=Path(onnx_path),
        device="cpu",
    )
    # 10 frames at 30fps = 0.33s < 0.5s Jump minimum -> filtered
    poses = np.random.randn(10, 17, 2).astype(np.float32)
    segments = segmenter.segment(poses, fps=30.0)
    assert len(segments) == 0


def test_tas_min_duration_spin_longer():
    """Spin segments shorter than 2.0s are filtered."""
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    model.eval()
    with torch.no_grad():
        model.refiner.classifier.bias.zero_()
        model.refiner.classifier.bias[2] = 10.0  # Spin class
    onnx_path = "/tmp/test_tas_spin_min.onnx"
    _export_onnx(model, onnx_path)

    segmenter = TASElementSegmenter(
        model_path=Path(onnx_path),
        device="cpu",
    )
    # 30 frames at 30fps = 1.0s < 2.0s Spin minimum -> filtered
    poses = np.random.randn(30, 17, 2).astype(np.float32)
    segments = segmenter.segment(poses, fps=30.0)
    assert len(segments) == 0


def test_tas_segment_valid_duration():
    """Segments exceeding minimum duration are kept."""
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    model.eval()
    with torch.no_grad():
        model.refiner.classifier.bias.zero_()
        model.refiner.classifier.bias[1] = 10.0  # Jump class
    onnx_path = "/tmp/test_tas_valid_dur.onnx"
    _export_onnx(model, onnx_path)

    segmenter = TASElementSegmenter(
        model_path=Path(onnx_path),
        device="cpu",
    )
    # 60 frames at 30fps = 2.0s > 0.5s Jump minimum -> kept
    poses = np.random.randn(60, 17, 2).astype(np.float32)
    segments = segmenter.segment(poses, fps=30.0)
    assert len(segments) >= 1
    assert segments[0]["element_type"] in ("Jump", "Spin", "Step", "None")


if __name__ == "__main__":
    test_tas_inference_onnx()
    test_tas_min_duration_filter()
    test_tas_min_duration_spin_longer()
    test_tas_segment_valid_duration()
    print("ALL INFERENCE TESTS PASSED")
