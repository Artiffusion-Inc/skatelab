"""Tests for TAS inference pipeline."""

from pathlib import Path

import numpy as np
import pytest
import torch

try:
    from ml.src.tas.inference import TASElementSegmenter
    from ml.src.tas.model import BiGRUTAS
except ImportError:
    import sys
    from pathlib import Path as Path2

    sys.path.insert(0, str(Path2(__file__).parent.parent.parent / "src"))
    from tas.inference import TASElementSegmenter
    from tas.model import BiGRUTAS


def test_tas_inference():
    # Create a small model for testing
    model = BiGRUTAS(hidden_dim=32, num_layers=1)
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "config": {"hidden_dim": 32, "num_layers": 1, "dropout": 0.0},
    }
    torch.save(checkpoint, "/tmp/test_tas.pt")

    segmenter = TASElementSegmenter(
        model_path=Path("/tmp/test_tas.pt"),
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


if __name__ == "__main__":
    test_tas_inference()
    print("ALL INFERENCE TESTS PASSED")
