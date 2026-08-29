"""RED repro — `PhysicsEngine.fit_jump_trajectory` fits a parabola to the
CoM Y trajectory during flight:

    com_trajectory = self.calculate_center_of_mass(poses_3d)
    flight_com = com_trajectory[takeoff_idx : landing_idx + 1, 1]
    ...
    try:
        params, _ = curve_fit(parabola, t, flight_com)
        ...
    except Exception:
        return {"height": np.max(flight_com) - np.min(flight_com), ...}

`calculate_center_of_mass` (physics_engine.py) is a weighted sum of ALL 17
keypoint (x, y, z) coordinates — same shape as `calculate_com_trajectory`
(geometry.py) and `calculate_com_trajectory_2d`. A NaN keypoint on a flight
frame makes the CoM NaN for that frame → `flight_com` has NaN →
`curve_fit` raises (NaN in data) → `except Exception` fallback →
`np.max(flight_com) - np.min(flight_com)` = `nan - nan = nan` (NumPy max/min
propagate NaN, not nanmax/nanmin) → method returns `height=nan` (NaN-leak,
not a clamped false-best/worst — tranche BW).

`fit_jump_trajectory` (ml/src/analysis/physics_engine.py:463-545) is a PUBLIC
method (separate path from `analyze_2d`, which is tranche BV, issue #883). It
is the sibling of `_fit_jump_trajectory_with_com` (used by `analyze`, the 3D
path). `fit_jump_trajectory` computes its own CoM via
`self.calculate_center_of_mass(poses_3d)` then calls `curve_fit` on the
flight slice; the `except Exception` fallback (`np.max - np.min`, NOT
nanmax/nanmin) is the NaN-leak path.

Consequences (prod impact — `fit_jump_trajectory` is a public physics API,
returns `height` in meters, used for jump-quality reporting):
  1. `height = nan` flows into any caller that consumes the return dict. NaN
     is not valid JSON (RFC 8259) — `json.dumps` with default
     `allow_nan=True` emits `NaN` (non-standard, strict parsers reject).
     Frontend / API consumers may fail to parse, or render `nan`/`null`/error.
  2. The CoM-weighted-sum means the bug triggers on NaN in ANY of the 17
     keypoints on ANY flight frame — wide blast radius, same as BM/BN/BP/BQ/
     BR/BS/BT/BV. The landing-leg knee is frequently occluded in figure
     skating.
  3. `takeoff_velocity` and `fit_quality` are guarded in the fallback
     (`0.0`), but `height` is the NaN-leak — `np.max(flight_com) -
     np.min(flight_com)` is computed BEFORE any guard.
  4. Existing tests miss it: `test_fit_jump_trajectory*` feed all-valid
     keypoints. No test feeds a NaN keypoint through the 3D CoM into the
     `curve_fit` except-fallback `np.max - np.min`. The `np.max`/`np.min`
     NaN-propagation is not exercised on the fallback path.

The fix (NOT applied — repro only): make the fallback NaN-aware. Either:
  - mask NaN before the height: `finite = flight_com[np.isfinite(flight_com)]`;
    `if len(finite) == 0: height = 0.0`; else
    `height = float(np.max(finite) - np.min(finite))`; or
  - use `np.nanmax(flight_com) - np.nanmin(flight_com)` (NaN-safe max/min) and a
    NaN guard on the result (`if not np.isfinite(height): height = 0.0`).
  - Also guard the curve_fit path: when `flight_com` has NaN, `curve_fit`
    raises, but a NaN-aware fit (`np.polyfit` with masked data, or skip NaN)
    would use the valid frames instead of the crude max-min fallback.
  - The deeper fix is in `calculate_center_of_mass` (NaN-aware CoM — mask NaN
    keypoints, renormalize masses over valid keypoints per frame), which
    fixes every CoM-based metric at once.

The correct contract: a NaN keypoint on a flight frame must NOT leak NaN into
`fit_jump_trajectory`'s `height`. The method must skip the NaN frames
(`np.nanmax`/`np.nanmin` / NaN mask / 0.0 sentinel) and return a finite
height, NOT nan.

RED now: the observable assertions below describe the CORRECT behavior — a
flight with one occluded keypoint must return a FINITE `height` (close to the
all-valid value, or 0.0 / a neutral sentinel), NOT `nan`. They FAIL because
`curve_fit` raises on NaN → fallback `np.max([..., nan, ...]) = nan` then
`nan - nan = nan`. After the fix: the NaN frames are skipped and the value is
finite. The source-check test confirms the `np.max(flight_com) -
np.min(flight_com)` (not nanmax/nanmin) fallback line and the unguarded CoM
weighted sum are present (root cause locked).

Pure-Python (no GPU, no DB): `fit_jump_trajectory` and
`calculate_center_of_mass` are pure-data functions over a poses array.
"""

