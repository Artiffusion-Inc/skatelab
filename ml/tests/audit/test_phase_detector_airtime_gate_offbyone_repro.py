"""RED repro — phase_detector airtime validation gate off-by-one (inclusive-end span).

ml/src/analysis/phase_detector.py:205 and :426
    airtime = (landing_idx - takeoff_idx) / fps

This is a SPAN (landing_idx - takeoff_idx = exclusive-end distance), but
takeoff_idx/landing_idx are INCLUSIVE concrete frame indices (proven below).
The correct COUNT is (landing_idx - takeoff_idx + 1) / fps. At fps=30, a jump
with exactly 9 inclusive flight frames (takeoff=20, landing=28):

    span  airtime = 8 / 30 = 0.2667 s < 0.3  -> gate REJECTS valid jump  (BUG)
    count airtime = 9 / 30 = 0.3000 s >= 0.3 -> gate ACCEPTS             (CORRECT)

The 0.300 s true airtime sits exactly on the minimum-airtime threshold
(`if airtime < 0.3` at :208/:427). The span off-by-one shaves one frame,
pushing it under the gate, so a VALID short jump (single-rotation
waltz_jump/toe_loop ~0.3-0.4 s airtime) is deterministically rejected.

INCLUSIVE CONVENTION PROOF:
  - phase_detector.py:480 _scan_to_baseline docstring: "Returns: Frame index
    where CoM returns to baseline" — a CONCRETE frame index, inclusive.
  - phase_detector.py:449/:451 these same takeoff_idx/landing_idx become
    ElementPhase.takeoff/landing (types.py:464 "Landing frame" = inclusive).
  - physics_engine.py:631 `com[takeoff_idx : landing_idx + 1, 1]` — the +1 in
    the Python slice confirms landing_idx is the inclusive last frame.
  - #518 (ElementPhase.airtime_sec sibling) proven inclusive by the same
    convention chain.

SAME LINE, DIFFERENT BUG:
  - #499/#505 (fps=0 divide-by-zero on :205/:426) — off-by-one != divide-by-
    zero, exactly like #515 (detect_spin span off-by-one) was separate from
    the fps=0 bug on the same spin_classifier.py:90 line.

REPRO (parabolic path, 9-frame flight at 30 fps):
  Construct poses where CoM follows a parabola over frames 18-30, crossing
  baseline at exactly frame 20 (takeoff) and frame 28 (landing) — 9 inclusive
  flight frames. The parabolic detector finds this segment: R^2=1.0 (perfect
  parabola fit), peak inside segment, a>0. _scan_to_baseline returns
  takeoff=20, landing=28. But the span airtime = 8/30 = 0.267 < 0.3 -> the
  gate `continue`s past this segment, discarding the only valid parabola.
  The detector falls back to the velocity-based com_improved path which
  returns a WIDER, less-accurate window (takeoff=19, landing=34).

  RED: the parabolic path should detect takeoff=20, landing=28 (the true
  9-frame flight, R^2=1.0) with confidence > 0. With the bug, the gate
  rejects it and the result has landing=34 (fallback window), not 28.

Round-3 scout ERRORED lowering to low-confidence ("ambiguous event-time") —
_scan_to_baseline docstring + :449/:451 routing to ElementPhase PROVE
inclusive frame index.
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
    """Build (N, 17, 2) poses whose calculate_com_trajectory == target_com.

    All 17 keypoints share the same Y per frame, so CoM == (mass_sum * Y).
    Dividing by the mass sum makes CoM == target_com exactly.
    """
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
    stays within the parabola and achieves R^2=1.0. Outside [18, 30] the CoM
    is flat at baseline_y, so the median-filter baseline == baseline_y and
    _scan_to_baseline returns exactly `takeoff` and `landing`.
    """
    com_y = np.full(n_frames, baseline_y, dtype=np.float64)
    # Parabola: com = a*(f - center)^2 + peak_y, com = baseline_y at f=takeoff/landing.
    half_span = (landing - takeoff) / 2.0  # distance from center to crossing
    a = (baseline_y - peak_y) / (half_span**2)
    # Extend the parabola 2 frames past each crossing for the fit window.
    ext_lo = takeoff - 2
    ext_hi = landing + 2
    for f in range(ext_lo, ext_hi + 1):
        t = f - center
        com_y[f] = a * (t**2) + peak_y
    return com_y


