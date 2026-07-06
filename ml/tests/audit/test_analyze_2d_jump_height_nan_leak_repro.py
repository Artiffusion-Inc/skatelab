"""RED repro — `PhysicsEngine.analyze_2d` computes the jump height from the
2D CoM trajectory over the flight phase:

    com = calculate_com_trajectory_2d(poses_2d)
    flight_com_y = com[takeoff_idx : landing_idx + 1, 1]
    jump_height = float(np.max(flight_com_y) - np.min(flight_com_y))

`calculate_com_trajectory_2d` (geometry.py:388-435) is a weighted sum of ALL
17 keypoint (x, y) coordinates. A NaN keypoint on a flight frame makes the
CoM NaN for that frame → `flight_com_y` has NaN → `np.max(flight_com_y) = nan`
(NumPy max propagates NaN) → `np.min(flight_com_y) = nan` → `nan - nan = nan`
→ `jump_height = nan` (NaN-leak, not a clamped value — tranche BV).

`analyze_2d` (ml/src/analysis/physics_engine.py:596-680):

    com = calculate_com_trajectory_2d(poses_2d)
    if takeoff_idx is not None and landing_idx is not None:
        flight_frames = landing_idx - takeoff_idx + 1
        flight_time = flight_frames / fps
        flight_com_y = com[takeoff_idx : landing_idx + 1, 1]
        jump_height = float(np.max(flight_com_y) - np.min(flight_com_y))
        if takeoff_idx > 0:
            dt = 1.0 / fps
            takeoff_velocity_y = float((com[takeoff_idx, 1] - com[takeoff_idx - 1, 1]) / dt)
            takeoff_velocity = abs(takeoff_velocity_y)
        try:
            t_flight = np.arange(flight_frames) / fps
            coeffs = np.polyfit(t_flight, flight_com_y, 2)
            ...
        except (np.linalg.LinAlgError, ValueError):
            fit_quality = 0.0
    return {"jump_height": jump_height, "flight_time": flight_time,
            "takeoff_velocity": takeoff_velocity, "fit_quality": fit_quality,
            "avg_inertia": None}

`pipeline.py:370` calls `engine.analyze_2d(...)` and stores the result in
`physics_dict`, which flows into `AnalysisReport(physics=physics_dict)`
(pipeline.py:423). The outer `try/except Exception` (pipeline.py:374) does
NOT catch the NaN-leak — `analyze_2d` returns normally (no exception), so
`physics_dict["jump_height"] = nan` reaches the report.

Consequences (prod impact — `jump_height` is a top-level physics result,
serialized into the analysis report):
  1. `physics_dict["jump_height"] = nan` → `AnalysisReport.physics["jump_height"]
     = nan`. NaN is not valid JSON (RFC 8259) — `json.dumps` with default
     `allow_nan=True` emits `NaN` (non-standard, strict parsers reject).
     Frontend / API consumers may fail to parse, or render `nan`/`null`/error.
  2. The CoM-weighted-sum means the bug triggers on NaN in ANY of the 17
     keypoints on ANY flight frame — wide blast radius, same as BM/BN/BP/BQ/
     BR/BS/BT. The landing-leg knee is frequently occluded in figure skating.
  3. `takeoff_velocity` is also NaN-leaked when the takeoff or takeoff-1
     frame has a NaN keypoint (backward difference through the CoM).
  4. `fit_quality` is mostly guarded (`np.polyfit` raises on NaN → except →
     `fit_quality = 0.0`), but `jump_height` is computed BEFORE the try/except
     and is NOT guarded.
  5. Existing tests miss it: `test_analyze_2d_jump_height_landing_drop_repro.py`
     (a sibling tranche) feeds all-valid keypoints. No test feeds a NaN
     keypoint through the 2D CoM into `np.max(flight_com_y) - np.min(...)`.
     The `np.max`/`np.min` NaN-propagation is not exercised on this path.

The fix (NOT applied — repro only): make `analyze_2d` NaN-aware. Either:
  - mask NaN before the height: `finite = flight_com_y[np.isfinite(flight_com_y)]`;
    `if len(finite) == 0: jump_height = 0.0`; else
    `jump_height = float(np.max(finite) - np.min(finite))`; or
  - use `np.nanmax(flight_com_y) - np.nanmin(flight_com_y)` (NaN-safe max/min)
    and a NaN guard on the result (`if not np.isfinite(jump_height):
    jump_height = 0.0`); and
  - guard `takeoff_velocity`: `if not np.isfinite(takeoff_velocity):
    takeoff_velocity = 0.0`.
  - The deeper fix is in `calculate_com_trajectory_2d` (NaN-aware CoM — mask
    NaN keypoints, renormalize masses over valid keypoints per frame), which
    fixes every CoM-based metric (smoothness BM, hard_landing BN,
    relative_jump_height BP, toe_assist BQ, approach_direction_change BR,
    jump_height_com BS, landing_com_velocity BT, analyze_2d jump_height BV)
    at once.

The correct contract: a NaN keypoint on a flight frame must NOT leak NaN into
`analyze_2d`'s `jump_height` (or `takeoff_velocity`). The metric must skip the
NaN frames (`np.nanmax`/`np.nanmin` / NaN mask / 0.0 sentinel) and return a
finite height, NOT nan.

RED now: the observable assertions below describe the CORRECT behavior — a
flight with one occluded keypoint must return a FINITE `jump_height` (close to
the all-valid value, or 0.0 / a neutral sentinel), NOT `nan`. They FAIL
because `np.max([..., nan, ...]) = nan` then `nan - nan = nan`. After the fix:
the NaN frames are skipped and the value is finite. The source-check test
confirms the `np.max(flight_com_y) - np.min(flight_com_y)` (not nanmax/nanmin)
line and the unguarded `takeoff_velocity` backward-diff line are present
(root cause locked).

Pure-Python (no GPU, no DB): `analyze_2d` and `calculate_com_trajectory_2d`
are pure-data functions over a poses array.
"""