import inspect

import numpy as np

from src.analysis.physics_engine import PhysicsEngine
from src.types import H36Key


def _flight_pose_3d(nan_keypoint: str | None = None, n: int = 12) -> np.ndarray:
    """A 12-frame 3D pose sequence with a parabolic flight arc — CoM rises (Y
    decreases) during flight (frames 2..7) via `Y -= 0.02*(f-2)*(7-f)`, so the
    all-valid `height` from the parabola fit is finite nonzero (~0.125 m).

    When `nan_keypoint` is set, that keypoint is NaN on the flight frames
    (3..6) — the occlusion case. `calculate_center_of_mass` is a weighted sum
    over all 17 keypoints, so one NaN keypoint makes the CoM NaN for those
    frames → `flight_com` has NaN → `curve_fit` raises → except-fallback →
    `np.max(flight_com) - np.min(flight_com) = nan` → `height = nan`.
    """
    poses = np.zeros((n, 17, 3), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.HEAD] = [0.0, 0.0, 0.0]
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.1, 0.0]
        poses[f, H36Key.RSHOULDER] = [0.2, 0.1, 0.0]
        poses[f, H36Key.LHIP] = [-0.1, 0.5, 0.0]
        poses[f, H36Key.RHIP] = [0.1, 0.5, 0.0]
        poses[f, H36Key.LKNEE] = [-0.1, 0.9, 0.0]
        poses[f, H36Key.RKNEE] = [0.1, 0.9, 0.0]
        poses[f, H36Key.LFOOT] = [-0.1, 1.0, 0.0]
        poses[f, H36Key.RFOOT] = [0.1, 1.0, 0.0]
    # Parabolic flight arc: CoM rises (Y decreases) during frames 2..7.
    for f in range(2, 8):
        poses[f, :, 1] -= 0.02 * (f - 2) * (7 - f)
    if nan_keypoint:
        kp = {"rknee": H36Key.RKNEE, "rwrist": H36Key.RWRIST, "lfoot": H36Key.LFOOT}[nan_keypoint]
        # NaN on flight frames (3..6) — inside the takeoff:landing+1 slice.
        for f in range(3, 7):
            poses[f, kp] = [np.nan, np.nan, np.nan]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: a flight with one occluded keypoint must return a FINITE
# height (graceful degradation), NOT nan.
# --------------------------------------------------------------------------- #


