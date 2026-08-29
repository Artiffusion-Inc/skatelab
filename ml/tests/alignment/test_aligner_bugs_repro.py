"""RED repro: aligner.compute_distance crashes on empty/single-frame input.

Bug (HIGH): ml/src/alignment/aligner.py:94, 102, 136 — compute_distance
and compute_distance_3d crash on degenerate input:
- Line 94: `user[:, joints, :].reshape(len(user), -1)` raises
  `ValueError: cannot reshape array of size 0 into shape (0, newaxis)`
- Line 102: `alignment.distance / max(len(user), len(reference))` raises
  `ZeroDivisionError` when both inputs are empty

The sibling `motion_dtw.py:470` (and `motion_dtw.py:515` for 3D)
already has the #478 fix: early-return `inf` when `len(user) < 2 or
len(reference) < 2`. `aligner.py` was not patched with the same fix.

This test verifies the contract: compute_distance on degenerate input
(empty / single-frame) returns `inf` instead of crashing.
"""

import math

import numpy as np
import pytest

from src.alignment.aligner import MotionAligner


def test_compute_distance_empty_inputs_returns_inf():
    """Both empty → no crash, returns inf."""
    aligner = MotionAligner()
    user = np.zeros((0, 17, 2), dtype=np.float32)
    reference = np.zeros((0, 17, 2), dtype=np.float32)
    result = aligner.compute_distance(user, reference)
    assert result == float("inf"), f"Empty inputs should return inf, got {result}"


def test_compute_distance_single_frame_input_returns_inf():
    """Single frame → no crash, returns inf (can't compute DTW on <2 frames)."""
    aligner = MotionAligner()
    user = np.random.rand(1, 17, 2).astype(np.float32)
    reference = np.random.rand(1, 17, 2).astype(np.float32)
    result = aligner.compute_distance(user, reference)
    assert result == float("inf"), f"Single frame should return inf, got {result}"


def test_compute_distance_3d_empty_returns_inf():
    """3D variant: empty → no crash, returns inf."""
    aligner = MotionAligner()
    user = np.zeros((0, 17, 3), dtype=np.float32)
    reference = np.zeros((0, 17, 3), dtype=np.float32)
    result = aligner.compute_distance_3d(user, reference)
    assert result == float("inf"), f"3D empty inputs should return inf, got {result}"


def test_compute_distance_valid_input_works():
    """Regression guard: normal input still computes a real distance."""
    aligner = MotionAligner()
    rng = np.random.default_rng(42)
    user = rng.random((10, 17, 2)).astype(np.float32)
    reference = rng.random((10, 17, 2)).astype(np.float32)
    result = aligner.compute_distance(user, reference)
    assert math.isfinite(result), f"Valid input should give finite distance, got {result}"
    assert result >= 0
