"""RED repro — `BiomechanicsAnalyzer.compute_jump_height_com` computes the
CoM-based jump height as `takeoff_com - peak_com`, where
`peak_com = np.min(flight_com)` over the flight-phase CoM slice. The CoM
trajectory (`calculate_com_trajectory`) is a weighted sum of ALL 17 keypoint
Y-coordinates; a NaN keypoint on ANY flight frame makes the CoM NaN for that
frame, `flight_com` has NaN, `np.min(flight_com) = nan` (NumPy propagates NaN),
`takeoff_com - nan = nan`, and the method returns `nan` (NaN-leak, not a
clamped false-best/worst — tranche BS).

`compute_jump_height_com` (ml/src/analysis/metrics.py:755-798):

    com_trajectory = calculate_com_trajectory(poses)
    if phases.takeoff >= phases.landing:
        return 0.0
    takeoff_com = com_trajectory[phases.takeoff]
    flight_com = com_trajectory[phases.takeoff : phases.landing + 1]
    peak_com = np.min(flight_com)
    return float(takeoff_com - peak_com)

`calculate_com_trajectory` (geometry.py:287-335) — weighted sum of all 17
keypoint Y-coordinates. Any NaN keypoint → `com_y[frame] = nan`.

When a keypoint is NaN on a flight frame (takeoff < frame <= landing):
  - `com_trajectory[frame] = nan` (one NaN term poisons the weighted sum)
  - `flight_com = com_trajectory[takeoff : landing + 1]` has NaN
  - `peak_com = np.min(flight_com) = nan`  ← NumPy min propagates NaN (not
    `np.nanmin` which would skip NaN)
  - `takeoff_com - nan = nan`  (or `nan - nan = nan` if takeoff frame is NaN)
  - `return float(nan) = nan`  ← NaN-leak

`analyze()` (metrics.py:202-211) emits `max_height` with `value=height` —
`is_good=False` is hardcoded, `reference_range=(0,0)`, so the `is_good` gate
is unaffected; but `value=nan` breaks downstream:
  1. **JSON serialization**: NaN is not valid JSON (RFC 8259). `json.dumps`
     with default `allow_nan=True` emits `NaN` (non-standard, strict parsers
     reject). Frontend / API consumers may fail to parse, or render
     `nan`/`null`/error.
  2. **Recommender**: the rule-based recommender consumes `max_height` for
     jump-quality text; `nan` propagates through comparisons (`nan > x` is
     always False) → wrong branch → wrong recommendation.
  3. **Frontend display**: charts/reports showing `max_height` render `nan`
     or crash.

Note: `compute_jump_height_com` is NOT in the GOE composite (`compute_goe_score`
uses `compute_relative_jump_height`, a sibling method — covered by tranche BP,
issue #875). So this is a NaN-leak into a user-facing metric, not a GOE
inflation. But it is the SAME root cause: `calculate_com_trajectory` plain
weighted sum + `np.min` (not nanmin) + no NaN guard on the return.

Reproduced (12 frames, fps=30, waltz_jump; takeoff=2, landing=7; parabolic
flight arc `Y -= 0.02*(f-2)*(7-f)` → CoM rises in flight → valid height ≈ 0.156
norm):

    all-valid parabolic flight          → height = 0.156  (finite, correct)
    NaN RKNEE on flight frames 3..6     → height = nan    (BUG: NaN-leak)
    NaN RWRIST on flight frames 3..6   → height = nan    (BUG: any keypoint)

Consequences (prod impact — max_height is user-facing, displayed in reports):
  1. `analyze()` (metrics.py:202-211) emits `max_height` with `value=nan`.
     NaN is not valid JSON — breaks strict parsers, frontend, recommender.
  2. The CoM-weighted-sum means the bug triggers on NaN in ANY of the 17
     keypoints on ANY flight frame — wide blast radius, same as BM/BN/BP/BQ/BR.
  3. Existing tests miss it: `test_compute_jump_height_com*` feed all-valid
     keypoints. No test feeds a NaN keypoint through the CoM into the
     `np.min(flight_com)` peak. The `np.min` (not nanmin) NaN-propagation is
     not exercised on this method.

The fix (NOT applied — repro only): make the metric NaN-aware. Either:
  - mask NaN before the min: `finite = flight_com[np.isfinite(flight_com)]`;
    `if len(finite) == 0: return 0.0`; `peak_com = np.min(finite)`; or
  - use `np.nanmin(flight_com)` (NaN-safe min over the finite frames) and a
    NaN guard on the result (`if not np.isfinite(peak_com): return 0.0`); and
  - guard the return: `height = takeoff_com - peak_com; if not
    np.isfinite(height): return 0.0`.
  - The deeper fix is in `calculate_com_trajectory` (NaN-aware CoM — mask NaN
    keypoints, renormalize masses over valid keypoints per frame), which
    fixes every CoM-based metric (smoothness BM, hard_landing BN,
    relative_jump_height BP, toe_assist BQ, approach_direction_change BR,
    jump_height_com BS, peak_com) at once.

The correct contract: a NaN keypoint on a flight frame must NOT leak NaN
into the `max_height` value. The metric must skip the NaN frames (`np.nanmin`
/ NaN mask / sentinel) and return a finite height (or 0.0 "no data"), NOT nan.

RED now: the observable assertions below describe the CORRECT behavior — a
flight with one occluded keypoint must return a FINITE height (close to the
all-valid value, or 0.0 / a neutral sentinel), NOT `nan`. They FAIL because
`np.min([..., nan, ...]) = nan` then `takeoff_com - nan = nan`. After the
fix: the NaN frames are skipped and the value is finite. The source-check
test confirms the `peak_com = np.min(flight_com)` (not nanmin) + unguarded
`return float(takeoff_com - peak_com)` lines are present (root cause locked).

Pure-Python (no GPU, no DB): `compute_jump_height_com` and
`calculate_com_trajectory` are pure-data functions over a poses array.
"""