class TestPhaseDetectorAirtimeGateOffByOne:
    """The 0.3 s minimum-airtime gate uses span, not inclusive count."""

    def test_nine_frame_flight_passes_airtime_gate(self):
        """A 9-frame inclusive flight at 30 fps (0.300 s) must pass the
        minimum-airtime gate (airtime < 0.3 is False for 0.300).

        The parabolic detector finds a perfect parabola (R^2=1.0) over this
        flight with takeoff=20, landing=28. With the span bug:
            airtime = (28 - 20) / 30 = 0.267 < 0.3 -> gate rejects (`continue`)
        so the valid parabola is discarded and the detector falls back to a
        wider, less-accurate velocity-based window. With the inclusive fix:
            airtime = (28 - 20 + 1) / 30 = 0.300 -> 0.300 < 0.3 is False ->
            gate accepts, parabolic result returned with takeoff=20, landing=28.

        RED now: the result's landing != 28 (the gate rejected the valid
        parabola and the fallback returned a wider window).
        """
        fps = 30.0
        com_y = _nine_frame_flight_com(
            n_frames=60, baseline_y=0.5, peak_y=0.2, center=24, takeoff=20, landing=28
        )
        poses = _poses_from_com(com_y, baseline_y=0.5)

        # Sanity: CoM matches the designed trajectory.
        com_check = calculate_com_trajectory(poses)
        np.testing.assert_allclose(com_check, com_y, atol=1e-5)

        detector = PhaseDetector()
        result = detector._detect_jump_phases_parabolic(poses, fps=fps)

        # The parabolic path found a perfect parabola (R^2=1.0) with
        # takeoff=20, landing=28 (proven via _scan_to_baseline). The inclusive
        # airtime = 9/30 = 0.300 s passes the `airtime < 0.3` gate. The detector
        # should return this as the best result: landing == 28.
        assert result.phases.takeoff == 20, (
            f"Expected parabolic takeoff=20 (true flight start), got "
            f"takeoff={result.phases.takeoff}. The 9-frame flight "
            f"(takeoff=20, landing=28, R^2=1.0) should be detected by the "
            f"parabolic path."
        )
        assert result.phases.landing == 28, (
            f"BUG: phase_detector.py:426 `airtime = (landing_idx - takeoff_idx) "
            f"/ fps` is a SPAN (8/30 = 0.267 < 0.3), but takeoff_idx/landing_idx "
            f"are INCLUSIVE frame indices (proven: _scan_to_baseline docstring "
            f"'Frame index where CoM returns to baseline' at :480; :449/:451 "
            f"route to ElementPhase.takeoff/landing; physics_engine.py:631 "
            f"`com[takeoff:landing+1]` slice +1 confirms inclusive). The "
            f"correct COUNT is (28 - 20 + 1)/30 = 0.300 s, which passes the "
            f"`airtime < 0.3` gate. The span off-by-one rejects this valid "
            f"9-frame/0.300s jump (single-rotation waltz_jump/toe_loop airtime "
            f"~0.3-0.4s) -> confidence=0.0/fallback -> valid jump LOST from "
            f"coach report -> downstream metrics/GOE/recommender get fallback. "
            f"Got landing={result.phases.landing} (fallback wider window), "
            f"expected landing=28 (true inclusive flight end). #518 sibling "
            f"(ElementPhase.airtime_sec inclusive-end), same line as #499/#505 "
            f"(fps=0 — different bug), #515 family (inclusive-end span)."
        )

    def test_inclusive_airtime_at_boundary_not_rejected(self):
        """Directly prove the gate rejects a 0.300 s inclusive airtime.

        Replicates the exact computation at phase_detector.py:426 to show
        that 9 inclusive frames at 30 fps (0.300 s) is falsely rejected by
        the span formula while passing the inclusive formula.
        """
        fps = 30.0
        takeoff_idx = 20
        landing_idx = 28  # 20..28 inclusive = 9 frames

        span_airtime = (landing_idx - takeoff_idx) / fps  # BUG: 8/30
        count_airtime = (landing_idx - takeoff_idx + 1) / fps  # CORRECT: 9/30

        # The gate is `if airtime < 0.3: reject`.
        # Inclusive 0.300 must NOT be rejected (0.300 < 0.3 is False).
        assert count_airtime >= 0.3, (
            f"Inclusive airtime {count_airtime:.4f} should pass the >= 0.3 "
            f"threshold (9 frames / 30 fps = 0.300 s)"
        )
        # The span formula wrongly rejects this valid jump.
        assert span_airtime < 0.3, (
            f"Span airtime {span_airtime:.4f} is the BUG value that causes "
            f"the gate to reject a valid 0.300 s jump"
        )
        # Therefore the current code (span) rejects; the fix (count) accepts.
        gate_rejects_span = span_airtime < 0.3  # True with bug
        gate_rejects_count = count_airtime < 0.3  # False with fix
        assert gate_rejects_count is False, (
            "With the inclusive fix, the gate must NOT reject a 0.300 s jump."
        )
        assert gate_rejects_span is True, (
            f"BUG: the span formula (landing-takeoff)/fps = {span_airtime:.4f} "
            f"falsely rejects a valid 0.300 s (9-frame @ 30fps) jump at the "
            f"minimum-airtime gate. phase_detector.py:205,426 should be "
            f"(landing_idx - takeoff_idx + 1) / fps."
        )

    def test_scan_to_baseline_returns_inclusive_frame_indices(self):
        """Prove _scan_to_baseline returns inclusive concrete frame indices.

        This confirms the inclusive convention: takeoff_idx and landing_idx
        from _scan_to_baseline are the actual frame where CoM crosses
        baseline, and they route directly to ElementPhase.takeoff/landing
        (which physics_engine.py:631 slices as com[takeoff:landing+1]).
        """
        fps = 30.0
        com_y = _nine_frame_flight_com(
            n_frames=60, baseline_y=0.5, peak_y=0.2, center=24, takeoff=20, landing=28
        )
        poses = _poses_from_com(com_y, baseline_y=0.5)
        com_check = calculate_com_trajectory(poses)
        np.testing.assert_allclose(com_check, com_y, atol=1e-5)

        # Reproduce the parabolic detector's baseline + scan internally.
        n = len(poses)
        com_smooth = com_y.astype(np.float64)
        baseline_win = min(61, max(21, n // 3))
        baseline = median_filter(com_smooth, size=baseline_win)

        # Peak of the parabola is at center=24.
        peak_frame = 24
        takeoff_idx = PhaseDetector._scan_to_baseline(
            com_smooth, baseline, peak_frame, direction=-1
        )
        landing_idx = PhaseDetector._scan_to_baseline(
            com_smooth, baseline, peak_frame, direction=+1
        )

        # The scan returns the concrete frame where CoM crosses baseline.
        assert takeoff_idx == 20, (
            f"_scan_to_baseline backward from peak=24 should return 20 "
            f"(first frame where com >= baseline), got {takeoff_idx}"
        )
        assert landing_idx == 28, (
            f"_scan_to_baseline forward from peak=24 should return 28 "
            f"(first frame where com >= baseline), got {landing_idx}"
        )
        # 20..28 inclusive = 9 frames. These are the same indices routed to
        # ElementPhase.takeoff/landing at phase_detector.py:449/:451.
        inclusive_count = landing_idx - takeoff_idx + 1
        assert inclusive_count == 9
        # The span (current airtime formula) is 8, one short.
        assert landing_idx - takeoff_idx == 8
