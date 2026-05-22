"""Tests for total rotation counting and under-rotation detection."""

import numpy as np
import pytest


def test_total_rotation_single():
    """One full rotation = 360 degrees."""
    from src.analysis.metrics import compute_total_rotation

    angles = np.linspace(0, 2 * np.pi, 100)  # 0 to 360 deg, unwrapped
    total_deg, rot_count = compute_total_rotation(angles, fps=30.0)
    assert abs(total_deg - 360.0) < 5.0
    assert abs(rot_count - 1.0) < 0.02


def test_total_rotation_triple():
    """Triple jump = 3 rotations = 1080 degrees."""
    from src.analysis.metrics import compute_total_rotation

    angles = np.linspace(0, 6 * np.pi, 300)  # 0 to 1080 deg
    total_deg, rot_count = compute_total_rotation(angles, fps=30.0)
    assert abs(total_deg - 1080.0) < 10.0
    assert abs(rot_count - 3.0) < 0.05


def test_total_rotation_empty():
    """Empty or single-element array = 0 rotation."""
    from src.analysis.metrics import compute_total_rotation

    angles = np.array([], dtype=np.float32)
    total_deg, rot_count = compute_total_rotation(angles, fps=30.0)
    assert total_deg == 0.0
    assert rot_count == 0.0

    angles = np.array([1.0], dtype=np.float32)
    total_deg, rot_count = compute_total_rotation(angles, fps=30.0)
    assert total_deg == 0.0
    assert rot_count == 0.0


def test_under_rotation_quarter_short():
    """Jump 1/4 rotation short of triple."""
    from src.analysis.metrics import compute_under_rotation

    under = compute_under_rotation(measured_degrees=990.0, target_rotations=3)
    assert abs(under - 90.0) < 1.0  # quarter revolution


def test_under_rotation_clean():
    """Clean triple, no under-rotation."""
    from src.analysis.metrics import compute_under_rotation

    under = compute_under_rotation(measured_degrees=1080.0, target_rotations=3)
    assert abs(under) < 1.0


def test_under_rotation_over_rotated():
    """Over-rotated jump returns negative under-rotation."""
    from src.analysis.metrics import compute_under_rotation

    under = compute_under_rotation(measured_degrees=1170.0, target_rotations=3)
    assert under < 0  # negative = over-rotated
    assert abs(under - (-90.0)) < 1.0
