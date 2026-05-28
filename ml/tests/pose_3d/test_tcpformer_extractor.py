"""Tests for TCPFormerExtractor 3D pose lifter wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.pose_3d.tcpformer_extractor import TCPFormerExtractor


@pytest.fixture
def mock_onnx_extractor(monkeypatch):
    """Mock ONNXPoseExtractor to avoid loading heavy ONNX models."""

    class FakeONNXPoseExtractor:
        def __init__(self, model_path, device="auto"):
            self.model_path = Path(model_path)
            self.device = device

        def estimate_3d(self, poses_2d):
            """Return synthetic 3D poses: (N, 17, 3)."""
            n_frames = poses_2d.shape[0]
            poses_3d = np.zeros((n_frames, 17, 3), dtype=np.float32)
            # Put some structure in so it's not all zeros
            poses_3d[:, :, 0] = poses_2d[:, :, 0]
            poses_3d[:, :, 1] = poses_2d[:, :, 1]
            poses_3d[:, :, 2] = 0.5  # constant depth
            return poses_3d

    monkeypatch.setattr(
        "src.pose_3d.tcpformer_extractor.ONNXPoseExtractor",
        FakeONNXPoseExtractor,
    )
    return FakeONNXPoseExtractor


class TestTCPFormerExtractorInit:
    def test_default_init(self, mock_onnx_extractor):
        """Should initialize with default model path and device."""
        extractor = TCPFormerExtractor()
        assert extractor.model_path == Path("data/models/TCPFormer_ap3d_81_fp16.onnx")
        assert extractor._onnx.device == "auto"

    def test_custom_init(self, mock_onnx_extractor):
        """Should accept custom model path and device."""
        extractor = TCPFormerExtractor(
            model_path="custom/model.onnx",
            device="cuda",
        )
        assert extractor.model_path == Path("custom/model.onnx")
        assert extractor._onnx.device == "cuda"

    def test_string_path_converted(self, mock_onnx_extractor):
        """String path should be converted to Path."""
        extractor = TCPFormerExtractor(model_path="/some/path.onnx")
        assert isinstance(extractor.model_path, Path)


class TestTCPFormerExtractorExtractSequence:
    def test_extract_sequence_2d_input(self, mock_onnx_extractor):
        """Should accept (N, 17, 2) input and return (N, 17, 3)."""
        extractor = TCPFormerExtractor()
        poses_2d = np.random.rand(50, 17, 2).astype(np.float32)
        result = extractor.extract_sequence(poses_2d)

        assert result.shape == (50, 17, 3)
        assert result.dtype == np.float32

    def test_extract_sequence_3d_input(self, mock_onnx_extractor):
        """Should slice (N, 17, 3) input to 2D before passing to ONNX."""
        extractor = TCPFormerExtractor()
        poses_3d_input = np.random.rand(30, 17, 3).astype(np.float32)
        result = extractor.extract_sequence(poses_3d_input)

        assert result.shape == (30, 17, 3)

    def test_extract_sequence_single_frame(self, mock_onnx_extractor):
        """Should handle single-frame input."""
        extractor = TCPFormerExtractor()
        poses_2d = np.random.rand(1, 17, 2).astype(np.float32)
        result = extractor.extract_sequence(poses_2d)

        assert result.shape == (1, 17, 3)

    def test_extract_sequence_preserves_xy(self, mock_onnx_extractor):
        """Synthetic mock should preserve x/y from input."""
        extractor = TCPFormerExtractor()
        poses_2d = np.random.rand(20, 17, 2).astype(np.float32)
        result = extractor.extract_sequence(poses_2d)

        np.testing.assert_allclose(result[:, :, 0], poses_2d[:, :, 0], rtol=1e-5)
        np.testing.assert_allclose(result[:, :, 1], poses_2d[:, :, 1], rtol=1e-5)

    def test_temporal_window_constant(self):
        """TEMPORAL_WINDOW should be 81."""
        assert TCPFormerExtractor.TEMPORAL_WINDOW == 81


class TestTCPFormerExtractorReset:
    def test_reset_is_noop(self, mock_onnx_extractor):
        """reset should not raise and should be a no-op."""
        extractor = TCPFormerExtractor()
        extractor.reset()  # Should not raise
        assert extractor._onnx is not None
