"""RED repro — `BiomechanicsAnalyzer.compute_rotation_speed`
(ml/src/analysis/metrics.py:1381) LEAKS NaN into the rotation-speed metric when
a shoulder keypoint is NaN on the flight frames — a silent NaN-poisoning of
the report, not a crash.

Root cause (ml/src/analysis/metrics.py:1381-1415):
  `compute_rotation_speed` computes the shoulder-axis angle with NO NaN guard:
    line 1393: `left_shoulder = poses[:, H36Key.LSHOULDER]`
    line 1394: `right_shoulder = poses[:, H36Key.RSHOULDER]`
    line 1396: `shoulder_vector = right_shoulder - left_shoulder`
    line 1397: `angles = np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])`
    line 1400: `velocity = self.compute_angular_velocity(angles_deg, fps)`
    line 1404: `flight_velocity = velocity[phases.takeoff : phases.landing]`
    line 1405: `return float(np.max(np.abs(flight_velocity)))`
  With NaN in a shoulder on any flight frame: `shoulder_vector` contains NaN
  → `np.arctan2(nan, x)` = NaN → `angles_deg` NaN → `compute_angular_velocity`
  (`np.unwrap(nan)` = NaN, `np.gradient(nan)` = NaN) → `velocity` NaN →
  `flight_velocity` contains NaN → `np.max(np.abs(NaN))` = NaN (np.max, not
  np.nanmax) → returns NaN.

  The degenerate-phases guard (line 1403-1404, `if phases.takeoff <
  phases.landing and phases.landing < len(velocity)`) does NOT cover NaN —
  phases are valid here, the data is NaN. `np.max(np.abs(...))` (not
  `np.nanmax`) returns NaN if ANY element is NaN. `compute_rotation_speed` has
  NO NaN check: it does not `np.isnan`-mask, does not `np.nanmax`, does not
  return a 0.0 sentinel.

Consumer (ml/src/analysis/metrics.py:230):
  `BiomechanicsAnalyzer.analyze` calls
  `rot_speed = self.compute_rotation_speed(poses, phases, fps)` (line 230) and
  packs it into `MetricResult(name="rotation_speed", value=rot_speed, ...)`. A
  NaN shoulder on a flight frame → `rotation_speed` = NaN → the metric list →
  the recommender → the report JSON → the GOE proxy. The user gets a report
  with a NaN/missing rotation speed instead of a degraded-but-finite estimate
  (NaN-masked peak, or 0.0 sentinel).

Consequences (prod impact):
  1. A NaN shoulder keypoint on ANY flight frame (shoulders can be occluded
     during fast rotation — arms cross the body) silently NaN-poisons the
     `rotation_speed` metric. No exception, no warning — the NaN flows into the
     report JSON / GOE.
  2. `rotation_speed` is a key GOE-proxy feature (peak angular velocity during
     flight — a primary jump-quality signal). A NaN here breaks the GOE
     computation downstream (`compute_goe_score` aggregates the metrics).
  3. The bug is the same `np.max(np.abs(NaN))` = NaN pattern as the CoM tranches
     (CE `compute_jump_height_com` #899, `np.min(flight_com)`) — `np.max`/`np.min`
     propagate NaN, the metric layer has no NaN guard.
  4. Existing tests (`test_metrics*` / `test_biomechanics*`) feed all-valid
     poses. No test feeds a NaN shoulder on a flight frame and asserts the
     rotation speed degrades (NaN-masked finite peak or 0.0 sentinel), not NaN.

The fix (NOT applied — repro only):
  - `compute_rotation_speed`: NaN-mask the shoulder vector before `arctan2`
    (skip NaN frames, `np.nanmean`-style), OR `np.nanmax(np.abs(flight_velocity))`
    (NaN-ignored peak) + guard (if all-NaN flight → 0.0 sentinel); and/or
  - `compute_angular_velocity`: NaN-mask before `np.gradient` (but the
    gradient of a NaN-containing series is NaN at the NaN and its neighbors —
    `np.nanmax` at the consumer is the cleaner local fix); and/or
  - guard `if not np.isfinite(peak): return 0.0` before return.
  - The deeper fix is in gap-filling/smoothing (ensure no NaN reaches the
    metric), but the metric must still be defensive.

The correct contract: a NaN shoulder keypoint on a flight frame must NOT
NaN-poison the rotation-speed metric. `compute_rotation_speed` must return a
finite float (NaN-masked peak or 0.0 sentinel), NOT NaN.

RED now: the observable assertions below describe the CORRECT behavior — a
finite rotation speed on NaN-keypoint input. They FAIL because `np.max(np.abs(
flight_velocity))` is NaN. After the fix: NaN is masked and the speed is
finite. The source-check test confirms `compute_rotation_speed` uses
`np.max(np.abs(flight_velocity))` (NOT `np.nanmax`) and has NO NaN guard —
root cause locked.

Pure-Python (no GPU, no DB): `compute_rotation_speed` and
`compute_angular_velocity` are pure-data functions over pose arrays.
"""