import inspect

import numpy as np

from src.analysis.physics_engine import PhysicsEngine
from src.utils.geometry import calculate_com_trajectory_2d
from src.types import H36Key


def _flight_pose_2d(nan_keypoint: str | None = None, n: int = 12) -> np.ndarray:
    """A 12-frame 2D pose sequence with a parabolic flight arc — CoM rises (Y
    decreases) during flight (frames 2..7) via `Y -= 0.02*(f-2)*(7-f)`, so the
    all-valid `jump_height = max - min` is finite nonzero (~0.14 norm).

    When `nan_keypoint` is set, that keypoint is NaN on the flight frames
    (3..6) — the occlusion case. `calculate_com_trajectory_2d` is a weighted
    sum over all 17 keypoints, so one NaN keypoint makes the CoM NaN for those
    frames → `flight_com_y` has NaN → `np.max(flight_com_y) = nan` →
    `np.min = nan` → `jump_height = nan`.
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


# --------------------------------------------------------------------------- #
# Observable 1: a flight with one occluded keypoint must return a FINITE
# jump_height (graceful degradation), NOT nan.
# --------------------------------------------------------------------------- #


def test_nan_knee_analyze_2d_jump_height_is_finite_repro():
    """CORRECT behavior: a 2D flight with ONE occluded knee keypoint on the
    flight frames must return a FINITE `jump_height` — skip the NaN frames
    (`np.nanmax`/`np.nanmin` / NaN mask) and report the height from the valid
    frames, close to the all-valid value, or 0.0 / a neutral sentinel. It
    must NOT return `nan` (a NaN-leak that breaks JSON serialization of the
    analysis report and frontend display of `jump_height`).

    RED now: `RKNEE` NaN on flight frames 3..6 →
    `calculate_com_trajectory_2d` is a weighted sum over all 17 keypoints, so
    the CoM of those frames is NaN → `flight_com_y = com[tk:ld+1, 1]` has NaN
    → `np.max(flight_com_y) = nan` (NumPy max propagates NaN, not nanmax) →
    `np.min(flight_com_y) = nan` → `nan - nan = nan` → `jump_height = nan`.
    `pipeline.py:370` stores this in `physics_dict`, which reaches
    `AnalysisReport(physics=...)` (pipeline.py:423) — the outer try/except
    does NOT catch it (no exception). After the fix: the NaN frames are
    skipped and the value is finite.
    """
    engine = PhysicsEngine()

    # Baseline: all-valid parabolic flight → finite nonzero jump_height.
    r_valid = engine.analyze_2d(_flight_pose_2d(None), takeoff_idx=2,
                                landing_idx=7, fps=30.0)
    assert np.isfinite(r_valid["jump_height"]) and r_valid["jump_height"] > 0.0, (
        f"test fixture broken: all-valid parabolic flight reported jump_height "
        f"{r_valid['jump_height']}, expected finite > 0. The fixture needs a "
        f"parabolic flight arc (`Y -= 0.02*(f-2)*(7-f)`) so the CoM rises in "
        f"flight and the all-valid baseline is nonzero finite — otherwise the "
        f"NaN-vs-valid contrast is meaningless."
    )

    # One occluded knee on flight frames — same flight, one NaN keypoint.
    r_nan = engine.analyze_2d(_flight_pose_2d("rknee"), takeoff_idx=2,
                              landing_idx=7, fps=30.0)

    # CORRECT contract: the occluded-keypoint jump_height must be FINITE
    # (graceful NaN-skip / 0.0 sentinel), NOT nan — a NaN-leak breaks JSON
    # serialization of the analysis report and frontend display.
    assert np.isfinite(r_nan["jump_height"]), (
        f"BUG: PhysicsEngine.analyze_2d returned jump_height={r_nan['jump_height']} "
        f"(nan) for a parabolic flight (all-valid = {r_valid['jump_height']:.4f}) "
        f"with a NaN RKNEE on the flight frames (occlusion). "
        f"`calculate_com_trajectory_2d` is a weighted sum over ALL 17 keypoints, "
        f"so one NaN keypoint makes the CoM NaN for those frames; "
        f"`flight_com_y = com[tk:ld+1, 1]` has NaN; `np.max(flight_com_y) = nan` "
        f"(NumPy max propagates NaN, not np.nanmax); `np.min = nan`; "
        f"`nan - nan = nan` → jump_height = nan. `pipeline.py:370` stores this "
        f"in `physics_dict` → `AnalysisReport(physics=...)` (pipeline.py:423) — "
        f"the outer try/except does NOT catch it (no exception). NaN is not "
        f"valid JSON (RFC 8259), breaks strict parsers and frontend display of "
        f"`jump_height`. (Sanity: all-valid = {r_valid['jump_height']:.4f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint (CoM weighted sum),
# not just the knee — a NaN wrist also leaks nan.
# --------------------------------------------------------------------------- #


def test_nan_wrist_analyze_2d_jump_height_is_finite_repro():
    """CORRECT behavior: a 2D flight with one occluded WRIST on the flight
    frames must also return a finite `jump_height`. The CoM weighted sum
    includes the arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist
    poisons the CoM the same way as a NaN knee. The bug has a wide blast
    radius — ANY of the 17 keypoints, same as BM/BN/BP/BQ/BR/BS/BT.

    RED now: `RWRIST` NaN → CoM NaN → `np.max(nan)=nan` → `jump_height=nan`.
    After the fix: graceful degradation on any occluded keypoint.
    """
    engine = PhysicsEngine()
    r_nan = engine.analyze_2d(_flight_pose_2d("rwrist"), takeoff_idx=2,
                              landing_idx=7, fps=30.0)

    assert np.isfinite(r_nan["jump_height"]), (
        f"BUG: PhysicsEngine.analyze_2d returned jump_height={r_nan['jump_height']} "
        f"(nan) for a parabolic flight with a NaN RWRIST on the flight frames. "
        f"The CoM weighted sum includes the arms (r_forearm = (RELBOW + RWRIST) / "
        f"2), so a NaN wrist poisons the CoM the same way as a NaN knee. The bug "
        f"has a wide blast radius — ANY of the 17 keypoints, not just the knee. "
        f"A fix that only guards the knee (or only the legs) would leave the "
        f"arm/head keypoints broken. The root-cause fix is NaN-aware CoM "
        f"(`calculate_com_trajectory_2d`) or `np.nanmax`/`np.nanmin` on "
        f"`flight_com_y`."
    )


# --------------------------------------------------------------------------- #
# Observable 3: occluding LKNEE vs RKNEE must give the same jump_height —
# symmetric in which side is occluded.
# --------------------------------------------------------------------------- #


def test_nan_knee_analyze_2d_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE on the flight frames must
    give the same `jump_height` — both poison the CoM weighted sum identically
    (one NaN term). The metric must be symmetric in which side is occluded.

    RED now: both give `nan` (symmetric today, both NaN-leak). This is a
    regression guard that PASSES today only after the fix (both finite and
    equal). It locks the symmetry contract so a fix that only handles one
    side does not pass.
    """
    engine = PhysicsEngine()
    poses_r = _flight_pose_2d("rknee")
    poses_l = _flight_pose_2d(None)
    for f in range(3, 7):
        poses_l[f, H36Key.LKNEE] = [np.nan, np.nan]

    r_right = engine.analyze_2d(poses_r, takeoff_idx=2, landing_idx=7, fps=30.0)
    r_left = engine.analyze_2d(poses_l, takeoff_idx=2, landing_idx=7, fps=30.0)

    # Both must be finite (the fix) AND equal — symmetric in which side.
    assert np.isfinite(r_right["jump_height"]) and np.isfinite(r_left["jump_height"]), (
        f"BUG (symmetry): occluding LKNEE/RKNEE gives non-finite jump_height "
        f"({r_left['jump_height']} vs {r_right['jump_height']}). Both must be "
        f"finite (graceful NaN-skip) before the symmetry contract can be checked."
    )
    assert abs(r_right["jump_height"] - r_left["jump_height"]) < 1e-3, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different jump_height "
        f"({r_left['jump_height']:.4f} vs {r_right['jump_height']:.4f}). Both "
        f"poison the CoM weighted sum identically (one NaN term) — the metric "
        f"must be symmetric in which side is occluded. A fix that only handles "
        f"one side would break this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid parabolic flight still reports finite, nonzero.
