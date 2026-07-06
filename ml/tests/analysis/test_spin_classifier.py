"""Tests for spin type detection and classification."""

import numpy as np
import pytest

from ml.src.analysis.spin_classifier import classify_spin, detect_spin


def test_classify_upright_spin():
    name, conf = classify_spin(
        duration_s=2.0,
        hip_y_range=0.05,
        angular_velocity_mean=400.0,
    )
    assert name == "upright_spin"
    assert conf > 0.5


def test_classify_scratch_spin():
    name, conf = classify_spin(
        duration_s=2.0,
        hip_y_range=0.15,
        angular_velocity_mean=350.0,
    )
    assert name in ("scratch_spin", "one_foot_spin")
    assert conf > 0.4


def test_detect_spin_true():
    vel = np.zeros(100)
    vel[20:60] = 350.0  # Spinning region
    hip_y = np.ones(100) * 0.5
    is_spin, duration, _hip_range, _mask = detect_spin(vel, hip_y, fps=30.0)
    assert is_spin
    assert duration > 1.0


def test_detect_spin_false():
    vel = np.ones(100) * 50.0  # Below threshold
    hip_y = np.ones(100) * 0.5
    is_spin, _, _, _mask = detect_spin(vel, hip_y, fps=30.0)
    assert not is_spin


def test_detect_spin_too_short():
    vel = np.zeros(100)
    vel[45:55] = 350.0  # Only 10 frames ~0.33s at 30fps
    hip_y = np.ones(100) * 0.5
    is_spin, duration, _, _mask = detect_spin(vel, hip_y, fps=30.0)
    assert not is_spin
    assert duration < 1.0


def test_classify_short_duration():
    _name, conf = classify_spin(
        duration_s=0.5,  # Below min for all spins
        hip_y_range=0.05,
        angular_velocity_mean=400.0,
    )
    # Should still classify but with lower confidence (duration penalized)
    assert conf < 0.8


def test_detect_spin_with_hip_variation():
    vel = np.zeros(100)
    vel[10:70] = 250.0
    hip_y = np.linspace(0.4, 0.6, 100)  # Varying hip position
    is_spin, _duration, hip_range, _mask = detect_spin(vel, hip_y, fps=30.0)
    assert is_spin
    assert hip_range > 0.0
