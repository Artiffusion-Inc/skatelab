"""Tests for H3.6M conversion functions."""

import numpy as np
import pytest

from src.pose_estimation.h36m import coco_to_h36m, coco_to_h36m_batch
from src.types import H36Key


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


# --- prod-ready-audit repro (M1) ---
# These tests are RED-by-design: they prove the coco_to_h36m midpoint block
# (ml/src/pose_estimation/h36m.py:121-133) has NO NaN guard on hip/shoulder
# midpoints, unlike the HEAD block (lines ~137-165) which guards eye
# confidence and falls back to the nose. NaN in one hip silently poisons
# HIP_CENTER, SPINE, and THORAX. Tests stay RED until the bug is fixed.


def test_m1_coco_to_h36m_nan_in_one_hip_poisons_hip_center():
    """M1: NaN in RIGHT_HIP (conf 0.5) must not make HIP_CENTER NaN.

    Contract (proven by the HEAD block fallback in the same function): when
    one member of a midpoint pair is unreliable, the converter should fall
    back to the confident joint rather than propagate NaN. The hip midpoint
    block lacks this guard, so HIP_CENTER becomes NaN and silently poisons
    CoM/phase/metrics downstream.
    """
    coco = np.full((17, 3), 0.5, dtype=np.float32)
    coco[:, 2] = 0.9  # high confidence everywhere
    # Left hip valid, right hip NaN (but non-zero confidence, simulating a
    # detector glitch where coordinates are NaN yet confidence is reported).
    coco[11] = [0.40, 0.60, 0.9]  # LEFT_HIP valid
    coco[12] = [np.nan, np.nan, 0.5]  # RIGHT_HIP NaN coords, conf 0.5

    h36m = coco_to_h36m(coco)

    # HIP_CENTER is the midpoint of the two hips. With the bug it is NaN.
    # Intended contract: finite (fallback to the confident hip).
    assert np.isfinite(h36m[H36Key.HIP_CENTER.value, 0]), (
        "M1: HIP_CENTER x is NaN because RIGHT_HIP coords are NaN and the "
        "midpoint block has no NaN guard (unlike the HEAD block fallback)."
    )
    assert np.isfinite(h36m[H36Key.HIP_CENTER.value, 1]), (
        "M1: HIP_CENTER y is NaN because RIGHT_HIP coords are NaN and the "
        "midpoint block has no NaN guard (unlike the HEAD block fallback)."
    )


def test_m1_coco_to_h36m_nan_in_one_hip_poisons_spine_and_thorax():
    """M1: NaN in one hip also poisons SPINE (depends on mid_hip) and the
    NaN can flow further. THORAX uses mid_shoulder only, so it stays finite
    here, but SPINE = 0.5*mid_shoulder + 0.5*mid_hip becomes NaN."""
    coco = np.full((17, 3), 0.5, dtype=np.float32)
    coco[:, 2] = 0.9
    coco[11] = [0.40, 0.60, 0.9]  # LEFT_HIP valid
    coco[12] = [np.nan, np.nan, 0.5]  # RIGHT_HIP NaN
    # Shoulders both valid so THORAX is finite; SPINE depends on mid_hip.
    coco[5] = [0.45, 0.45, 0.9]  # LEFT_SHOULDER
    coco[6] = [0.55, 0.45, 0.9]  # RIGHT_SHOULDER

    h36m = coco_to_h36m(coco)

    assert np.isfinite(h36m[H36Key.SPINE.value, 0]), (
        "M1: SPINE x is NaN because it mixes mid_shoulder (finite) with "
        "mid_hip (NaN); the midpoint block has no NaN guard."
    )
    assert np.isfinite(h36m[H36Key.SPINE.value, 1]), (
        "M1: SPINE y is NaN because it mixes mid_shoulder (finite) with "
        "mid_hip (NaN); the midpoint block has no NaN guard."
    )


def test_m1_coco_to_h36m_batch_nan_in_one_hip_poisons_hip_center():
    """M1: same NaN poisoning in the vectorized coco_to_h36m_batch path."""
    poses = np.full((3, 17, 3), 0.5, dtype=np.float32)
    poses[:, :, 2] = 0.9
    # Frame 1: right hip NaN coords.
    poses[1, 11] = [0.40, 0.60, 0.9]  # LEFT_HIP valid
    poses[1, 12] = [np.nan, np.nan, 0.5]  # RIGHT_HIP NaN

    h36m = coco_to_h36m_batch(poses)

    assert np.isfinite(h36m[1, H36Key.HIP_CENTER.value, 0]), (
        "M1 (batch): HIP_CENTER x is NaN on the frame with a NaN right hip; "
        "the vectorized midpoint block has no NaN guard."
    )
    assert np.isfinite(h36m[1, H36Key.HIP_CENTER.value, 1]), (
        "M1 (batch): HIP_CENTER y is NaN on the frame with a NaN right hip; "
        "the vectorized midpoint block has no NaN guard."
    )