def test_nan_knee_fit_jump_trajectory_height_is_finite_repro():
    """CORRECT behavior: a 3D flight with ONE occluded knee keypoint on the
    flight frames must return a FINITE `height` — skip the NaN frames
    (`np.nanmax`/`np.nanmin` / NaN mask) and report the height from the valid
    frames, close to the all-valid value, or 0.0 / a neutral sentinel. It must
    NOT return `nan` (a NaN-leak that breaks JSON serialization and frontend
    display of jump `height`).

    RED now: `RKNEE` NaN on flight frames 3..6 →
    `calculate_center_of_mass` is a weighted sum over all 17 keypoints, so
    the CoM of those frames is NaN → `flight_com = com[tk:ld+1, 1]` has NaN →
    `curve_fit(parabola, t, flight_com)` raises (NaN in data) → `except
    Exception` fallback → `np.max(flight_com) = nan` (NumPy max propagates
    NaN, not np.nanmax) → `np.min = nan` → `nan - nan = nan` → `height = nan`.
    After the fix: the NaN frames are skipped and the value is finite.
    """
    engine = PhysicsEngine()

    # Baseline: all-valid parabolic flight → finite nonzero height.
    r_valid = engine.fit_jump_trajectory(_flight_pose_3d(None), 2, 7, 30.0)
    assert np.isfinite(r_valid["height"]) and r_valid["height"] > 0.0, (
        f"test fixture broken: all-valid parabolic flight reported height "
        f"{r_valid['height']}, expected finite > 0. The fixture needs a "
        f"parabolic flight arc (`Y -= 0.02*(f-2)*(7-f)`) so the CoM rises in "
        f"flight and the all-valid baseline is nonzero finite — otherwise the "
        f"NaN-vs-valid contrast is meaningless."
    )

    # One occluded knee on flight frames — same flight, one NaN keypoint.
    r_nan = engine.fit_jump_trajectory(_flight_pose_3d("rknee"), 2, 7, 30.0)

    # CORRECT contract: the occluded-keypoint height must be FINITE (graceful
    # NaN-skip / 0.0 sentinel), NOT nan — a NaN-leak breaks JSON serialization
    # and frontend display of jump `height`.
    assert np.isfinite(r_nan["height"]), (
        f"BUG: PhysicsEngine.fit_jump_trajectory returned height={r_nan['height']} "
        f"(nan) for a parabolic flight (all-valid = {r_valid['height']:.4f}) "
        f"with a NaN RKNEE on the flight frames (occlusion). "
        f"`calculate_center_of_mass` is a weighted sum over ALL 17 keypoints, "
        f"so one NaN keypoint makes the CoM NaN for those frames; "
        f"`flight_com = com[tk:ld+1, 1]` has NaN; `curve_fit(parabola, t, "
        f"flight_com)` raises (NaN in data); `except Exception` fallback → "
        f"`np.max(flight_com) = nan` (NumPy max propagates NaN, not np.nanmax); "
        f"`np.min = nan`; `nan - nan = nan` → height = nan. NaN is not valid "
        f"JSON (RFC 8259), breaks strict parsers and frontend display of jump "
        f"`height`. (Sanity: all-valid = {r_valid['height']:.4f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint (CoM weighted sum),
# not just the knee — a NaN wrist also leaks nan.
# --------------------------------------------------------------------------- #


def test_nan_wrist_fit_jump_trajectory_height_is_finite_repro():
    """CORRECT behavior: a 3D flight with one occluded WRIST on the flight
    frames must also return a finite `height`. The CoM weighted sum includes
    the arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist poisons the
    CoM the same way as a NaN knee. The bug has a wide blast radius — ANY of
    the 17 keypoints, same as BM/BN/BP/BQ/BR/BS/BT/BV.

    RED now: `RWRIST` NaN → CoM NaN → curve_fit raises → fallback
    `np.max(nan)=nan` → `height=nan`. After the fix: graceful degradation on
    any occluded keypoint.
    """
    engine = PhysicsEngine()
    r_nan = engine.fit_jump_trajectory(_flight_pose_3d("rwrist"), 2, 7, 30.0)

    assert np.isfinite(r_nan["height"]), (
        f"BUG: PhysicsEngine.fit_jump_trajectory returned height={r_nan['height']} "
        f"(nan) for a parabolic flight with a NaN RWRIST on the flight frames. "
        f"The CoM weighted sum includes the arms (r_forearm = (RELBOW + RWRIST) / "
        f"2), so a NaN wrist poisons the CoM the same way as a NaN knee. The bug "
        f"has a wide blast radius — ANY of the 17 keypoints, not just the knee. "
        f"A fix that only guards the knee (or only the legs) would leave the "
        f"arm/head keypoints broken. The root-cause fix is NaN-aware CoM "
        f"(`calculate_center_of_mass`) or `np.nanmax`/`np.nanmin` on the "
        f"`flight_com` fallback."
    )


# --------------------------------------------------------------------------- #
# Observable 3: occluding LKNEE vs RKNEE must give the same height —
# symmetric in which side is occluded.
# --------------------------------------------------------------------------- #


def test_nan_knee_fit_jump_trajectory_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE on the flight frames must
    give the same `height` — both poison the CoM weighted sum identically
    (one NaN term). The metric must be symmetric in which side is occluded.

    RED now: both give `nan` (symmetric today, both NaN-leak). This is a
    regression guard that PASSES today only after the fix (both finite and
    equal). It locks the symmetry contract so a fix that only handles one
    side does not pass.
    """
    engine = PhysicsEngine()
    poses_r = _flight_pose_3d("rknee")
    poses_l = _flight_pose_3d(None)
    for f in range(3, 7):
        poses_l[f, H36Key.LKNEE] = [np.nan, np.nan, np.nan]

    r_right = engine.fit_jump_trajectory(poses_r, 2, 7, 30.0)
    r_left = engine.fit_jump_trajectory(poses_l, 2, 7, 30.0)

    # Both must be finite (the fix) AND equal — symmetric in which side.
    assert np.isfinite(r_right["height"]) and np.isfinite(r_left["height"]), (
        f"BUG (symmetry): occluding LKNEE/RKNEE gives non-finite height "
        f"({r_left['height']} vs {r_right['height']}). Both must be finite "
        f"(graceful NaN-skip) before the symmetry contract can be checked."
    )
    assert abs(r_right["height"] - r_left["height"]) < 1e-3, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different height "
        f"({r_left['height']:.4f} vs {r_right['height']:.4f}). Both poison the "
        f"CoM weighted sum identically (one NaN term) — the metric must be "
        f"symmetric in which side is occluded. A fix that only handles one "
        f"side would break this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid parabolic flight still reports finite, nonzero.
# --------------------------------------------------------------------------- #


def test_all_valid_fit_jump_trajectory_height_unchanged_repro():
    """Regression guard: an all-valid parabolic flight must still report a
    finite, nonzero `height`. The fix (nanmax/nanmin / NaN mask / NaN-aware
    CoM) must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    engine = PhysicsEngine()
    r = engine.fit_jump_trajectory(_flight_pose_3d(None), 2, 7, 30.0)
    assert np.isfinite(r["height"]) and r["height"] > 0.0, (
        f"BUG (regression): all-valid parabolic flight reported height "
        f"{r['height']}, expected finite > 0. The no-NaN case must be "
        f"unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — np.max - np.min fallback (not nanmax/
# nanmin) + unguarded CoM weighted sum.
# --------------------------------------------------------------------------- #


def test_fit_jump_trajectory_nan_unsafe_source_repro():
    """GREEN contract source check: the NaN-leak bug is fixed in BOTH places.

    `fit_jump_trajectory`'s except-fallback computes height from a NaN-safe
    finite mask (not the NaN-propagating `np.max(flight_com) - np.min(...)`)
    and guards the result. `calculate_center_of_mass` masks NaN keypoints so
    an occluded joint cannot poison the CoM (the source-level fix that
    repairs every 3D CoM-based metric).
    """
    src = inspect.getsource(PhysicsEngine.fit_jump_trajectory)
    # The except-fallback uses a NaN-safe finite mask, not NaN-propagating
    # np.max(flight_com) - np.min(flight_com).
    assert "np.isfinite(flight_com)" in src and "np.max(finite_com) - np.min(finite_com)" in src, (
        "BUG: fit_jump_trajectory's except-fallback must compute height from a "
        "finite mask of the flight CoM so a fully-occluded frame cannot leak "
        "NaN (#884)."
    )
    assert "np.isfinite(fallback_height)" in src, (
        "BUG: fit_jump_trajectory's except-fallback must guard the fallback "
        "height against a non-finite result (#884)."
    )

    # And the 3D CoM (`calculate_center_of_mass`) is NaN-aware — masking NaN
    # keypoints so an occluded joint cannot poison the CoM. Same root cause as
    # BM/BN/BP/BQ/BR/BS/BT/BV.
    com_src = inspect.getsource(PhysicsEngine.calculate_center_of_mass)
    assert "np.isfinite" in com_src, (
        "BUG: calculate_center_of_mass must mask NaN keypoints (np.isfinite) "
        "so a single occluded joint cannot NaN-poison the CoM and leak into "
        "fit_jump_trajectory height."
    )