import inspect

import numpy as np

from src.analysis.element_defs import ELEMENT_DEFS
from src.analysis.metrics import BiomechanicsAnalyzer
from src.utils.geometry import calculate_com_trajectory
from src.types import ElementPhase, H36Key


def _flight_pose(nan_keypoint: str | None = None, n: int = 12) -> np.ndarray:
    """A 12-frame pose sequence with a parabolic flight arc — CoM rises (Y
    decreases) during flight (frames 2..7) via `Y -= 0.02*(f-2)*(7-f)`, peaking
    mid-flight, so the all-valid jump height is finite nonzero (~0.156 norm).

    When `nan_keypoint` is set, that keypoint is NaN on the flight frames
    (3..6) — the occlusion case. `calculate_com_trajectory` is a weighted sum
    over all 17 keypoints, so one NaN keypoint makes the CoM NaN for those
    frames → `flight_com` has NaN → `np.min(flight_com) = nan` →
    `takeoff_com - nan = nan` → method returns nan.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.HEAD] = [0.0, 0.0]
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.1]
        poses[f, H36Key.RSHOULDER] = [0.2, 0.1]
        poses[f, H36Key.LHIP] = [-0.1, 0.5]
        poses[f, H36Key.RHIP] = [0.1, 0.5]
        poses[f, H36Key.LKNEE] = [-0.1, 0.9]
        poses[f, H36Key.RKNEE] = [0.1, 0.9]
        poses[f, H36Key.LFOOT] = [-0.1, 1.0]
        poses[f, H36Key.RFOOT] = [0.1, 1.0]
    # Parabolic flight arc: CoM rises (Y decreases) during frames 2..7.
    for f in range(2, 8):
        poses[f, :, 1] -= 0.02 * (f - 2) * (7 - f)
    if nan_keypoint:
        kp = {"rknee": H36Key.RKNEE, "rwrist": H36Key.RWRIST,
              "lfoot": H36Key.LFOOT}[nan_keypoint]
        # NaN on flight frames (3..6) — inside the takeoff:landing+1 slice.
        for f in range(3, 7):
            poses[f, kp] = [np.nan, np.nan]
    return poses


def _phases(n: int = 12):
    return ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=4,
                        landing=7, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: a flight with one occluded keypoint must return a FINITE
# jump height (graceful degradation), NOT nan.
# --------------------------------------------------------------------------- #


def test_nan_knee_jump_height_com_is_finite_repro():
    """CORRECT behavior: a flight with ONE occluded knee keypoint on the
    flight frames must return a FINITE jump height — skip the NaN frames
    (`np.nanmin` / NaN mask) and report the peak from the valid frames, close
    to the all-valid value, or 0.0 / a neutral sentinel. It must NOT return
    `nan` (a NaN-leak that breaks JSON serialization, the recommender, and
    frontend display of `max_height`).

    RED now: `RKNEE` NaN on flight frames 3..6 → `calculate_com_trajectory`
    is a weighted sum over all 17 keypoints, so the CoM of those frames is NaN
    → `flight_com = com_trajectory[takeoff:landing+1]` has NaN →
    `peak_com = np.min(flight_com) = nan` (NumPy min propagates NaN, not
    `np.nanmin`) → `takeoff_com - nan = nan` → method returns `nan`. After
    the fix: the NaN frames are skipped and the value is finite.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])

    # Baseline: all-valid parabolic flight → finite nonzero height.
    h_valid = analyzer.compute_jump_height_com(_flight_pose(None), _phases())
    assert np.isfinite(h_valid) and h_valid > 0.0, (
        f"test fixture broken: all-valid parabolic flight reported height "
        f"{h_valid}, expected finite > 0. The fixture needs a parabolic flight "
        f"arc (`Y -= 0.02*(f-2)*(7-f)`) so the CoM rises in flight and the "
        f"all-valid baseline is nonzero finite — otherwise the NaN-vs-valid "
        f"contrast is meaningless."
    )

    # One occluded knee on flight frames — same flight, one NaN keypoint.
    h_nan = analyzer.compute_jump_height_com(_flight_pose("rknee"), _phases())

    # CORRECT contract: the occluded-keypoint height must be FINITE (graceful
    # NaN-skip / 0.0 sentinel), NOT nan — a NaN-leak breaks JSON, recommender,
    # frontend display of `max_height`.
    assert np.isfinite(h_nan), (
        f"BUG: compute_jump_height_com returned {h_nan} (nan) for a parabolic "
        f"flight (all-valid height = {h_valid:.4f}) with a NaN RKNEE on the "
        f"flight frames (occlusion). `calculate_com_trajectory` is a weighted "
        f"sum over ALL 17 keypoints, so one NaN keypoint makes the CoM NaN for "
        f"those frames; `flight_com = com_trajectory[takeoff:landing+1]` has "
        f"NaN; `peak_com = np.min(flight_com) = nan` (NumPy min propagates NaN, "
        f"not np.nanmin); `takeoff_com - nan = nan`. The method returns nan — "
        f"a NaN-leak into the `max_height` MetricResult value (metrics.py:202-"
        f"211). NaN is not valid JSON (RFC 8259), breaks strict parsers, the "
        f"recommender (nan > x is always False → wrong branch), and frontend "
        f"display. (Sanity: all-valid height = {h_valid:.4f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint (CoM weighted sum),
# not just the knee — a NaN wrist also leaks nan.
# --------------------------------------------------------------------------- #


def test_nan_wrist_jump_height_com_is_finite_repro():
    """CORRECT behavior: a flight with one occluded WRIST on the flight frames
    must also return a finite height. The CoM weighted sum includes the arms
    (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist poisons the CoM the
    same way as a NaN knee. The bug has a wide blast radius — ANY of the 17
    keypoints, same as BM/BN/BP/BQ/BR.

    RED now: `RWRIST` NaN → CoM NaN → `np.min(flight_com) = nan` →
    `takeoff_com - nan = nan`. After the fix: graceful degradation on any
    occluded keypoint.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    h_nan = analyzer.compute_jump_height_com(_flight_pose("rwrist"), _phases())

    assert np.isfinite(h_nan), (
        f"BUG: compute_jump_height_com returned {h_nan} (nan) for a parabolic "
        f"flight with a NaN RWRIST on the flight frames. The CoM weighted sum "
        f"includes the arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist "
        f"poisons the CoM the same way as a NaN knee. The bug has a wide blast "
        f"radius — ANY of the 17 keypoints, not just the knee. A fix that only "
        f"guards the knee (or only the legs) would leave the arm/head keypoints "
        f"broken. The root-cause fix is NaN-aware CoM "
        f"(`calculate_com_trajectory`) or `np.nanmin` on `flight_com`."
    )


# --------------------------------------------------------------------------- #
# Observable 3: occluding LKNEE vs RKNEE must give the same jump height —
# symmetric in which side is occluded.
# --------------------------------------------------------------------------- #


def test_nan_knee_jump_height_com_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE on the flight frames must
    give the same jump height — both poison the CoM weighted sum identically
    (one NaN term). The metric must be symmetric in which side is occluded.

    RED now: both give `nan` (symmetric today, both NaN-leak). This is a
    regression guard that PASSES today only after the fix (both finite and
    equal). It locks the symmetry contract so a fix that only handles one
    side does not pass.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    poses_r = _flight_pose("rknee")
    poses_l = _flight_pose(None)
    for f in range(3, 7):
        poses_l[f, H36Key.LKNEE] = [np.nan, np.nan]

    h_right_nan = analyzer.compute_jump_height_com(poses_r, _phases())
    h_left_nan = analyzer.compute_jump_height_com(poses_l, _phases())

    # Both must be finite (the fix) AND equal — symmetric in which side.
    assert np.isfinite(h_right_nan) and np.isfinite(h_left_nan), (
        f"BUG (symmetry): occluding LKNEE/RKNEE gives non-finite jump heights "
        f"({h_left_nan} vs {h_right_nan}). Both must be finite (graceful NaN-"
        f"skip) before the symmetry contract can be checked."
    )
    assert abs(h_right_nan - h_left_nan) < 1e-3, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different jump heights "
        f"({h_left_nan:.4f} vs {h_right_nan:.4f}). Both poison the CoM weighted "
        f"sum identically (one NaN term) — the metric must be symmetric in "
        f"which side is occluded. A fix that only handles one side would break "
        f"this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid parabolic flight still reports finite, nonzero.
# --------------------------------------------------------------------------- #


def test_all_valid_jump_height_com_unchanged_repro():
    """Regression guard: an all-valid parabolic flight must still report a
    finite, nonzero jump height. The fix (nanmin / NaN mask / NaN-aware CoM)
    must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    h = analyzer.compute_jump_height_com(_flight_pose(None), _phases())
    assert np.isfinite(h) and h > 0.0, (
        f"BUG (regression): all-valid parabolic flight reported height {h}, "
        f"expected finite > 0. The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — np.min(flight_com) (not nanmin) + unguarded
# return float(takeoff_com - peak_com).
# --------------------------------------------------------------------------- #


def test_jump_height_com_nan_unsafe_source_repro():
    """Source check: `compute_jump_height_com` computes
    `peak_com = np.min(flight_com)` (NOT `np.nanmin` — propagates NaN) and
    `return float(takeoff_com - peak_com)` (no NaN guard on the return). Root
    cause locked.

    RED now: the `np.min(flight_com)` line and the unguarded
    `return float(takeoff_com - peak_com)` line are present (PASS — root cause
    locked). After the fix: the min becomes `np.nanmin` (or a NaN mask /
    sentinel) and/or the return guards NaN — this test FAILS, signaling the
    observable tests above should flip to GREEN.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_jump_height_com)
    # The np.min (NOT nanmin) line is present — propagates NaN.
    assert "peak_com = np.min(flight_com)" in src, (
        "BUG: compute_jump_height_com must compute "
        "`peak_com = np.min(flight_com)` (NaN-propagating, not `np.nanmin`) "
        "for this repro to be valid. If it was changed to `np.nanmin(flight_com)` "
        "(or a NaN mask), the NaN-leak bug is fixed — update the observable "
        "tests to the GREEN contract."
    )
    assert "np.nanmin" not in src, (
        "BUG: compute_jump_height_com now uses `np.nanmin` — the NaN-leak bug "
        "is fixed; update the observable tests to the GREEN contract."
    )
    # The unguarded return line is present.
    assert "return float(takeoff_com - peak_com)" in src, (
        "BUG: compute_jump_height_com must compute "
        "`return float(takeoff_com - peak_com)` (no NaN guard) for this repro "
        "to be valid. If a NaN guard was added (e.g. "
        "`if not np.isfinite(peak_com): return 0.0`), the NaN-leak bug is "
        "fixed — update the observable tests to the GREEN contract."
    )
    assert "np.isfinite" not in src and "np.isnan" not in src, (
        "BUG: a NaN guard (`np.isfinite` / `np.isnan`) appeared in "
        "compute_jump_height_com — the NaN-leak bug is fixed; update the "
        "observable tests to the GREEN contract."
    )

    # And the CoM trajectory is a plain weighted sum (no NaN masking) —
    # proving a NaN keypoint poisons the CoM. Same root cause as BM/BN/BP/BQ/BR.
    com_src = inspect.getsource(calculate_com_trajectory)
    assert "np.isnan" not in com_src and "np.isfinite" not in com_src and \
        "nanmean" not in com_src and "nansum" not in com_src, (
        "BUG: calculate_com_trajectory now has a NaN-aware path "
        "(np.isnan / np.isfinite / nanmean / nansum) — the CoM NaN-propagation "
        "bug is fixed at the source; update the observable tests to the GREEN "
        "contract. (This would also fix every CoM-based metric — smoothness BM, "
        "hard_landing BN, relative_jump_height BP, toe_assist BQ, "
        "approach_direction_change BR — at once.)"
    )