# --------------------------------------------------------------------------- #


def test_all_valid_analyze_2d_jump_height_unchanged_repro():
    """Regression guard: an all-valid parabolic flight must still report a
    finite, nonzero `jump_height`. The fix (nanmax/nanmin / NaN mask /
    NaN-aware CoM) must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    engine = PhysicsEngine()
    r = engine.analyze_2d(_flight_pose_2d(None), takeoff_idx=2, landing_idx=7,
                          fps=30.0)
    assert np.isfinite(r["jump_height"]) and r["jump_height"] > 0.0, (
        f"BUG (regression): all-valid parabolic flight reported jump_height "
        f"{r['jump_height']}, expected finite > 0. The no-NaN case must be "
        f"unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — np.max - np.min (not nanmax/nanmin) +
# unguarded takeoff_velocity backward diff.
# --------------------------------------------------------------------------- #


def test_analyze_2d_jump_height_nan_unsafe_source_repro():
    """Source check: `analyze_2d` computes
    `jump_height = float(np.max(flight_com_y) - np.min(flight_com_y))` (NOT
    `np.nanmax`/`np.nanmin` — propagates NaN) and the unguarded
    `takeoff_velocity_y = float((com[takeoff_idx, 1] - com[takeoff_idx - 1, 1]) / dt)`.
    Root cause locked.

    RED now: the `np.max(flight_com_y) - np.min(flight_com_y)` line and the
    unguarded backward-diff line are present (PASS — root cause locked). After
    the fix: the max/min becomes `np.nanmax`/`np.nanmin` (or a NaN mask /
    sentinel) and/or the backward-diff guards NaN — this test FAILS,
    signaling the observable tests above should flip to GREEN.
    """
    src = inspect.getsource(PhysicsEngine.analyze_2d)
    # The np.max - np.min (NOT nanmax/nanmin) line is present — propagates NaN.
    assert "jump_height = float(np.max(flight_com_y) - np.min(flight_com_y))" in src, (
        "BUG: analyze_2d must compute "
        "`jump_height = float(np.max(flight_com_y) - np.min(flight_com_y))` "
        "(NaN-propagating, not `np.nanmax`/`np.nanmin`) for this repro to be "
        "valid. If it was changed to `np.nanmax(...) - np.nanmin(...)` (or a "
        "NaN mask), the NaN-leak bug is fixed — update the observable tests to "
        "the GREEN contract."
    )
    assert "np.nanmax" not in src and "np.nanmin" not in src, (
        "BUG: analyze_2d now uses `np.nanmax`/`np.nanmin` — the NaN-leak bug is "
        "fixed; update the observable tests to the GREEN contract."
    )
    # The unguarded takeoff_velocity backward-diff line is present.
    assert "takeoff_velocity_y = float((com[takeoff_idx, 1] - com[takeoff_idx - 1, 1]) / dt)" in src, (
        "BUG: analyze_2d must compute the unguarded backward diff "
        "`takeoff_velocity_y = float((com[takeoff_idx, 1] - com[takeoff_idx - 1, 1]) / dt)` "
        "for this repro to be valid. If a NaN guard was added on "
        "`takeoff_velocity`, the NaN-leak bug is fixed — update the observable "
        "tests to the GREEN contract."
    )
    assert "np.isfinite" not in src and "np.isnan" not in src, (
        "BUG: a NaN guard (`np.isfinite` / `np.isnan`) appeared in analyze_2d — "
        "the NaN-leak bug is fixed; update the observable tests to the GREEN "
        "contract."
    )

    # And the 2D CoM trajectory is a plain weighted sum (no NaN masking) —
    # proving a NaN keypoint poisons the CoM. Same root cause as BM/BN/BP/BQ/
    # BR/BS/BT.
    com_src = inspect.getsource(calculate_com_trajectory_2d)
    assert "np.isnan" not in com_src and "np.isfinite" not in com_src and \
        "nanmean" not in com_src and "nansum" not in com_src, (
        "BUG: calculate_com_trajectory_2d now has a NaN-aware path "
        "(np.isnan / np.isfinite / nanmean / nansum) — the CoM NaN-propagation "
        "bug is fixed at the source; update the observable tests to the GREEN "
        "contract. (This would also fix every CoM-based metric — smoothness BM, "
        "hard_landing BN, relative_jump_height BP, toe_assist BQ, "
        "approach_direction_change BR, jump_height_com BS, landing_com_velocity "
        "BT — at once.)"
    )