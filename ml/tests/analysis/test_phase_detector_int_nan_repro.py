"""Issue #1112 — `_detect_jump_phases_parabolic` int(NaN) crash on NaN fps.

Background
----------
The issue (filed before #1061 was fixed) reported a crash at
`min_dur = max(5, int(0.2 * fps))` in
`ml/src/analysis/phase_detector.py:_detect_jump_phases_parabolic` when fps
is NaN. `0.2 * NaN = NaN` and `int(NaN)` raises
`ValueError: cannot convert float NaN to integer`.

#1061 (PR #1129) already added a `math.isfinite(fps) and fps > 0` guard at
the function entry. This file is the regression test requested by #1112 —
it pins the contract that NaN fps must raise a typed ValueError, not a
raw `int(NaN)` ValueError.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.analysis.phase_detector import PhaseDetector

# CoM mass weights in calculate_com_trajectory sum to 1.3, so every
# keypoint Y = target / 1.3 yields CoM == target.
_COM_MASS_SUM = 0.081 + 0.497 + 0.050 * 4 + 0.100 * 2 + 0.161 * 2  # = 1.3


def _poses_from_com(target_com: np.ndarray, baseline_y: float = 0.5) -> np.ndarray:
    """Build (N, 17, 2) poses whose calculate_com_trajectory == target_com."""
    n = len(target_com)
    poses = np.full((n, 17, 2), baseline_y, dtype=np.float32)
    poses[:, :, 0] = 0.5
    poses[:, :, 1] = (target_com / _COM_MASS_SUM).astype(np.float32)[:, None]
    return poses


def _n_frames_with_parabolic_dip(
    n_frames: int = 60,
    baseline_y: float = 0.5,
    peak_y: float = 0.2,
    center: int = 24,
    takeoff: int = 20,
    landing: int = 28,
) -> np.ndarray:
    """Build a CoM trajectory with a 9-frame parabolic dip (#1061 fixture)."""
    com_y = np.full(n_frames, baseline_y, dtype=np.float64)
    half_span = (landing - takeoff) / 2.0
    a = (baseline_y - peak_y) / (half_span**2)
    ext_lo = takeoff - 2
    ext_hi = landing + 2
    for f in range(ext_lo, ext_hi + 1):
        t = f - center
        com_y[f] = a * (t**2) + peak_y
    return com_y


@pytest.fixture
def parabolic_poses() -> np.ndarray:
    """60-frame pose sequence with a clear parabolic flight segment."""
    com = _n_frames_with_parabolic_dip()
    return _poses_from_com(com)


class TestParabolicIntNaNCrash:
    """Issue #1112: int(NaN) crash on NaN fps must be guarded."""

    def test_nan_fps_does_not_crash_with_int_value_error(self, parabolic_poses: np.ndarray) -> None:
        """NaN fps must raise a typed error (or be handled) — never a raw
        `ValueError: cannot convert float NaN to integer` from int(NaN).

        The contract: when fps is non-finite, the function should raise
        ValueError (typed) per the #1061/#1129 guard. The bug is when
        int(NaN) is reached inside min_dur computation.
        """
        det = PhaseDetector()
        with pytest.raises((ValueError, TypeError)) as exc_info:
            det._detect_jump_phases_parabolic(parabolic_poses, math.nan)
        # The crash from the bug would be exactly: "cannot convert float NaN
        # to integer". The guard should produce a different message.
        assert "cannot convert float NaN to integer" not in str(exc_info.value), (
            "int(NaN) crash regressed: the fps guard at function entry is missing or ineffective."
        )

    def test_positive_fps_still_works(self, parabolic_poses: np.ndarray) -> None:
        """Sanity: a normal fps=30.0 must still detect the jump phases
        (and must not raise)."""
        det = PhaseDetector()
        result = det._detect_jump_phases_parabolic(parabolic_poses, 30.0)
        assert result is not None
        # The PhaseDetectionResult has .phases (ElementPhase) and .confidence.
        assert 0.0 <= result.confidence <= 1.0

    def test_infinity_fps_rejected(self, parabolic_poses: np.ndarray) -> None:
        """inf fps must also be rejected by the isfinite guard."""
        det = PhaseDetector()
        with pytest.raises(ValueError):
            det._detect_jump_phases_parabolic(parabolic_poses, math.inf)

    def test_negative_fps_rejected(self, parabolic_poses: np.ndarray) -> None:
        """Negative fps must also be rejected by the > 0 half of the guard."""
        det = PhaseDetector()
        with pytest.raises(ValueError):
            det._detect_jump_phases_parabolic(parabolic_poses, -1.0)

    def test_zero_fps_rejected(self, parabolic_poses: np.ndarray) -> None:
        """Zero fps must also be rejected by the > 0 half of the guard."""
        det = PhaseDetector()
        with pytest.raises(ValueError):
            det._detect_jump_phases_parabolic(parabolic_poses, 0.0)
