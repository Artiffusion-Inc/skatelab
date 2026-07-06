"""RED repro — `BiomechanicsAnalyzer.compute_jump_height_com`
(ml/src/analysis/metrics.py:755) LEAKS NaN into the jump-height metric when a
single keypoint is NaN on the flight frames — a silent NaN-poisoning of the
report, not a crash.

Root cause (ml/src/analysis/metrics.py:784-801):
  `compute_jump_height_com` calls `calculate_com_trajectory(poses)`
  (ml/src/utils/geometry.py) when `com_trajectory is None`.
  `calculate_com_trajectory` computes the CoM Y-coordinate as a plain weighted
  sum of all 17 keypoints (Dempster segment-mass ratios):
      com_y = head*0.081 + torso*0.497 + arms*0.050 + thighs*0.100 + legs*0.161 ...
  It has NO NaN-aware path — no `np.isnan`, no `np.nanmean`, no `np.nan_to_num`,
  no `np.isfinite` mask. A NaN in ANY segment (a single NaN keypoint on a
  flight frame — landing-leg knee frequently occluded in figure skating) makes
  `com_y` NaN for that frame (NaN + finite = NaN, propagates through the
  weighted sum).

  Then:
    line 793: `takeoff_com = com_trajectory[phases.takeoff]`        # NaN if takeoff CoM NaN
    line 797: `flight_com = com_trajectory[phases.takeoff : phases.landing + 1]`
    line 798: `peak_com = np.min(flight_com)`                       # NaN propagate (np.min, not np.nanmin)
    line 801: `return float(takeoff_com - peak_com)`                # nan - nan = nan

  The degenerate-phases guard (line 789-790, `phases.takeoff >= phases.landing
  → 0.0`, ticket #424) does NOT cover NaN — phases are valid here, the data is
  NaN. `np.min` (not `np.nanmin`) returns NaN if ANY element is NaN.

Consumer (ml/src/analysis/metrics.py:203):
  `BiomechanicsAnalyzer.analyze` calls
  `height = self.compute_jump_height_com(poses, phases, com_trajectory=...)`
  and packs it into `MetricResult(name="max_height", value=height, ...)`. A NaN
  height flows unchanged into the metric list → the recommender → the Russian
  text report JSON → the GOE proxy score. `pipeline.py` feeds `analyze` the
  post-gap-fill / post-smoothing poses; if gap-filling fails to fill one
  occluded joint on a flight frame (common — landing-leg knee), the height
  metric silently becomes NaN. The user gets a report with a NaN/missing jump
  height instead of a degraded-but-finite estimate (NaN-masked CoM, or 0.0).

Consequences (prod impact):
  1. A single NaN keypoint on ANY flight frame (landing-leg knee, wrist, elbow
     — all common occlusions) silently NaN-poisons the `max_height` metric.
     No exception, no warning — the NaN flows into the report JSON / GOE.
  2. The bug composes with the CoM tranches (BV `analyze_2d` #883, BW
     `fit_jump_trajectory` #884): `calculate_com_trajectory` is the SHARED root
     cause — the same plain weighted sum, no NaN-aware path, leaks NaN into
     every consumer. `compute_jump_height_com` is one of them.
  3. The 60%-error DEPRECATED `compute_jump_height` (hip-only, line 719) has the
     same bug: `peak_y = np.min(hip_y_series[phases.takeoff : phases.landing])`
     (line 753) — `np.min` of a NaN-containing slice is NaN, `landing_y -
     peak_y` = NaN. A NaN in the hip Y series (occluded hip) leaks NaN the same
     way. The deprecation does not excuse the NaN-leak.
  4. Existing tests (`test_metrics*` / `test_biomechanics*`) feed all-valid
     poses. No test feeds a NaN keypoint on a flight frame and asserts the
     height degrades (finite NaN-masked estimate or 0.0), not NaN.

The fix (NOT applied — repro only):
  - `calculate_com_trajectory`: NaN-mask each segment before the weighted sum
    (skip NaN keypoints — `np.nanmean`-style per-frame, or mask then re-weight
    on the available keypoints) — root-cause fix, fixes ALL CoM consumers
    (this, BV, BW, phase detector); and/or
  - `compute_jump_height_com`: `peak_com = np.nanmin(flight_com)` (NaN-ignored
    min) and guard `takeoff_com` NaN (`if not np.isfinite(takeoff_com): return
    0.0`) — local fix, does not fix the shared root cause; and/or
  - `compute_jump_height` (deprecated): `peak_y = np.nanmin(...)` + takeoff-NaN
    guard — same local pattern.
  - The deeper fix is in gap-filling/smoothing (ensure no NaN reaches the
    metric), but the metric must still be defensive.

The correct contract: a NaN keypoint on a flight frame must NOT NaN-poison the
jump-height metric. `compute_jump_height_com` must return a finite float
(NaN-masked estimate or 0.0 sentinel), NOT NaN. The deprecated
`compute_jump_height` likewise.

RED now: the observable assertions below describe the CORRECT behavior — a
finite height on NaN-keypoint input. They FAIL because `calculate_com_trajectory`
propagates NaN and `np.min(flight_com)` is NaN. After the fix: NaN is masked
and the height is finite. The source-check test confirms
`calculate_com_trajectory` has NO NaN-aware path and `compute_jump_height_com`
uses `np.min` (not `np.nanmin`) — root cause locked.

Pure-Python (no GPU, no DB): `compute_jump_height_com`, `compute_jump_height`,
and `calculate_com_trajectory` are pure-data functions over pose arrays.
"""

