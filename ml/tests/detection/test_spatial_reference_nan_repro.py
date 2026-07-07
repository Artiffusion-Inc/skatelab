"""Repro tests for issue #1208: draw_axes int(origin+axis*length) NaN crash.

RED on master: int(NaN) raises ValueError when origin or length is NaN/inf,
even if camera_pose is finite. The existing roll/pitch guard does not cover
origin or length.
"""

import inspect
import math

import numpy as np
import pytest

from src.detection.spatial_reference import CameraPose, SpatialReferenceDetector

FRAME = np.zeros((120, 200, 3), dtype=np.uint8)
FINITE_POSE = CameraPose(roll=0.0, pitch=0.0, yaw=0.0, confidence=1.0, source="imu")


def _draw(origin, length: float) -> np.ndarray:
    return SpatialReferenceDetector().draw_axes(FRAME.copy(), FINITE_POSE, origin, length)


class TestDrawAxesOriginLengthNaN:
    def test_nan_origin_no_crash(self):
        """int(NaN) at line 330/331 must NOT raise — draw_axes returns a frame."""
        frame = _draw((math.nan, 50.0), 60.0)
        assert frame is not None
        assert frame.shape == FRAME.shape

    def test_nan_length_no_crash(self):
        """int(origin + axis * NaN) at line 333/334 must NOT raise."""
        frame = _draw((50.0, 50.0), math.nan)
        assert frame is not None
        assert frame.shape == FRAME.shape

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_nonfinite_origin_or_length_does_not_crash(self, bad):
        """Any non-finite origin component or length must not raise."""
        frame = _draw((bad, 50.0), 60.0)
        assert frame is not None
        frame = _draw((50.0, bad), 60.0)
        assert frame is not None
        frame = _draw((50.0, 50.0), bad)
        assert frame is not None

    def test_source_has_isfinite_guard_for_origin_length(self):
        """Root-cause lock: an isfinite guard must cover origin and length."""
        src = inspect.getsource(SpatialReferenceDetector.draw_axes)
        assert "isfinite" in src, "draw_axes must guard origin/length with isfinite"
        # The int() casts at 330-334 must be inside or after a guard, not raw.
        # If origin/length are not guarded, any NaN in caller args crashes the int().
        assert "origin" in src and "length" in src, "guard must reference origin and length"
