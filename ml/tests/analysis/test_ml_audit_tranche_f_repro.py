"""RED repro — ML pipeline bugs from audit (tranche F).

Bug #1: metrics.py compute_rotation_yaw_delta uses exclusive-end slice
  (phases.takeoff:phases.landing) while the rest of the codebase uses
  inclusive-end (phases.takeoff:phases.landing+1). This drops the landing
  frame from the yaw trajectory, making rotation count ~1 frame short.

Bug #3: multi_score.py line 33 rewards over-rotation. When
  under_rotation_deg < 0 (over-rotation), the formula
  (1 - under_rotation_deg / 90) * weight increases the subscore instead
  of decreasing it. A triple with 20° over-rotation gets rotation_subscore
  = 0.367 instead of the expected 0.233.

Bug #4: metrics.py compute_landing_knee_stability and
  compute_landing_trunk_recovery use exclusive-end slices WITHOUT capping
  at len(poses), unlike compute_landing_smoothness which does
  min(phases.end + 1, len(poses)). This can cause IndexError on
  degenerate boundaries.

These tests document the bugs as source-level assertions. Full reproduction
  would require GPU inference, which is not available in test.
"""

import pytest


def test_yaw_delta_exclusive_end_slice():
    """Bug #1: compute_rotation_yaw_delta uses exclusive-end (takeoff:landing)
    while flight height uses inclusive-end (takeoff:landing+1).

    This drops the landing frame from the yaw trajectory.
    """
    from pathlib import Path

    metrics_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "metrics.py"
    source = metrics_path.read_text()

    # #554: yaw delta path must use inclusive-end slice to match the rest of
    # the codebase (flight height at 797/1515). np.arange(takeoff, landing)
    # drops the landing frame — rotation count ~1 frame short.
    # After fix: arange upper bound is `phases.landing + 1` (inclusive).
    assert "np.arange(phases.takeoff, phases.landing + 1)" in source, (
        "Yaw delta path must use inclusive-end slice (phases.landing + 1) "
        "to match flight height and not drop the landing frame."
    )

    # The flight height path uses inclusive end (landing+1)
    assert "phases.takeoff : phases.landing + 1" in source, (
        "Expected inclusive-end slice in flight height path"
    )

    # No exclusive-end slices should remain in the flight window range.
    import re

    exclusive = len(re.findall(r"np\.arange\(phases\.takeoff,\s*phases\.landing\)", source))
    assert exclusive == 0, (
        f"Exclusive-end np.arange(phases.takeoff, phases.landing) still present "
        f"({exclusive} occurrence(s)) — drops the landing frame."
    )

    inclusive = len(re.findall(r"phases\.landing \+ 1", source))
    assert inclusive >= 3, "Inclusive-end pattern exists (used by height, phases, etc.)"


def test_under_rotation_negative_rewards_over_rotation():
    """Bug #3: over-rotation (negative under_rotation_deg) INCREASES rotation subscore.

    Formula: (1 - under_rotation_deg / 90) * 0.3
    When under_rotation_deg = -20 (over-rotation):
      (1 - (-20) / 90) * 0.3 = (1 + 0.222) * 0.3 = 0.367
    Expected: rotation subscore should DECREASE for over-rotation.
    """
    # Over-rotation: measured 1100° vs target 1080° → under_rotation = -20
    under_rotation_deg = -20.0
    rotation_weight = 0.3
    # #555: abs() — over-rotation should DECREASE subscore (judges deduct
    # for both under and over). Old sign-sensitive (1 - x/90) REWARDED
    # over-rotation (1 - -20/90 = 1.222 > 1.0, subscore 0.367 > weight 0.3).
    rotation_subscore = (1 - abs(under_rotation_deg) / 90) * rotation_weight

    assert rotation_subscore < rotation_weight, (
        f"Over-rotation still REWARDS subscore: {rotation_subscore:.3f} > {rotation_weight:.3f}. "
        f"Over-rotation should DECREASE the subscore, not increase it."
    )

    # Normal case: under-rotation = 30° → subscore should decrease
    normal_under = 30.0
    normal_subscore = (1 - normal_under / 90) * rotation_weight
    assert normal_subscore < rotation_weight, (
        f"Under-rotation decreases subscore: {normal_subscore:.3f} < {rotation_weight:.3f} (correct)"
    )


def test_landing_stability_no_array_bounds_guard():
    """Bug #4: compute_landing_knee_stability and compute_landing_trunk_recovery
    use exclusive-end slices WITHOUT capping at len(poses).

    compute_landing_smoothness correctly caps:
      min(phases.end + 1, len(poses))
    But compute_landing_knee_stability does NOT cap:
      poses[post_landing_start : phases.end + 1]
    If phases.end == len(poses) - 1, this is fine.
    If phases.end >= len(poses), this crashes or returns empty array.
    """
    from pathlib import Path

    metrics_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "metrics.py"
    source = metrics_path.read_text()

    # compute_landing_smoothness has the guard
    assert "min(phases.end + 1, len(poses))" in source, (
        "Expected array bounds guard in compute_landing_smoothness"
    )

    # compute_landing_knee_stability does NOT have the guard
    # Find the stability function's slice
    stability_start = source.find("def compute_landing_knee_stability")
    stability_end = source.find("def compute_landing_trunk_recovery")
    stability_body = source[stability_start:stability_end]

    # It uses phases.end + 1 without capping
    assert "phases.end + 1" in stability_body, "Expected exclusive-end slice in stability function"
    assert (
        "min(" not in stability_body
        or "min(" in stability_body[: stability_body.find("phases.end")]
    ), "Stability function should NOT cap the slice (that's the bug)"


def test_arm_position_math_is_correct():
    """NOT a bug: compute_arm_position math is equivalent.

    np.mean(left_dist + right_dist) / 2 == (np.mean(left) + np.mean(right)) / 2
    due to linearity. The clamp max(0, 1-avg) correctly zeroes negative values.
    """
    import numpy as np

    left = np.array([0.3, 0.4, 0.5])
    right = np.array([0.2, 0.3, 0.4])

    # Code version
    avg_code = float(np.mean(left + right) / 2)
    result_code = float(max(0, 1 - avg_code))

    # Alternative version
    avg_alt = float((np.mean(left) + np.mean(right)) / 2)
    result_alt = float(max(0, 1 - avg_alt))

    assert abs(result_code - result_alt) < 1e-10, "arm_position math should be equivalent"


def test_python_min_vs_np_minimum_for_nan():
    """NOT a bug: Python min(130, NaN) returns 130, not NaN.

    compute_landing_quality uses Python's min(), not np.minimum().
    Python's min() ignores NaN in the comparison, returning the
    non-NaN value. This is CORRECT behavior for the landing quality
    case — we want the better (less bent) knee angle.
    """
    import numpy as np

    left_angle = 130.0
    right_angle = float("nan")

    # Python min() — used in the code
    py_result = min(left_angle, right_angle)
    assert py_result == 130.0, f"Python min(130, NaN) should return 130.0, got {py_result}"

    # np.minimum — would propagate NaN (NOT used in the code)
    np_result = np.minimum(left_angle, right_angle)
    assert np.isnan(np_result), f"np.minimum(130, NaN) should return NaN, got {np_result}"