import inspect

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _poses(n: int = 12) -> np.ndarray:
    """A 12-frame NormalizedPose (17, 2) with shoulders rotating (increasing
    angle across frames) so the all-valid rotation speed is a finite positive
    deg/s (~515 deg/s at 30 fps).

    H3.6M indices (this build):
      1 RHIP, 2 RKNEE, 3 RFOOT, 4 LHIP, 5 LKNEE, 6 LFOOT,
      11 LSHOULDER, 14 RSHOULDER.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        ang = 0.3 * f  # radians, increasing — shoulder axis rotates
        poses[f, H36Key.LSHOULDER] = [-0.2 * np.cos(ang), 0.1 + 0.2 * np.sin(ang)]
        poses[f, H36Key.RSHOULDER] = [0.2 * np.cos(ang), 0.1 - 0.2 * np.sin(ang)]
        poses[f, H36Key.RHIP] = [0.1, 0.5]
        poses[f, H36Key.LHIP] = [-0.1, 0.5]
        poses[f, H36Key.RKNEE] = [0.1, 0.7]
        poses[f, H36Key.LKNEE] = [-0.1, 0.7]
        poses[f, H36Key.RFOOT] = [0.1, 0.9]
        poses[f, H36Key.LFOOT] = [-0.1, 0.9]
    return poses


def _phases() -> ElementPhase:
    return ElementPhase(name="j", start=0, takeoff=2, peak=5, landing=7, end=10)


# --------------------------------------------------------------------------- #
# Observable 1: a NaN shoulder on the flight frames must NOT NaN-poison
# compute_rotation_speed — must return a finite float, NOT NaN.
# --------------------------------------------------------------------------- #


def test_nan_shoulder_rotation_speed_finite_repro():
    """CORRECT behavior: `compute_rotation_speed` with a NaN RSHOULDER on the
    flight frames (3..6 — shoulders occluded during fast rotation, arms cross
    the body) must return a FINITE float (a NaN-masked peak velocity, or the
    0.0 degenerate sentinel), NOT NaN. The metric must degrade gracefully — the
    user gets a degraded-but-finite rotation speed, not a NaN hole in the
    report.

    RED now: NaN RSHOULDER on flight frames → `shoulder_vector` NaN →
    `np.arctan2(nan, x)` = NaN → `compute_angular_velocity` (`np.unwrap(nan)` =
    NaN, `np.gradient(nan)` = NaN) → `velocity` NaN → `flight_velocity` contains
    NaN → `np.max(np.abs(NaN))` = NaN (np.max, NOT np.nanmax) → returns NaN.
    `analyze` (line 230) packs this NaN into `MetricResult(name="
    rotation_speed", value=NaN)` → the NaN flows into the report JSON / GOE.
    After the fix: NaN masked (`np.nanmax` / NaN-guard / 0.0 sentinel) and the
    speed is finite.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))

    # Baseline: all-valid → finite positive rotation speed.
    v_valid = an.compute_rotation_speed(_poses(), _phases(), fps=30.0)
    assert np.isfinite(v_valid) and v_valid > 0.0, (
        f"test fixture broken: all-valid rotation speed {v_valid} is "
        f"non-finite or non-positive; expected finite > 0. The fixture needs "
        f"shoulders rotating (increasing angle) so the angular velocity is a "
        f"finite positive deg/s."
    )

    poses = _poses()
    for f in range(3, 7):
        poses[f, H36Key.RSHOULDER] = [np.nan, np.nan]  # NaN RSHOULDER on flight

    v = an.compute_rotation_speed(poses, _phases(), fps=30.0)
    assert isinstance(v, float), (
        f"BUG: compute_rotation_speed returned non-float {type(v).__name__} "
        f"({v}) for NaN-shoulder input; expected float."
    )
    assert np.isfinite(v), (
        f"BUG: compute_rotation_speed returned {v} (NaN) for a NaN RSHOULDER "
        f"on the flight frames 3..6 (occlusion during fast rotation). "
        f"`shoulder_vector = right_shoulder - left_shoulder` → NaN → "
        f"`np.arctan2(nan, x)` = NaN → `compute_angular_velocity` (`np.unwrap("
        f"nan)` = NaN, `np.gradient(nan)` = NaN) → `velocity` NaN → "
        f"`flight_velocity` contains NaN → `np.max(np.abs(NaN))` = NaN (np.max, "
        f"NOT np.nanmax) → returns NaN. `analyze` (line 230) packs this NaN into "
        f'`MetricResult(name="rotation_speed", value=NaN)` → the NaN flows '
        f"into the report JSON / GOE proxy (`rotation_speed` is a primary "
        f"jump-quality signal). The user gets a NaN hole in the report instead "
        f"of a degraded-but-finite estimate. (Sanity: all-valid = {v_valid}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in EITHER shoulder — the shoulder
# vector poisons on NaN in either endpoint.
# --------------------------------------------------------------------------- #


def test_nan_any_shoulder_rotation_speed_finite_repro():
    """CORRECT behavior: a NaN in EITHER shoulder (LSHOULDER or RSHOULDER) on
    the flight frames must NOT NaN-poison `compute_rotation_speed`.
    `shoulder_vector = right_shoulder - left_shoulder` poisons on NaN in EITHER
    endpoint, so any occluded shoulder keypoint triggers the bug.

    RED now: NaN in LSHOULDER (11), RSHOULDER (14) each → NaN speed. After the
    fix: graceful degradation on any occluded shoulder.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    for kp in (H36Key.LSHOULDER, H36Key.RSHOULDER):
        poses = _poses()
        for f in range(3, 7):
            poses[f, kp] = [np.nan, np.nan]
        v = an.compute_rotation_speed(poses, _phases(), fps=30.0)
        assert np.isfinite(v), (
            f"BUG: compute_rotation_speed returned {v} (NaN) for a NaN "
            f"shoulder ({kp.name}) on the flight frames 3..6. "
            f"`shoulder_vector = right_shoulder - left_shoulder` poisons on NaN "
            f"in EITHER endpoint, so any occluded shoulder keypoint triggers "
            f"the NaN-leak. (A fix that only guards one shoulder leaves the "
            f"other broken.)"
        )


# --------------------------------------------------------------------------- #
# Observable 3: the NaN-poisoned speed flows through `analyze` into the
# `rotation_speed` MetricResult — the real prod-impact path (report JSON / GOE).
# --------------------------------------------------------------------------- #


def test_analyze_rotation_speed_metric_finite_on_nan_shoulder_repro():
    """CORRECT behavior: `BiomechanicsAnalyzer.analyze` with a NaN RSHOULDER on
    the flight frames must produce a `rotation_speed` metric with a FINITE
    value, NOT NaN. `analyze` (line 230) calls `compute_rotation_speed` and
    packs the result into `MetricResult(name="rotation_speed", value=rot_speed)`
    — a NaN speed flows unchanged into the metric list → recommender → report
    JSON → GOE proxy. This is the real prod-impact path: the user's report gets
    a NaN rotation speed (a primary jump-quality signal) instead of a
    degraded-but-finite estimate.

    RED now: NaN RSHOULDER on flight frames 3..6 → `rotation_speed` metric
    value = NaN. After the fix: finite `rotation_speed` metric value.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    poses = _poses()
    for f in range(3, 7):
        poses[f, H36Key.RSHOULDER] = [np.nan, np.nan]

    results = an.analyze(poses, _phases(), fps=30.0)
    rot_metric = next((r for r in results if r.name == "rotation_speed"), None)
    assert rot_metric is not None, (
        "BUG: analyze() did not produce a `rotation_speed` metric; the metric "
        "name or the analyze() output changed — update the repro fixture."
    )
    assert np.isfinite(rot_metric.value), (
        f"BUG: analyze() `rotation_speed` metric value = {rot_metric.value} "
        f"(NaN) for a NaN RSHOULDER on the flight frames 3..6. `analyze` (line "
        f"230) calls `compute_rotation_speed` and packs the result into "
        f'`MetricResult(name="rotation_speed", value=rot_speed)` — the NaN '
        f"speed flows unchanged into the metric list → recommender → report "
        f"JSON → GOE proxy (`rotation_speed` is a primary jump-quality signal). "
        f"The user's report gets a NaN rotation speed instead of a "
        f"degraded-but-finite estimate. This is the real prod-impact path (a "
        f"NaN hole in the report / a NaN GOE), not just an internal-metric NaN."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid poses still produce a finite positive rotation
# speed.
# --------------------------------------------------------------------------- #


def test_all_valid_rotation_speed_unchanged_repro():
    """Regression guard: all-valid poses must still produce a finite positive
    rotation speed. The fix (NaN guard / `np.nanmax` / 0.0 sentinel) must not
    change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the all-valid case.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    v = an.compute_rotation_speed(_poses(), _phases(), fps=30.0)
    assert np.isfinite(v) and v > 0.0, (
        f"BUG (regression): all-valid rotation speed {v} is non-finite or "
        f"non-positive; expected finite > 0. The no-NaN case must be unchanged "
        f"by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — compute_rotation_speed uses
# np.max(np.abs(flight_velocity)) (NOT np.nanmax) and has NO NaN guard.
# --------------------------------------------------------------------------- #


def test_rotation_speed_nan_leak_source_repro():
    """Source check (GREEN contract): the NaN-leak fix is locked.

    - `compute_rotation_speed` still computes the shoulder-axis angle via
      `np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])` (the fix is
      at the peak, not the angle).
    - the peak uses `np.nanmax(np.abs(flight_velocity))` (#903, NOT
      `np.max`) so a NaN shoulder frame does not poison the peak into NaN.
    - a finite-guard returns 0.0 when every flight frame is NaN.
    - the degenerate-phases sentinel (`return 0.0`) is still present.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_rotation_speed)
    # The shoulder-axis arctan2 is still present (the fix is at the peak).
    assert "np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])" in src, (
        "BUG: compute_rotation_speed must still compute the shoulder-axis "
        "angle via `np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])`; "
        "the #903 fix is at the peak, not the angle."
    )
    # np.nanmax (NOT np.max) skips NaN frames at the peak.
    assert "np.nanmax(np.abs(flight_velocity))" in src, (
        "BUG: compute_rotation_speed must peak with `np.nanmax(np.abs("
        "flight_velocity))` (#903, NOT `np.max`) so a NaN shoulder on a "
        "flight frame does not poison the peak into NaN."
    )
    # A finite-guard returns 0.0 when every flight frame is NaN.
    assert "np.isfinite(peak)" in src, (
        "BUG: compute_rotation_speed must guard `if not np.isfinite(peak): "
        "return 0.0` (#903) so a fully-NaN flight slice degrades to 0.0 "
        "instead of leaking NaN into rotation_speed / GOE."
    )

    # The degenerate-phases guard still exists (returns 0.0).
    assert (
        "if phases.takeoff < phases.landing and phases.landing < len(velocity)" in src
        and "return 0.0" in src
    ), (
        "BUG: compute_rotation_speed must still guard `if phases.takeoff < "
        "phases.landing and phases.landing < len(velocity): ... return 0.0` "
        "(degenerate-phases sentinel); the #903 NaN guard is an addition, not "
        "a replacement."
    )
