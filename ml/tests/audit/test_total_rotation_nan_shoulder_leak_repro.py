"""RED repro — `BiomechanicsAnalyzer.compute_total_rotation_from_poses`
(ml/src/analysis/metrics.py:1202) LEAKS NaN into the total-rotation and
rotation-count metrics when a shoulder keypoint is NaN on the flight frames —
a silent NaN-poisoning of the report, not a crash.

Root cause (ml/src/analysis/metrics.py:1202-1229):
  `compute_total_rotation_from_poses` computes the shoulder-axis angle with NO
  NaN guard:
    line 1216: `shoulder_vector = right_shoulder - left_shoulder`
    line 1217: `angles = np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])`
    line 1218: `unwrapped = np.unwrap(angles)`
    line 1220: `return compute_total_rotation(unwrapped, fps)`
  With NaN in a shoulder on any flight frame: `shoulder_vector` contains NaN
  → `np.arctan2(nan, x)` = NaN → `np.unwrap(NaN)` = NaN → `unwrapped` contains
  NaN. Then `compute_total_rotation` (line 1583):
    line 1586: `total_radians = float(abs(shoulder_angles_unwrapped[-1] - shoulder_angles_unwrapped[0]))`
  If the LAST or FIRST flight frame shoulder is NaN: `unwrapped[-1]` or
  `unwrapped[0]` = NaN → `NaN - x` = NaN → `abs(NaN)` = NaN → `total_degrees` =
  NaN → `rotation_count = NaN / 360.0` = NaN → returns `(NaN, NaN)`.

  The degenerate-phases guard (line 1214-1215, `if phases.takeoff >=
  phases.landing or phases.landing >= len(poses)`) does NOT cover NaN — phases
  are valid here, the data is NaN. `compute_total_rotation` has NO NaN check: it
  does not `np.isnan`-mask, does not `np.nanmean`/`np.nansum`, does not return a
  0.0 sentinel. `compute_total_rotation_from_poses` has NO NaN guard on the
  shoulder vector either.

Consumer (ml/src/analysis/metrics.py:369-417):
  `BiomechanicsAnalyzer.analyze` calls
  `total_rotation_deg, rotation_count = self.compute_total_rotation_from_poses(
  poses, phases, fps)` (line 369) and packs them into
  `MetricResult(name="total_rotation_deg", value=total_rotation_deg)` (line 389)
  and `MetricResult(name="rotation_count", value=rotation_count)` (line 397).
  Then `under_rotation_deg = compute_under_rotation(total_rotation_deg,
  target_rotations)` (line 417) = `target_deg - NaN` = NaN → packed into
  `MetricResult(name="under_rotation_deg", value=NaN)`. A NaN shoulder on a
  flight frame → `total_rotation_deg` = NaN, `rotation_count` = NaN,
  `under_rotation_deg` = NaN → the metric list → the recommender → the report
  JSON → the GOE proxy. The user gets a report with a NaN/missing rotation
  (the primary jump identifier — a waltz jump read as "0 rotations" or a NaN
  hole) instead of a degraded-but-finite estimate (NaN-masked rotation or 0.0
  sentinel).

Consequences (prod impact):
  1. A NaN shoulder keypoint on ANY flight frame (shoulders can be occluded
     during fast rotation — arms cross the body) silently NaN-poisons
     `total_rotation_deg` AND `rotation_count` AND `under_rotation_deg`. No
     exception, no warning — the NaN flows into the report JSON / GOE.
  2. `rotation_count` is the PRIMARY jump identifier (1 = single, 2 = double,
     3 = triple). A NaN here means the recommender cannot tell the user which
     jump they performed — the report is a NaN hole where the jump type should
     be. `under_rotation_deg = NaN` breaks the under-rotation diagnosis
     ("landed 90° short of the rotation" becomes "NaN short").
  3. The bug is the same `np.arctan2(NaN)` = NaN + `np.unwrap(NaN)` = NaN pattern
     as the rotation-speed tranche (CH #903) — the shoulder-axis angle
     computation has no NaN guard at any consumer.
  4. Existing tests (`test_metrics*` / `test_biomechanics*`) feed all-valid
     poses. No test feeds a NaN shoulder on a flight frame and asserts the
     total rotation degrades (NaN-masked finite rotation or 0.0 sentinel), not
     NaN.

The fix (NOT applied — repro only):
  - `compute_total_rotation_from_poses`: NaN-mask the shoulder vector before
    `arctan2` (skip NaN frames, `np.nanmean`-style), OR guard
    `if not np.all(np.isfinite(unwrapped)): return 0.0, 0.0` before return;
    and/or
  - `compute_total_rotation`: NaN-guard the endpoints before the subtraction
    (`np.isfinite`-check on `unwrapped[0]`/`unwrapped[-1]`, return 0.0 sentinel
    on NaN); and/or
  - `analyze` / `compute_under_rotation`: NaN-guard the `total_rotation_deg`
    before `under_rotation_deg = target_deg - total_rotation_deg`.
  - The deeper fix is in gap-filling/smoothing (ensure no NaN reaches the
    metric), but the metric must still be defensive.

The correct contract: a NaN shoulder keypoint on a flight frame must NOT
NaN-poison the total-rotation metrics. `compute_total_rotation_from_poses`
must return finite floats (NaN-masked rotation or 0.0 sentinel), NOT NaN —
and must NOT let the NaN reach `total_rotation_deg` / `rotation_count` /
`under_rotation_deg` in the report.

RED now: the observable assertions below describe the CORRECT behavior — finite
total rotation / count / under-rotation on NaN-keypoint input. They FAIL because
`np.arctan2(NaN)` = NaN, `np.unwrap(NaN)` = NaN, and
`abs(unwrapped[-1] - unwrapped[0])` is NaN. After the fix: NaN is masked and the
rotation is finite. The source-check test confirms
`compute_total_rotation_from_poses` uses `np.arctan2(shoulder_vector[:, 1],
shoulder_vector[:, 0])` + `np.unwrap(angles)` unguarded and has NO NaN guard,
and `compute_total_rotation` uses
`abs(shoulder_angles_unwrapped[-1] - shoulder_angles_unwrapped[0])` unguarded —
root cause locked.

Pure-Python (no GPU, no DB): `compute_total_rotation_from_poses` and
`compute_total_rotation` are pure-data functions over pose arrays.
"""

