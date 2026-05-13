"""Tests for H3.6M conversion functions."""

import numpy as np
import pytest

from src.pose_estimation.h36m import coco_to_h36m, coco_to_h36m_batch


def test_coco_to_h36m_batch():
    """Vectorized conversion matches per-frame results."""
    poses_coco = np.random.randn(50, 17, 2).astype(np.float32)
    result_loop = np.stack([coco_to_h36m(p) for p in poses_coco])
    result_batch = coco_to_h36m_batch(poses_coco)
    np.testing.assert_allclose(result_loop, result_batch, atol=1e-6)


def test_coco_to_h36m_batch_3d():
    """Batch conversion works with 3D (x, y, conf) input."""
    poses_coco = np.random.randn(30, 17, 3).astype(np.float32)
    # Ensure confidence values are in valid range
    poses_coco[:, :, 2] = np.abs(poses_coco[:, :, 2])
    result_loop = np.stack([coco_to_h36m(p) for p in poses_coco])
    result_batch = coco_to_h36m_batch(poses_coco)
    np.testing.assert_allclose(result_loop, result_batch, atol=1e-6)


def test_coco_to_h36m_batch_single_frame():
    """Batch works with N=1 (single frame)."""
    poses_coco = np.random.randn(1, 17, 2).astype(np.float32)
    result_loop = np.stack([coco_to_h36m(p) for p in poses_coco])
    result_batch = coco_to_h36m_batch(poses_coco)
    np.testing.assert_allclose(result_loop, result_batch, atol=1e-6)


def test_coco_to_h36m_batch_head_fallback():
    """Batch handles HEAD fallback (low confidence eyes) correctly."""
    poses_coco = np.random.randn(5, 17, 3).astype(np.float32)
    # Set eye confidence low to trigger fallback
    poses_coco[:, 1, 2] = 0.1  # LEFT_EYE low conf
    poses_coco[:, 2, 2] = 0.1  # RIGHT_EYE low conf
    # Set other confidences high
    poses_coco[:, 0, 2] = 0.9  # NOSE
    poses_coco[:, 5, 2] = 0.9  # LEFT_SHOULDER
    poses_coco[:, 6, 2] = 0.9  # RIGHT_SHOULDER
    result_loop = np.stack([coco_to_h36m(p) for p in poses_coco])
    result_batch = coco_to_h36m_batch(poses_coco)
    np.testing.assert_allclose(result_loop, result_batch, atol=1e-6)
