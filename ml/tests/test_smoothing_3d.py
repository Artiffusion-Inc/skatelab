"""Tests for 3D smoothing in PoseSmoother."""

import numpy as np
import pytest

from src.utils.smoothing import PoseSmoother, get_skating_optimized_config


@pytest.fixture
def poses_3d():
    """Create (50, 17, 3) 3D poses with slight noise."""
    rng = np.random.default_rng(42)
    base = np.zeros((50, 17, 3), dtype=np.float32)
    t = np.linspace(0, 2 * np.pi, 50, dtype=np.float32)
    for j in range(17):
        base[:, j, 0] = np.sin(t) + rng.normal(0, 0.01, 50).astype(np.float32)
        base[:, j, 1] = np.cos(t) + rng.normal(0, 0.01, 50).astype(np.float32)
        base[:, j, 2] = np.sin(t * 0.5) + rng.normal(0, 0.01, 50).astype(np.float32)
    return base


def test_smooth_3d_output_shape(poses_3d):
    smoother = PoseSmoother(config=get_skating_optimized_config(30.0), freq=30.0)
    result = smoother.smooth_3d(poses_3d)
    assert result.shape == (50, 17, 3)


def test_smooth_3d_reduces_noise(poses_3d):
    smoother = PoseSmoother(config=get_skating_optimized_config(30.0), freq=30.0)
    result = smoother.smooth_3d(poses_3d)
    input_var = np.var(poses_3d[:, 0, 2])
    output_var = np.var(result[:, 0, 2])
    assert output_var < input_var


def test_smooth_3d_invalid_shape():
    smoother = PoseSmoother(freq=30.0)
    with pytest.raises(ValueError, match=r"Expected shape.*N, 17, 3"):
        smoother.smooth_3d(np.zeros((10, 17, 2), dtype=np.float32))


def test_smooth_phase_aware_3d_output_shape(poses_3d):
    smoother = PoseSmoother(config=get_skating_optimized_config(30.0), freq=30.0)
    boundaries = [15, 35]
    result = smoother.smooth_phase_aware_3d(poses_3d, boundaries)
    assert result.shape == (50, 17, 3)


def test_smooth_phase_aware_3d_no_boundaries(poses_3d):
    smoother = PoseSmoother(config=get_skating_optimized_config(30.0), freq=30.0)
    result = smoother.smooth_phase_aware_3d(poses_3d, [])
    assert result.shape == (50, 17, 3)


def test_smooth_detects_3d_input(poses_3d):
    smoother = PoseSmoother(config=get_skating_optimized_config(30.0), freq=30.0)
    result = smoother.smooth(poses_3d)
    assert result.shape == (50, 17, 3), "smooth() should handle 3D input"
