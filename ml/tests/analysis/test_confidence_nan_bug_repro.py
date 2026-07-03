"""RED repro — confidence.py NaN-clamp bug (tranche H).

Bug #10: confidence.py:51 `return max(0.0, min(1.0, confidence))` silently
  returns 1.0 when the weighted sum is NaN. Python's builtin `min(1.0, NaN)`
  returns 1.0 (ignores NaN), so `max(0.0, 1.0)` returns 1.0.

Source: ml/src/analysis/confidence.py:44-51.

When `phase.confidence` is NaN (e.g. upstream phase detection failed
silently), the function reports PERFECT confidence (1.0) for the phase.
This propagates to `compute_overall_confidence` which weighted-averages
across all phases, inflating the overall confidence value.

NOT-a-bug guards for:
- ZeroDivisionError catch in compute_joint_angles (line 99) — numba
  jitted angle_3pt_rad raises ZeroDivisionError on NaN input, which is
  caught and returns np.nan. This is the CORRECT path (not silent 0.0
  as initially reported by the agent).
"""

from __future__ import annotations

import pytest


def test_nan_phase_confidence_returns_1_0_silently():
    """Bug #10: NaN input to compute_phase_confidence must NOT return 1.0.

    Pre-fix: Python's `min(1.0, NaN)` returns 1.0 (NaN is ignored in
    comparison) → `max(0.0, 1.0)` returns 1.0. A phase with completely
    missing/NaN confidence is reported as 100% confident.

    #561 fix: NaN input → 0.0 confidence (the phase is unreliable, not
    perfect). Explicit `math.isnan` check before the clamp.
    """
    import math

    from src.analysis.confidence import compute_phase_confidence
    from src.analysis.types import PhaseExtended

    phase = PhaseExtended(
        name="air",
        start_frame=10,
        end_frame=40,
        start_time=10 / 30.0,
        end_time=40 / 30.0,
        confidence=float("nan"),  # upstream phase detection failed
        detection_method="com_parabola",
    )
    result = compute_phase_confidence(phase, total_frames=120, fps=30.0)
    # Post-fix: NaN input → 0.0 confidence (unreliable phase).
    assert result == 0.0, (
        f"NaN phase.confidence should produce 0.0 confidence (phase is "
        f"unreliable), got {result}. Pre-fix: min(1.0, NaN) returns 1.0, "
        f"silently reporting perfect confidence for missing data."
    )
    assert math.isfinite(result), f"NaN input must NOT propagate NaN to output. Got {result}."


def test_nan_phase_confidence_propagates_to_overall():
    """Bug #10b: NaN phase must NOT inflate overall confidence.

    Pre-fix: single phase with NaN confidence → reports 1.0 → overall 1.0.
    Post-fix: NaN phase reports 0.0 → overall 0.0 (or similar).
    """
    from src.analysis.confidence import compute_overall_confidence
    from src.analysis.types import PhaseDetectionResultV2, PhaseExtended

    nan_phase = PhaseExtended(
        name="air",
        start_frame=10,
        end_frame=40,
        start_time=10 / 30.0,
        end_time=40 / 30.0,
        confidence=float("nan"),
        detection_method="com_parabola",
    )
    result = PhaseDetectionResultV2(phases=[nan_phase], element_type="waltz_jump")
    overall = compute_overall_confidence(result, total_frames=120, fps=30.0)
    # Post-fix: NaN-only phases should produce 0.0 overall confidence
    # (the entire analysis is unreliable), NOT 1.0.
    assert overall < 1.0, (
        f"NaN-only phases should NOT produce 1.0 overall confidence, got {overall}. "
        f"Pre-fix: 1.0 (fake perfect). Post-fix: 0.0 (unreliable analysis)."
    )


def test_min_max_builtin_nan_ignored_direct():
    """Document the root cause: Python's min/max ignore NaN in comparisons."""
    nan = float("nan")
    # min(1.0, NaN) returns 1.0 — the first argument
    assert min(1.0, nan) == 1.0, "Python min(1.0, NaN) returns 1.0"
    # max(0.0, 1.0) returns 1.0
    assert max(0.0, min(1.0, nan)) == 1.0, "max(0.0, min(1.0, NaN)) returns 1.0"


# ---------------------------------------------------------------------------
# NOT-a-bug guards
# ---------------------------------------------------------------------------


def test_angle_3pt_with_nan_raises_zero_division_error_in_jitted():
    """NOT a bug: numba-jitted angle_3pt_rad raises ZeroDivisionError on NaN,
    which is caught by compute_joint_angles and returns np.nan.

    The agent who initially reported this bug as silent-0.0 was wrong
    because the numba-jitted version's behavior differs from plain numpy.
    """
    from src.analysis.angles import compute_joint_angles
    from src.types import H36Key

    # Build a pose with one NaN keypoint at the right hip
    pose = np.zeros((17, 2), dtype=np.float32)
    pose[H36Key.LHIP] = [0.4, 0.5]
    pose[H36Key.RHIP] = [float("nan"), 0.5]  # NaN at vertex input
    pose[H36Key.THORAX] = [0.5, 0.3]
    pose[H36Key.LKNEE] = [0.45, 0.7]
    pose[H36Key.RKNEE] = [0.55, 0.7]
    pose[H36Key.LSHOULDER] = [0.4, 0.3]
    pose[H36Key.RSHOULDER] = [0.5, 0.3]
    pose[H36Key.RELBOW] = [0.55, 0.4]
    pose[H36Key.LELBOW] = [0.45, 0.4]
    pose[H36Key.LFOOT] = [0.45, 0.9]
    pose[H36Key.RFOOT] = [0.55, 0.9]
    pose[H36Key.LWRIST] = [0.4, 0.5]
    pose[H36Key.RWRIST] = [0.5, 0.5]

    angles = compute_joint_angles(pose)
    # Angles involving the NaN hip should be NaN, not 0.0
    # "R Hip" uses RKNEE, RHIP, RKNEE — the RHIP is NaN
    assert "R Hip" in angles, f"Expected 'R Hip' in angles, got {list(angles.keys())}"
    r_hip = angles["R Hip"]
    # Document: this is NaN, NOT 0.0 (the try/except catches ZeroDivisionError)
    assert np.isnan(r_hip), (
        f"R Hip angle with NaN hip should be NaN, got {r_hip}. "
        f"compute_joint_angles correctly returns NaN for invalid pose keypoints."
    )


import numpy as np  # needed for the test above
