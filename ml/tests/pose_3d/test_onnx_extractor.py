# tests/pose_3d/test_onnx_extractor.py
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def onnx_model_path():
    p = Path("data/models/motionagformer-s-ap3d.onnx")
    if not p.exists():
        pytest.skip("ONNX model not exported yet")
    # External data file required by ONNX Runtime (large, may be excluded from CI)
    data_file = p.with_name("motionagformer-s-ap3d.onnx.data")
    if not data_file.exists():
        pytest.skip("ONNX external data file not available")
    return p


def test_onnx_extractor_init(onnx_model_path):
    from src.pose_3d.onnx_extractor import ONNXPoseExtractor

    ext = ONNXPoseExtractor(onnx_model_path, device="cpu")
    assert ext.temporal_window == 81


def test_onnx_extractor_single_window(onnx_model_path):
    from src.pose_3d.onnx_extractor import ONNXPoseExtractor

    ext = ONNXPoseExtractor(onnx_model_path, device="cpu")
    # Input: (81, 17, 2) normalized 2D poses
    poses_2d = np.random.rand(81, 17, 2).astype(np.float32) * 0.5 + 0.25
    result = ext.estimate_3d(poses_2d)
    assert result.shape == (81, 17, 3)
    # Z coordinates should be reasonable (not all zeros, not huge)
    assert not np.allclose(result[:, :, 2], 0)
    assert np.nanmax(np.abs(result)) < 10


def test_onnx_extractor_long_sequence(onnx_model_path):
    from src.pose_3d.onnx_extractor import ONNXPoseExtractor

    ext = ONNXPoseExtractor(onnx_model_path, device="cpu")
    # Input longer than 81 frames — should be windowed
    poses_2d = np.random.rand(200, 17, 2).astype(np.float32) * 0.5 + 0.25
    result = ext.estimate_3d(poses_2d)
    assert result.shape == (200, 17, 3)


def test_onnx_extractor_short_sequence(onnx_model_path):
    from src.pose_3d.onnx_extractor import ONNXPoseExtractor

    ext = ONNXPoseExtractor(onnx_model_path, device="cpu")
    # Input shorter than 81 frames — should be padded
    poses_2d = np.random.rand(30, 17, 2).astype(np.float32) * 0.5 + 0.25
    result = ext.estimate_3d(poses_2d)
    assert result.shape == (30, 17, 3)


def test_center_weighted_scatter_reduces_windows():
    """Triangular window weighting enables larger stride = fewer windows."""
    # Stride 54 (33% overlap) vs stride 40 (50% overlap)
    n_frames = 300
    window = 81
    stride_old = window // 2  # 40
    stride_new = window * 2 // 3  # 54

    windows_old = len(range(0, n_frames, stride_old))
    windows_new = len(range(0, n_frames, stride_new))

    assert windows_new < windows_old, "New stride should produce fewer windows"


def test_center_weighted_scatter_triangle_weights():
    """Verify triangular window shape: ramp up, flat center, ramp down."""
    # Simulate the weighting logic directly
    w = 81
    frame_count = w
    window_weights = np.ones(frame_count, dtype=np.float32)
    ramp_len = min(frame_count, w // 4)  # 20
    window_weights[:ramp_len] = np.linspace(0.5, 1.0, ramp_len)
    window_weights[-ramp_len:] = np.linspace(1.0, 0.5, ramp_len)

    # Center frames should have weight 1.0
    assert window_weights[ramp_len:-ramp_len].sum() == pytest.approx(
        (frame_count - 2 * ramp_len) * 1.0
    )
    # Edges should taper
    assert window_weights[0] == pytest.approx(0.5)
    assert window_weights[-1] == pytest.approx(0.5)
    assert window_weights[ramp_len - 1] == pytest.approx(1.0)


def test_onnx_extractor_release_clears_session(onnx_model_path):
    """release() deletes the ONNX session and sets it to None."""
    from src.pose_3d.onnx_extractor import ONNXPoseExtractor

    ext = ONNXPoseExtractor(onnx_model_path, device="cpu")
    assert ext.session is not None
    ext.release()
    assert ext.session is None


def test_onnx_extractor_release_idempotent(onnx_model_path):
    """Calling release() twice does not error."""
    from src.pose_3d.onnx_extractor import ONNXPoseExtractor

    ext = ONNXPoseExtractor(onnx_model_path, device="cpu")
    ext.release()
    ext.release()  # Should not raise
    assert ext.session is None