import inspect

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer, compute_total_rotation
from src.types import ElementPhase, H36Key


def _poses(n: int = 12) -> np.ndarray:
    """A 12-frame NormalizedPose (17, 2) with shoulders rotating (increasing
    angle across frames) so the all-valid total rotation is a finite positive
    number of degrees (~69 deg at 30 fps over the flight window 2..7).

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
    # Flight = frames 2..6 (takeoff..landing). NaN on flight frame 6 (last flight
    # frame) poisons unwrapped[-1] → abs(unwrapped[-1] - unwrapped[0]) = NaN.
    return ElementPhase(name="j", start=0, takeoff=2, peak=5, landing=7, end=10)


# --------------------------------------------------------------------------- #
# Observable 1: a NaN shoulder on the flight frames must NOT NaN-poison
# compute_total_rotation_from_poses — must return finite (deg, count), NOT NaN.
# --------------------------------------------------------------------------- #


def test_nan_shoulder_total_rotation_finite_repro():
    """CORRECT behavior: `compute_total_rotation_from_poses` with a NaN
    RSHOULDER on the last flight frame (frame 6 — the `unwrapped[-1]` endpoint,
    shoulders occluded during fast rotation, arms cross the body) must return
    FINITE floats (a NaN-masked rotation, or the 0.0 degenerate sentinel), NOT
    (NaN, NaN). The metric must degrade gracefully — the user gets a
    degraded-but-finite rotation, not a NaN hole in the report.

    RED now: NaN RSHOULDER on flight frame 6 → `shoulder_vector` NaN on frame 6
    → `np.arctan2(nan, x)` = NaN → `np.unwrap(NaN)` = NaN → `unwrapped[-1]` =
    NaN → `abs(unwrapped[-1] - unwrapped[0])` = NaN → `total_degrees` = NaN →
    `rotation_count` = NaN/360 = NaN → returns (NaN, NaN). `analyze` (line 369)
    packs these NaNs into `MetricResult(name="total_rotation_deg", value=NaN)`
    and `MetricResult(name="rotation_count", value=NaN)` → the NaN flows into
    the report JSON / GOE. After the fix: NaN masked (NaN guard / 0.0 sentinel)
    and the rotation is finite.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))

    # Baseline: all-valid → finite positive total rotation.
    deg_valid, cnt_valid = an.compute_total_rotation_from_poses(
        _poses(), _phases(), fps=30.0
    )
    assert np.isfinite(deg_valid) and deg_valid > 0.0, (
        f"test fixture broken: all-valid total rotation {deg_valid} is "
        f"non-finite or non-positive; expected finite > 0. The fixture needs "
        f"shoulders rotating (increasing angle) so the unwrapped delta is a "
        f"finite positive deg."
    )

    poses = _poses()
    poses[6, H36Key.RSHOULDER] = [np.nan, np.nan]  # NaN RSHOULDER on last flight

    deg, cnt = an.compute_total_rotation_from_poses(poses, _phases(), fps=30.0)
    assert isinstance(deg, float) and isinstance(cnt, float), (
        f"BUG: compute_total_rotation_from_poses returned non-float elements "
        f"({type(deg).__name__}, {type(cnt).__name__}) for NaN-shoulder input; "
        f"expected (float, float)."
    )
    assert np.isfinite(deg), (
        f"BUG: compute_total_rotation_from_poses returned total_rotation_deg = "
        f"{deg} (NaN) for a NaN RSHOULDER on the last flight frame 6. "
        f"`shoulder_vector = right_shoulder - left_shoulder` → NaN on frame 6 "
        f"→ `np.arctan2(nan, x)` = NaN → `np.unwrap(NaN)` = NaN → "
        f"`unwrapped[-1]` = NaN → `abs(unwrapped[-1] - unwrapped[0])` = NaN → "
        f"`total_degrees` = NaN → `rotation_count` = NaN/360 = NaN. `analyze` "
        f"(line 369) packs these NaNs into "
        f"`MetricResult(name=\"total_rotation_deg\", value=NaN)` and "
        f"`MetricResult(name=\"rotation_count\", value=NaN)` → the NaN flows "
        f"into the report JSON / GOE (`rotation_count` is the PRIMARY jump "
        f"identifier — a waltz jump read as a NaN hole). The user gets a NaN "
        f"hole in the report instead of a degraded-but-finite estimate. "
        f"(Sanity: all-valid = {deg_valid:.3f} deg, {cnt_valid:.3f} rotations.)"
    )
    assert np.isfinite(cnt), (
        f"BUG: compute_total_rotation_from_poses returned rotation_count = "
        f"{cnt} (NaN) for a NaN RSHOULDER on the last flight frame 6. "
        f"`rotation_count = total_degrees / 360.0` (line 1587) → NaN / 360 = "
        f"NaN. `rotation_count` is the PRIMARY jump identifier (1 = single, 2 "
        f"= double, 3 = triple); a NaN here means the recommender cannot tell "
        f"the user which jump they performed. The metric must degrade to a "
        f"finite sentinel, not NaN. (Sanity: all-valid = {cnt_valid:.3f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in EITHER shoulder — the shoulder
# vector poisons on NaN in either endpoint, AND on NaN at the first flight
# frame (unwrapped[0]) too.
# --------------------------------------------------------------------------- #


def test_nan_any_shoulder_or_first_frame_total_rotation_finite_repro():
    """CORRECT behavior: a NaN in EITHER shoulder, OR on the FIRST flight
    frame (the `unwrapped[0]` endpoint), must NOT NaN-poison
    `compute_total_rotation_from_poses`. `shoulder_vector = right_shoulder -
    left_shoulder` poisons on NaN in EITHER endpoint; `abs(unwrapped[-1] -
    unwrapped[0])` poisons on NaN at EITHER endpoint frame.

    RED now: NaN in LSHOULDER (11), RSHOULDER (14) on the last flight frame, and
    NaN RSHOULDER on the FIRST flight frame (frame 2) each → (NaN, NaN). After
    the fix: graceful degradation on any occluded shoulder / endpoint.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))

    # NaN in either shoulder on the last flight frame (poisons unwrapped[-1]).
    for kp in (H36Key.LSHOULDER, H36Key.RSHOULDER):
        poses = _poses()
        poses[6, kp] = [np.nan, np.nan]
        deg, cnt = an.compute_total_rotation_from_poses(poses, _phases(), fps=30.0)
        assert np.isfinite(deg) and np.isfinite(cnt), (
            f"BUG: compute_total_rotation_from_poses returned ({deg}, {cnt}) "
            f"(NaN) for a NaN shoulder ({kp.name}) on the last flight frame 6. "
            f"`shoulder_vector = right_shoulder - left_shoulder` poisons on NaN "
            f"in EITHER endpoint, so any occluded shoulder keypoint triggers "
            f"the NaN-leak. (A fix that only guards one shoulder leaves the "
            f"other broken.)"
        )

    # NaN RSHOULDER on the FIRST flight frame (poisons unwrapped[0]).
    poses = _poses()
    poses[2, H36Key.RSHOULDER] = [np.nan, np.nan]
    deg, cnt = an.compute_total_rotation_from_poses(poses, _phases(), fps=30.0)
    assert np.isfinite(deg) and np.isfinite(cnt), (
        f"BUG: compute_total_rotation_from_poses returned ({deg}, {cnt}) "
        f"(NaN) for a NaN RSHOULDER on the FIRST flight frame 2. "
        f"`abs(unwrapped[-1] - unwrapped[0])` poisons on NaN at EITHER endpoint "
        f"frame — the first flight frame is the other endpoint. A guard that "
        f"only checks the last frame leaves the first-frame NaN leak open."
    )


# --------------------------------------------------------------------------- #
# Observable 3: the NaN-poisoned rotation flows through `analyze` into the
# `total_rotation_deg` / `rotation_count` / `under_rotation_deg` metrics — the
# real prod-impact path (report JSON / GOE).
# --------------------------------------------------------------------------- #


def test_analyze_total_rotation_metrics_finite_on_nan_shoulder_repro():
    """CORRECT behavior: `BiomechanicsAnalyzer.analyze` with a NaN RSHOULDER on
    the last flight frame must produce `total_rotation_deg`,
    `rotation_count`, and `under_rotation_deg` metrics with FINITE values, NOT
    NaN. `analyze` (line 369) calls `compute_total_rotation_from_poses` and
    packs the result into `MetricResult(name="total_rotation_deg", ...)` (line
    389) and `MetricResult(name="rotation_count", ...)` (line 397); then
    `under_rotation_deg = compute_under_rotation(total_rotation_deg,
    target_rotations)` (line 417) = `target_deg - NaN` = NaN → packed into
    `MetricResult(name="under_rotation_deg", value=NaN)`. A NaN shoulder →
    three NaN metrics → the recommender → the report JSON → GOE proxy.

    RED now: NaN RSHOULDER on flight frame 6 → `total_rotation_deg` = NaN,
    `rotation_count` = NaN, `under_rotation_deg` = NaN. After the fix: finite
    values for all three metrics.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    poses = _poses()
    poses[6, H36Key.RSHOULDER] = [np.nan, np.nan]

    results = an.analyze(poses, _phases(), fps=30.0)
    by_name = {r.name: r for r in results}

    for name in ("total_rotation_deg", "rotation_count", "under_rotation_deg"):
        assert name in by_name, (
            f"BUG: analyze() did not produce a `{name}` metric; the metric "
            f"name or the analyze() output changed — update the repro fixture."
        )
        assert np.isfinite(by_name[name].value), (
            f"BUG: analyze() `{name}` metric value = {by_name[name].value} "
            f"(NaN) for a NaN RSHOULDER on the last flight frame 6. `analyze` "
            f"(line 369) calls `compute_total_rotation_from_poses` → (NaN, "
            f"NaN) → packed into `total_rotation_deg` (line 389) and "
            f"`rotation_count` (line 397); then `under_rotation_deg = "
            f"compute_under_rotation(total_rotation_deg, target_rotations)` "
            f"(line 417) = `target_deg - NaN` = NaN. Three NaN metrics flow "
            f"into the recommender → the report JSON → the GOE proxy. "
            f"`rotation_count` is the PRIMARY jump identifier — the report "
            f"becomes a NaN hole where the jump type should be. The user gets "
            f"a NaN hole in the report instead of a degraded-but-finite "
            f"estimate. This is the real prod-impact path (NaN metrics in the "
            f"report / a NaN GOE), not just an internal-metric NaN."
        )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid poses still produce finite positive total
# rotation / count / under-rotation.
# --------------------------------------------------------------------------- #


def test_all_valid_total_rotation_unchanged_repro():
    """Regression guard: all-valid poses must still produce finite positive
    total rotation / count / under-rotation. The fix (NaN guard / NaN-mask /
    0.0 sentinel) must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the all-valid case.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    deg, cnt = an.compute_total_rotation_from_poses(_poses(), _phases(), fps=30.0)
    assert np.isfinite(deg) and deg > 0.0 and np.isfinite(cnt) and cnt > 0.0, (
        f"BUG (regression): all-valid total rotation ({deg}, {cnt}) is "
        f"non-finite or non-positive; expected finite > 0. The no-NaN case "
        f"must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — compute_total_rotation_from_poses uses
# np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0]) + np.unwrap(angles)
# unguarded; compute_total_rotation uses abs(unwrapped[-1] - unwrapped[0])
# unguarded. NO NaN guard in either.
# --------------------------------------------------------------------------- #


def test_total_rotation_nan_leak_source_repro():
    """Source check: `compute_total_rotation_from_poses` computes the
    shoulder-axis angle with unguarded `np.arctan2(shoulder_vector[:, 1],
    shoulder_vector[:, 0])` and `np.unwrap(angles)`, and `compute_total_rotation`
    returns `abs(shoulder_angles_unwrapped[-1] - shoulder_angles_unwrapped[0])`
    (unguarded, line 1586). NO NaN guard in either. Root cause locked.

    RED now: the unguarded `np.arctan2` + `np.unwrap` + `abs(...[-1] - ...[0])`
    are present (PASS — root cause locked). After the fix: a NaN guard /
    `np.isnan` / `np.isfinite` / NaN-mask appears in
    `compute_total_rotation_from_poses` OR `compute_total_rotation` — this test
    FAILS, signaling the observable tests above should flip to GREEN.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_total_rotation_from_poses)
    # The unguarded np.arctan2 shoulder-axis angle + np.unwrap are present.
    assert "np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])" in src, (
        "BUG: compute_total_rotation_from_poses must compute "
        f"`np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])` "
        f"(unguarded, line 1217) for this repro to be valid. If a NaN guard was "
        f"added before the arctan2, the NaN-leak is fixed — update the "
        f"observable tests to the GREEN contract."
    )
    assert "np.unwrap(angles)" in src, (
        "BUG: compute_total_rotation_from_poses must `np.unwrap(angles)` "
        "(unguarded, line 1218) for this repro to be valid. If a NaN guard was "
        "added before/after the unwrap, the NaN-leak is fixed — update the "
        "observable tests to the GREEN contract."
    )
    assert "np.isnan" not in src and "np.isfinite" not in src and \
           "np.nan_to_num" not in src, (
        "BUG: a NaN guard (`np.isnan` / `np.isfinite` / `np.nan_to_num`) "
        "appeared in compute_total_rotation_from_poses — the NaN-leak is "
        "fixed; update the observable tests to the GREEN contract."
    )

    tot_src = inspect.getsource(compute_total_rotation)
    # The unguarded abs(unwrapped[-1] - unwrapped[0]) return is present.
    assert "shoulder_angles_unwrapped[-1] - shoulder_angles_unwrapped[0]" in tot_src, (
        "BUG: compute_total_rotation must return "
        "`abs(shoulder_angles_unwrapped[-1] - shoulder_angles_unwrapped[0])` "
        "(unguarded, line 1586) for this repro to be valid. If it was changed "
        "to a NaN-guarded form, the NaN-leak is fixed — update the observable "
        "tests to the GREEN contract."
    )
    assert "np.isnan" not in tot_src and "np.isfinite" not in tot_src and \
           "np.nan_to_num" not in tot_src, (
        "BUG: a NaN guard (`np.isnan` / `np.isfinite` / `np.nan_to_num`) "
        "appeared in compute_total_rotation — the NaN-leak is fixed; update "
        "the observable tests to the GREEN contract."
    )

    # The degenerate-phases guard exists (returns 0.0, 0.0) — proves the
    # codebase already uses a 0.0 sentinel for degenerate input, so a NaN
    # sentinel fits the same pattern.
    assert "return 0.0, 0.0" in src, (
        "BUG: compute_total_rotation_from_poses must guard "
        "`if phases.takeoff >= phases.landing or phases.landing >= len(poses): "
        "return 0.0, 0.0` (degenerate-phases sentinel) for this repro to be "
        "valid. If the guard was removed, the repro is invalid."
    )