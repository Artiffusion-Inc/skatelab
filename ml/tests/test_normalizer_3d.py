"""Tests for PoseNormalizer.normalize_3d()."""

import numpy as np
import pytest

from src.pose_estimation.normalizer import PoseNormalizer
from src.types import H36Key


@pytest.fixture
def simple_3d_poses():
    """Create simple (5, 17, 3) poses with known geometry."""
    rng = np.random.default_rng(42)
    poses = rng.random((5, 17, 3)).astype(np.float32)
    poses[:, H36Key.HIP_CENTER] = [0.5, 0.5, 0.3]
    poses[:, H36Key.THORAX] = [0.5, 0.8, 0.3]
    return poses


def test_normalize_3d_output_shape(simple_3d_poses):
    normalizer = PoseNormalizer(target_spine_length=0.4)
    result = normalizer.normalize_3d(simple_3d_poses)
    assert result.shape == (5, 17, 3)


def test_normalize_3d_preserves_z(simple_3d_poses):
    normalizer = PoseNormalizer(target_spine_length=0.4)
    result_3d = normalizer.normalize_3d(simple_3d_poses)
    assert result_3d.shape[2] == 3
    result_2d = normalizer.normalize(simple_3d_poses)
    assert result_2d.shape[2] == 2


def test_normalize_3d_root_centered(simple_3d_poses):
    normalizer = PoseNormalizer(target_spine_length=0.4)
    result = normalizer.normalize_3d(simple_3d_poses)
    hip_center = result[:, H36Key.HIP_CENTER]
    np.testing.assert_allclose(hip_center, 0.0, atol=1e-6)


def test_normalize_3d_spine_length(simple_3d_poses):
    target = 0.4
    normalizer = PoseNormalizer(target_spine_length=target)
    result = normalizer.normalize_3d(simple_3d_poses)
    spine = result[:, H36Key.THORAX]
    spine_lengths = np.linalg.norm(spine, axis=1)
    np.testing.assert_allclose(spine_lengths, target, rtol=1e-5)


def test_normalize_3d_xy_matches_2d(simple_3d_poses):
    normalizer = PoseNormalizer(target_spine_length=0.4)
    result_2d = normalizer.normalize(simple_3d_poses)
    result_3d = normalizer.normalize_3d(simple_3d_poses)
    np.testing.assert_allclose(result_3d[:, :, :2], result_2d, atol=1e-6)


def test_normalize_3d_invalid_shape():
    normalizer = PoseNormalizer()
    with pytest.raises(ValueError, match="Expected poses shape"):
        normalizer.normalize_3d(np.zeros((5, 17, 2), dtype=np.float32))


def test_normalize_3d_single_frame():
    normalizer = PoseNormalizer(target_spine_length=0.4)
    poses = np.zeros((1, 17, 3), dtype=np.float32)
    poses[0, H36Key.HIP_CENTER] = [1.0, 2.0, 0.5]
    poses[0, H36Key.THORAX] = [1.0, 2.4, 0.5]
    result = normalizer.normalize_3d(poses)
    assert result.shape == (1, 17, 3)
    np.testing.assert_allclose(result[0, H36Key.HIP_CENTER], 0.0, atol=1e-6)