import inspect
import warnings

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase
from src.utils.geometry import calculate_com_trajectory


def _poses(n: int = 12) -> np.ndarray:
    """A 12-frame NormalizedPose (17, 2) with a parabolic flight (frames 2..7).

    Layout (H3.6M indices):
      0 HEAD, 1 LSHOULDER, 2 RSHOULDER, 4 LHIP, 5 RHIP,
      7 LFOOT, 8 RFOOT, 9 LELBOW, 10 RELBOW,
      11 RKNEE, 12 LKNEE, 13 LWRIST, 14 RWRIST.

    Frames 2..7 are the flight arc: Y -= 0.02 * (f-2) * (7-f) (peak at frame
    4-5). The all-valid CoM trajectory is finite, so
    `compute_jump_height_com` returns a finite positive height (~0.004 norm).
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, 0] = [0.0, 0.0]            # HEAD
        poses[f, 1] = [-0.2, 0.1]           # LSHOULDER
        poses[f, 2] = [0.2, 0.1]            # RSHOULDER
        poses[f, 4] = [-0.1, 0.5]           # LHIP
        poses[f, 5] = [0.1, 0.5]            # RHIP
        poses[f, 7] = [-0.1, 0.9]           # LFOOT
        poses[f, 8] = [0.1, 0.9]            # RFOOT
        poses[f, 9] = [-0.1, 0.95]          # LELBOW
        poses[f, 10] = [0.1, 0.95]          # RELBOW
        poses[f, 11] = [0.1, 0.7]           # RKNEE
        poses[f, 12] = [-0.1, 0.7]          # LKNEE
        poses[f, 13] = [-0.15, 0.4]         # LWRIST
        poses[f, 14] = [0.15, 0.4]          # RWRIST
    for f in range(2, 8):
        poses[f, :, 1] -= 0.02 * (f - 2) * (7 - f)
    return poses


def _phases() -> ElementPhase:
    return ElementPhase(name="j", start=0, takeoff=2, peak=5, landing=7, end=8)


# --------------------------------------------------------------------------- #
# Observable 1: a NaN landing-leg knee on the flight frames must NOT NaN-poison
# compute_jump_height_com — must return a finite float (NaN-masked estimate or
# 0.0 sentinel), NOT NaN.
# --------------------------------------------------------------------------- #


def test_nan_knee_flight_height_finite_repro():
    """CORRECT behavior: `compute_jump_height_com` with a NaN landing-leg knee
    (RKNEE) on the flight frames (3..6 — occlusion during rotation) must return
    a FINITE float (a NaN-masked CoM estimate, or the 0.0 degenerate sentinel),
    NOT NaN. The metric must degrade gracefully — the user gets a
    degraded-but-finite jump height, not a NaN hole in the report.

    RED now: `calculate_com_trajectory` is a plain weighted sum with no
    NaN-aware path → the NaN RKNEE makes `r_thigh` and `r_leg` NaN → `com_y`
    NaN for frames 3..6 → `flight_com` contains NaN → `peak_com = np.min(...)`
    = NaN (np.min, not np.nanmin) → `takeoff_com - peak_com` = NaN. After the
    fix: NaN masked (root cause: `calculate_com_trajectory` NaN-aware; or local:
    `np.nanmin` + takeoff-NaN guard) and the height is finite.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    poses = _poses()
    for f in range(3, 7):
        poses[f, 11] = [np.nan, np.nan]  # RKNEE NaN on flight frames

    # Baseline: all-valid → finite positive height.
    h_valid = an.compute_jump_height_com(_poses(), _phases())
    assert np.isfinite(h_valid) and h_valid >= 0.0, (
        f"test fixture broken: all-valid jump height {h_valid} is non-finite "
        f"or negative; expected finite >= 0. The fixture needs a parabolic "
        f"flight arc so the all-valid CoM peak is above takeoff."
    )

    h = an.compute_jump_height_com(poses, _phases())
    assert isinstance(h, float), (
        f"BUG: compute_jump_height_com returned non-float {type(h).__name__} "
        f"({h}) for NaN-knee input; expected float."
    )
    assert np.isfinite(h), (
        f"BUG: compute_jump_height_com returned {h} (NaN) for a NaN landing-leg "
        f"knee (RKNEE) on the flight frames 3..6 (occlusion during rotation). "
        f"`calculate_com_trajectory` is a plain weighted sum with NO NaN-aware "
        f"path → the NaN RKNEE makes `r_thigh` and `r_leg` NaN → `com_y` NaN "
        f"for frames 3..6 → `flight_com` contains NaN → `peak_com = np.min(...)` "
        f"= NaN (np.min, NOT np.nanmin) → `takeoff_com - peak_com` = NaN. "
        f"`analyze` (line 203) packs this NaN into `MetricResult(name="
        f"\"max_height\", value=NaN)` → the NaN flows into the report JSON / "
        f"GOE. The user gets a NaN hole in the report instead of a "
        f"degraded-but-finite estimate. (Sanity: all-valid = {h_valid}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint, not just the knee — a
# NaN in any segment poisons the weighted CoM sum. Wide blast radius.
# --------------------------------------------------------------------------- #


def test_nan_any_keypoint_flight_height_finite_repro():
    """CORRECT behavior: a NaN in ANY keypoint on the flight frames (not just
    the knee) must NOT NaN-poison `compute_jump_height_com`.
    `calculate_com_trajectory` uses ALL 17 keypoints in the weighted sum
    (head, torso, arms, thighs, legs — every segment), so a NaN in ANY
    keypoint makes its segment NaN → `com_y` NaN. The bug has a wide blast
    radius — any occluded joint on a flight frame.

    RED now: NaN in LWRIST (13), RELBOW (10), LFOOT (7) each → NaN height.
    After the fix: NaN-masked finite height on any occluded keypoint.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    for kp in (13, 10, 7):  # LWRIST, RELBOW, LFOOT — arm + leg segments
        poses = _poses()
        for f in range(3, 7):
            poses[f, kp] = [np.nan, np.nan]
        h = an.compute_jump_height_com(poses, _phases())
        assert np.isfinite(h), (
            f"BUG: compute_jump_height_com returned {h} (NaN) for a NaN "
            f"keypoint (index {kp}) on the flight frames 3..6. "
            f"`calculate_com_trajectory` uses ALL 17 keypoints in the weighted "
            f"sum (every segment), so a NaN in ANY keypoint makes its segment "
            f"NaN → `com_y` NaN → `np.min(flight_com)` = NaN. The bug has a "
            f"wide blast radius — any occluded joint on a flight frame "
            f"silently NaN-poisons the height metric. (A fix that only masks "
            f"the knee leaves the other 16 keypoints broken.)"
        )


# --------------------------------------------------------------------------- #
# Observable 3: the NaN-poisoned height flows through `analyze` into the
# `max_height` MetricResult — the real prod-impact path (report JSON / GOE).
# --------------------------------------------------------------------------- #


def test_analyze_max_height_metric_finite_on_nan_knee_repro():
    """CORRECT behavior: `BiomechanicsAnalyzer.analyze` with a NaN landing-leg
    knee on the flight frames must produce a `max_height` metric with a FINITE
    value, NOT NaN. `analyze` (line 203) calls `compute_jump_height_com` and
    packs the result into `MetricResult(name="max_height", value=height)` — a
    NaN height flows unchanged into the metric list → recommender → report JSON
    → GOE. This is the real prod-impact path: the user's report gets a NaN
    height instead of a degraded-but-finite estimate.

    RED now: NaN RKNEE on flight frames 3..6 → `max_height` metric value =
    NaN. After the fix: finite `max_height` metric value.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    poses = _poses()
    for f in range(3, 7):
        poses[f, 11] = [np.nan, np.nan]  # RKNEE NaN on flight frames

    results = an.analyze(poses, _phases(), fps=30.0)
    max_height = next(
        (r for r in results if r.name == "max_height"), None
    )
    assert max_height is not None, (
        "BUG: analyze() did not produce a `max_height` metric; the metric "
        "name or the analyze() output changed — update the repro fixture."
    )
    assert np.isfinite(max_height.value), (
        f"BUG: analyze() `max_height` metric value = {max_height.value} (NaN) "
        f"for a NaN landing-leg knee (RKNEE) on the flight frames 3..6. "
        f"`analyze` (line 203) calls `compute_jump_height_com` and packs the "
        f"result into `MetricResult(name=\"max_height\", value=height)` — the "
        f"NaN height flows unchanged into the metric list → recommender → "
        f"report JSON → GOE proxy score. The user's report gets a NaN jump "
        f"height instead of a degraded-but-finite estimate. This is the real "
        f"prod-impact path (a NaN hole in the report / a NaN GOE), not just an "
        f"internal-metric NaN."
    )


# --------------------------------------------------------------------------- #
# Observable 4: the DEPRECATED compute_jump_height (hip-only) has the same
# np.min-NaN-leak — a NaN in the hip Y series leaks NaN. Deprecation does not
# excuse the NaN-leak.
# --------------------------------------------------------------------------- #


def test_deprecated_compute_jump_height_nan_hip_y_finite_repro():
    """CORRECT behavior: the DEPRECATED `compute_jump_height` (hip-only, line
    719) with a NaN in the hip Y series on the flight frames must return a
    FINITE float, NOT NaN. Same `np.min`-NaN-leak: `peak_y = np.min(
    hip_y_series[phases.takeoff : phases.landing])` (line 753) — `np.min` of a
    NaN-containing slice is NaN → `landing_y - peak_y` = NaN. The deprecation
    does not excuse the NaN-leak — deprecated code still runs and still feeds
    reports until removed.

    RED now: NaN hip_y on flight frames 3..6 → NaN height. After the fix:
    `np.nanmin` + NaN-guard, finite height.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    hip_y = _poses()[:, 5, 1].astype(np.float64)  # RHIP Y series
    hip_y_nan = hip_y.copy()
    hip_y_nan[3:7] = np.nan  # NaN hip Y on flight frames (occluded hip)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        h = an.compute_jump_height(hip_y_nan, _phases())

    assert np.isfinite(h), (
        f"BUG: deprecated compute_jump_height returned {h} (NaN) for a NaN in "
        f"the hip Y series on the flight frames 3..6. Same `np.min`-NaN-leak: "
        f"`peak_y = np.min(hip_y_series[phases.takeoff : phases.landing])` "
        f"(line 753) — np.min of a NaN-containing slice is NaN → "
        f"`landing_y - peak_y` = NaN. The deprecation does not excuse the "
        f"NaN-leak — deprecated code still runs and still feeds reports until "
        f"removed."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid poses still produce a finite positive height.
# --------------------------------------------------------------------------- #


def test_all_valid_jump_height_unchanged_repro():
    """Regression guard: all-valid poses must still produce a finite positive
    height. The fix (NaN-aware `calculate_com_trajectory` / `np.nanmin` /
    NaN-guard) must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the all-valid case.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    h = an.compute_jump_height_com(_poses(), _phases())
    assert np.isfinite(h) and h >= 0.0, (
        f"BUG (regression): all-valid jump height {h} is non-finite or "
        f"negative; expected finite >= 0. The no-NaN case must be unchanged "
        f"by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — calculate_com_trajectory has NO NaN-aware
# path; compute_jump_height_com uses np.min (not np.nanmin).
# --------------------------------------------------------------------------- #


def test_compute_jump_height_nan_leak_source_repro():
    """Source check: `calculate_com_trajectory` is a plain weighted sum with NO
    NaN-aware path (no `np.isnan` / `np.nanmean` / `np.nan_to_num` /
    `np.isfinite`), and `compute_jump_height_com` uses `np.min(flight_com)` (NOT
    `np.nanmin`) on line 798. Root cause locked.

    RED now: the plain weighted sum + `np.min` are present (PASS — root cause
    locked). After the fix: a NaN-aware path appears in
    `calculate_com_trajectory` (root cause) OR `np.nanmin` /
    NaN-guard appears in `compute_jump_height_com` (local fix) — this test
    FAILS, signaling the observable tests above should flip to GREEN.
    """
    com_src = inspect.getsource(calculate_com_trajectory)
    # calculate_com_trajectory has NO NaN-aware path — plain weighted sum.
    assert not (
        "np.isnan" in com_src
        or "np.nanmean" in com_src
        or "np.nan_to_num" in com_src
        or "np.isfinite" in com_src
        or "np.nansum" in com_src
    ), (
        "BUG: a NaN-aware path (`np.isnan` / `np.nanmean` / `np.nan_to_num` / "
        "`np.isfinite` / `np.nansum`) appeared in `calculate_com_trajectory` — "
        "the shared CoM NaN-leak root cause is fixed (fixes this, BV #883, BW "
        "#884, and the phase detector). Update the observable tests to the "
        "GREEN contract."
    )

    h_src = inspect.getsource(BiomechanicsAnalyzer.compute_jump_height_com)
    # The unguarded np.min(flight_com) is present (NOT np.nanmin).
    assert "peak_com = np.min(flight_com)" in h_src, (
        "BUG: compute_jump_height_com must use `peak_com = np.min(flight_com)` "
        "(unguarded np.min, line 798) for this repro to be valid. If it was "
        "changed to `np.nanmin` or a NaN-guard was added, the local NaN-leak "
        "is fixed — update the observable tests to the GREEN contract."
    )
    assert "np.nanmin" not in h_src and "np.isnan" not in h_src and \
           "np.isfinite" not in h_src, (
        "BUG: a NaN guard (`np.nanmin` / `np.isnan` / `np.isfinite`) appeared "
        "in compute_jump_height_com — the local NaN-leak is fixed; update the "
        "observable tests to the GREEN contract."
    )

    # The degenerate-phases guard exists (returns 0.0, #424) — proves the
    # codebase already uses a 0.0 sentinel for degenerate input, so a NaN
    # sentinel fits the same pattern.
    assert "if phases.takeoff >= phases.landing:" in h_src and \
           "return 0.0" in h_src, (
        "BUG: compute_jump_height_com must guard `phases.takeoff >= "
        "phases.landing: return 0.0` (degenerate-phases sentinel, #424) for "
        "this repro to be valid. If the guard was removed, the repro is "
        "invalid."
    )

    # The deprecated compute_jump_height has the same np.min-NaN-leak.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        dh_src = inspect.getsource(BiomechanicsAnalyzer.compute_jump_height)
    assert "peak_y = np.min(hip_y_series" in dh_src, (
        "BUG: deprecated compute_jump_height must use `peak_y = np.min("
        "hip_y_series[phases.takeoff : phases.landing])` (unguarded np.min, "
        "line 753) for this repro to be valid. If it was changed to "
        "`np.nanmin` or a NaN-guard was added, the deprecated NaN-leak is "
        "fixed — update the observable tests to the GREEN contract."
    )