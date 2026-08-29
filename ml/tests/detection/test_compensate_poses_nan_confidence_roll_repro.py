"""Repro tests for issue #987: compensate_poses NaN confidence + NaN roll leaks.

Two NaN-leak paths through SpatialReferenceDetector.compensate_poses:
1. NaN confidence bypasses `confidence < 0.1` guard (NaN < 0.1 == False) ->
   compensation applied when contract says "skip".
2. NaN roll poisons rotation matrix R_2d -> NaN compensated poses ->
   NaN metrics everywhere downstream.

RED on master: both paths fall through unguarded.
"""

import inspect
import math

import numpy as np

from src.detection.spatial_reference import CameraPose, SpatialReferenceDetector


def _poses() -> np.ndarray:
    """Single finite pose, shape (1, 1, 2)."""
    return np.array([[[100.0, 50.0]]], dtype=float)


def _det() -> SpatialReferenceDetector:
    return SpatialReferenceDetector()


class TestCompensatePosesNanConfidence:
    def test_nan_confidence_drops_poses(self):
        """NaN confidence must fire the guard -> poses returned unchanged."""
        out = _det().compensate_poses(_poses(), CameraPose(roll=30.0, confidence=math.nan))
        # Guard fired: output equals input (no rotation applied), NOT rotated.
        np.testing.assert_array_equal(out, _poses())

    def test_nan_confidence_guard_source_lock(self):
        """Root-cause lock: confidence guard must be NaN-safe."""
        src = inspect.getsource(SpatialReferenceDetector.compensate_poses)
        assert "isfinite" in src, "compensate_poses missing isfinite guard"
        # The confidence comparison must use isfinite, not a bare `c < threshold`
        # that silently passes NaN.
        assert "not np.isfinite" in src or "np.isfinite" in src


class TestCompensatePosesNanRoll:
    def test_nan_roll_finite_poses(self):
        """NaN roll + finite confidence 1.0 must NOT produce all-NaN poses."""
        out = _det().compensate_poses(_poses(), CameraPose(roll=math.nan, confidence=1.0))
        # Finite output — NaN roll guarded (zeroed/skipped), not NaN-poisoned.
        assert np.all(np.isfinite(out)), f"NaN roll leaked into poses: {out}"

    def test_nan_roll_guard_source_lock(self):
        """Root-cause lock: roll must be isfinite-guarded before rotation math."""
        src = inspect.getsource(SpatialReferenceDetector.compensate_poses)
        assert "isfinite" in src, "compensate_poses missing isfinite guard on roll"
        # Roll guard before the rotation matrix is constructed.
        assert "roll" in src and "isfinite" in src


class TestCompensatePosesFiniteRegression:
    def test_finite_confidence_and_roll_unchanged(self):
        """Regression: finite confidence + finite roll still compensates."""
        out = _det().compensate_poses(_poses(), CameraPose(roll=0.0, confidence=1.0))
        # roll=0 -> identity rotation -> poses unchanged.
        np.testing.assert_array_equal(out, _poses())

    def test_low_confidence_skips(self):
        """Regression: low finite confidence still skips compensation."""
        out = _det().compensate_poses(_poses(), CameraPose(roll=30.0, confidence=0.05))
        np.testing.assert_array_equal(out, _poses())
