"""RED repro — phase_detector.py parabolic airtime NaN/neg fps silent 0.0 (#1061).

Bug: `_detect_jump_phases_parabolic` (ml/src/analysis/phase_detector.py:489)
has a NaN-blind `fps > 0` guard that silently coerces NaN fps to 0.0,
INDISTINGUISHABLE from a legitimate `fps=0` (a broken-header video).

    airtime = (landing_idx - takeoff_idx + 1) / fps if fps > 0 else 0.0
    # ^ NaN fps -> NaN > 0 is False -> airtime = 0.0 (silent NaN -> 0)

The same pattern repeats at line 247 in `_detect_jump_phases_com_improved`
(sibling to fix-1088 — NaN confidence fix). This file focuses on the
PARABOLIC path (line 489) as a distinct function with the same root cause,
per the issue's "sibling bug at line 459" pointer.

ROOT-CAUSE FAMILY: same as #1043/#1044/#1066 — `if fps > 0 else 0.0`
NaN-bypass, where NaN fps (common from cv2.CAP_PROP_FPS on webm/mkv) is
silently swallowed instead of raising ValueError.

FIX: at function entry, `math.isfinite(fps) and fps > 0` guard, mirror the
#1043/#1044/#1066 pattern.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import median_filter

from src.analysis.phase_detector import PhaseDetector
from src.types import H36Key
from src.utils.geometry import calculate_com_trajectory

# CoM mass weights in calculate_com_trajectory sum to 1.3 (not 1.0), so
# setting every keypoint's Y to `target / 1.3` yields CoM == target.
_COM_MASS_SUM = 0.081 + 0.497 + 0.050 * 4 + 0.100 * 2 + 0.161 * 2  # = 1.3


def _poses_from_com(target_com: np.ndarray, baseline_y: float = 0.5) -> np.ndarray:
    """Build (N, 17, 2) poses whose calculate_com_trajectory == target_com."""
    n = len(target_com)
    poses = np.full((n, 17, 2), baseline_y, dtype=np.float32)
    poses[:, :, 0] = 0.5
    poses[:, :, 1] = (target_com / _COM_MASS_SUM).astype(np.float32)[:, None]
    return poses


def _nine_frame_flight_com(
    n_frames: int = 60,
    baseline_y: float = 0.5,
    peak_y: float = 0.2,
    center: int = 24,
    takeoff: int = 20,
    landing: int = 28,
) -> np.ndarray:
    """CoM trajectory with a parabolic dip whose baseline crossings are at
    `takeoff` and `landing` (inclusive, 9 frames at default).

    The parabola extends 2 frames beyond each crossing (to frames 18-30) so
    that the parabolic detector's extended fit window [elevated-3, elevated+3]
    stays within the parabola and achieves R^2=1.0.
    """
    com_y = np.full(n_frames, baseline_y, dtype=np.float64)
    half_span = (landing - takeoff) / 2.0
    a = (baseline_y - peak_y) / (half_span**2)
    ext_lo = takeoff - 2
    ext_hi = landing + 2
    for f in range(ext_lo, ext_hi + 1):
        t = f - center
        com_y[f] = a * (t**2) + peak_y
    return com_y


class TestParabolicPhaseDetectorFpsNaNNegative:
    """Parabolic path: NaN/neg fps must be rejected, not silently swallowed."""

    def test_nan_fps_raises_value_error(self):
        """NaN fps must raise ValueError at function entry, not silently
        coerce to 0.0 airtime.

        Pre-fix: `if fps > 0 else 0.0` — `NaN > 0` is False, so airtime=0.0
        and the gate `airtime < 0.3` rejects the segment, and the detector
        silently returns a fallback with confidence=0.0 (indistinguishable
        from a legitimate broken-header fps=0). The user sees "no phase
        detected" instead of a clear "bad input" error.

        Post-fix: math.isfinite(fps) AND fps > 0 guard at function entry
        raises ValueError("fps must be finite and > 0, got nan").
        """
        fps = float("nan")
        com_y = _nine_frame_flight_com()
        poses = _poses_from_com(com_y, baseline_y=0.5)

        detector = PhaseDetector()
        with pytest.raises(ValueError, match=r"fps must be finite and > 0"):
            detector._detect_jump_phases_parabolic(poses, fps=fps)

    def test_negative_fps_raises_value_error(self):
        """Negative fps must raise ValueError (same root cause as NaN)."""
        fps = -30.0
        com_y = _nine_frame_flight_com()
        poses = _poses_from_com(com_y, baseline_y=0.5)

        detector = PhaseDetector()
        with pytest.raises(ValueError, match=r"fps must be finite and > 0"):
            detector._detect_jump_phases_parabolic(poses, fps=fps)

    def test_zero_fps_raises_value_error(self):
        """fps=0.0 (broken-header video) must also raise, not silently 0.0."""
        fps = 0.0
        com_y = _nine_frame_flight_com()
        poses = _poses_from_com(com_y, baseline_y=0.5)

        detector = PhaseDetector()
        with pytest.raises(ValueError, match=r"fps must be finite and > 0"):
            detector._detect_jump_phases_parabolic(poses, fps=fps)

    def test_inf_fps_raises_value_error(self):
        """inf fps must raise (math.isfinite catches inf, isnan does not)."""
        fps = float("inf")
        com_y = _nine_frame_flight_com()
        poses = _poses_from_com(com_y, baseline_y=0.5)

        detector = PhaseDetector()
        with pytest.raises(ValueError, match=r"fps must be finite and > 0"):
            detector._detect_jump_phases_parabolic(poses, fps=fps)

    def test_valid_fps_still_detects_jump(self):
        """Regression guard: valid fps=30.0 must still detect the 9-frame
        flight (takeoff=20, landing=28, R^2=1.0) — i.e. the fix does not
        break the working path.
        """
        fps = 30.0
        com_y = _nine_frame_flight_com()
        poses = _poses_from_com(com_y, baseline_y=0.5)

        detector = PhaseDetector()
        result = detector._detect_jump_phases_parabolic(poses, fps=fps)

        assert hasattr(result, "phases"), (
            f"Parabolic detector must return a result with .phases, got {type(result).__name__}"
        )
        assert result.phases.takeoff == 20, (
            f"Expected parabolic takeoff=20, got {result.phases.takeoff}"
        )
        assert result.phases.landing == 28, (
            f"Expected parabolic landing=28, got {result.phases.landing}"
        )

    def test_source_has_isfinite_fps_guard(self):
        """Source check: `_detect_jump_phases_parabolic` must contain a
        `math.isfinite(fps)` (or equivalent isfinite) guard, NOT just
        `if fps > 0`.

        Pre-fix: `if fps > 0 else 0.0` allows NaN to bypass.
        Post-fix: `if not (math.isfinite(fps) and fps > 0): raise`.
        """
        import inspect

        from src.analysis.phase_detector import PhaseDetector

        source = inspect.getsource(PhaseDetector._detect_jump_phases_parabolic)

        # Must contain isfinite check on fps
        assert "isfinite(fps)" in source, (
            "_detect_jump_phases_parabolic must contain `math.isfinite(fps)` "
            "guard. Pre-fix: NaN fps silently coerces to 0.0 airtime, "
            "indistinguishable from legitimate fps=0. Mirror the #1043/"
            "#1044/#1066 isfinite guard pattern."
        )
        # Must raise (not silently coerce)
        assert "raise" in source, (
            "_detect_jump_phases_parabolic must `raise ValueError` on bad fps, "
            "not silently return 0.0 airtime. The issue is #1061 — the silent "
            "NaN->0 coercion hides bad input from the user."
        )
        # The NaN-bypass `if fps > 0 else 0.0` pattern is allowed as a
        # defensive 2nd-line clamp (now unreachable after the entry guard),
        # but it must NOT be the ONLY protection — the source must contain
        # the explicit isfinite + raise at function entry.
        assert "raise ValueError" in source and "isfinite(fps)" in source, (
            "_detect_jump_phases_parabolic must contain BOTH "
            "`math.isfinite(fps)` and `raise ValueError` at function entry. "
            "Pre-fix: NaN fps silently coerces to 0.0 airtime, "
            "indistinguishable from legitimate fps=0. Mirror the #1043/"
            "#1044/#1063/#1066 isfinite+raise pattern."
        )
