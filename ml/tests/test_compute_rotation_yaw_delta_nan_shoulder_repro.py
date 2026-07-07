"""RED repro — `BiomechanicsAnalyzer.compute_rotation_yaw_delta` (3D yaw
cross-check, metrics.py:1454-1467) returns false-BAD `(0.0, 0.0)` when the
shoulder keypoint is NaN (occlusion). Issue #915.

Root cause (metrics.py:1454-1467):

    shoulder_length = np.linalg.norm(r_sho - l_sho, axis=1)   # NaN -> NaN
    median_length = np.median(shoulder_length)                # NaN (np.median,
                                                              #   NOT np.nanmedian)
    if median_length < 1e-6:                                  # NaN<1e-6 = False
                                                              #   -> guard SKIPS
        return 0.0, 0.0, ...
    valid = shoulder_length > 0.05 * median_length            # NaN>NaN = all-False
    if not np.all(valid):
        valid_idx = np.where(valid)[0]                        # empty
        if len(valid_idx) < 2:                                # 0<2 -> false-BAD
            return 0.0, 0.0, ...

`np.median` of a NaN-containing array is NaN (NaN propagates), `NaN < 1e-6`
is False (NaN comparison) so the degenerate-length guard does NOT fire, and
`NaN > 0.05*NaN` is all-False so `valid_idx` is empty and the `< 2` branch
returns the `(0.0, 0.0)` sentinel. The metric confuses "no data" (NaN
occlusion) with "no rotation" (0.0).

Consumer path (metrics.py:392-397, `_analyze_jump`):

    yaw_total, yaw_count, clamped = compute_rotation_yaw_delta(...)
    discrepancy = abs(rotation_count - yaw_count)   # abs(0.955 - 0) = 0.955
    rotation_discrepancy = discrepancy > 0.5         # True
    if rotation_discrepancy and clamped.sum() < 3:
        rotation_count = yaw_count                   # 0.0 — false-BAD OVERRIDE
        total_rotation_deg = abs(yaw_total)          # 0.0

A valid 2D `rotation_count` (~0.955 for a triple) is OVERWRITTEN by the
NaN-poisoned 3D yaw `0.0`. The 3D cross-check — designed to CORRECT the 2D
count — instead DESTROYS it on a single NaN shoulder. The Axel is reported
as "0 rotations".

The fix (NOT applied — repro only): NaN-shoulder must NOT false-zero. Use
`np.nanmedian` (NaN-ignored median) so a few NaN frames don't poison the
median, AND guard `median_length` with `np.isfinite` so an all-NaN shoulder
returns a NaN sentinel instead of 0.0. The consumer's
`abs(rotation_count - nan) > 0.5` is False (NaN comparison) -> the override
is skipped and the valid 2D `rotation_count` is preserved. Mirrors #966
classify_jump isfinite guard.

The correct contract: `compute_rotation_yaw_delta` with a NaN shoulder must
NOT return `(0.0, 0.0)` — it must return a NaN sentinel (flag occlusion,
not false-zero) so the consumer does not override a valid 2D count.

RED now: the observable assertions below describe the CORRECT behavior —
NaN shoulder returns non-zero / NaN, not false-BAD 0.0. They FAIL because
`np.median(NaN) < 1e-6` skips the guard and `valid_idx` is empty ->
`(0.0, 0.0)`. The source-check confirms the `nanmedian` + `isfinite` guard
is present (root cause locked).

Pure-Python (no GPU, no DB): `compute_rotation_yaw_delta` is a pure-data
staticmethod over a 3D poses array.
"""

import inspect

import numpy as np

from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import H36Key


def _flight_poses_3d(n_flight: int = 20, n_rotations: float = 3.0) -> np.ndarray:
    """A (n_flight, 17, 3) 3D pose sequence with rotating shoulders so the
    yaw cross-check computes a nonzero rotation. LSHOULDER/RSHOULDER rotate
    around Z (depth) across frames — yaw = arctan2(rz-lz, rx-lx) sweeps as
    frames progress. `n_rotations=3.0` models a triple jump (1080°).
    """
    poses = np.zeros((n_flight, 17, 3), dtype=np.float32)
    for f in range(n_flight):
        ang = f * (n_rotations * 2 * np.pi / n_flight)  # n_rotations over the flight
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.1, 0.0]
        poses[f, H36Key.RSHOULDER] = [0.2 * np.cos(ang), 0.1, 0.2 * np.sin(ang)]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: NaN RSHOULDER on a flight frame -> NOT false-BAD (0.0, 0.0).
# The 3D yaw cross-check must not destroy the rotation count on occlusion.
# --------------------------------------------------------------------------- #


def test_nan_shoulder_yaw_delta_not_false_zero_repro():
    """CORRECT behavior: NaN RSHOULDER on a flight frame must NOT yield the
    false-BAD `(0.0, 0.0)` sentinel. Either a NaN sentinel (occlusion
    flagged, consumer skips override) or a finite non-zero count
    (interpolated from finite neighbors) is acceptable; 0.0 is NOT.

    RED now: `np.median(NaN) = NaN`, `NaN < 1e-6` = False skips the guard,
    `NaN > 0.05*NaN` = all-False empties valid_idx -> `(0.0, 0.0)` false-BAD.
    """
    poses = _flight_poses_3d()
    poses[3, H36Key.RSHOULDER] = np.nan  # occlusion on flight frame 3
    flight = np.arange(poses.shape[0])
    total_deg, rot_count, _ = BiomechanicsAnalyzer.compute_rotation_yaw_delta(
        poses, flight, fps=30.0
    )
    assert not (rot_count == 0.0 and np.isfinite(rot_count)), (
        f"BUG: NaN RSHOULDER on frame 3 -> false-BAD (0.0, 0.0). got "
        f"total={total_deg!r}, count={rot_count!r}. NaN occlusion must NOT "
        f"zero the rotation count — return NaN sentinel (consumer skips "
        f"override) or interpolate from finite neighbors."
    )


# --------------------------------------------------------------------------- #
# Observable 2: all-NaN shoulder (both LSHOULDER + RSHOULDER every frame) ->
# NaN sentinel, NOT false-BAD 0.0. Blast radius: full occlusion still must
# not be confused with "no rotation".
# --------------------------------------------------------------------------- #


def test_nan_any_shoulder_yaw_delta_not_false_zero_repro():
    """CORRECT behavior: all-NaN shoulders (LSHOULDER + RSHOULDER every
    flight frame) must return a NaN sentinel, NOT the false-BAD `(0.0, 0.0)`.

    RED now: `np.median(all-NaN) = NaN`, guard skipped, `valid_idx` empty ->
    `(0.0, 0.0)` false-BAD. The consumer then overrides a valid 2D count
    with 0.0.
    """
    poses = _flight_poses_3d()
    poses[:, H36Key.LSHOULDER] = np.nan
    poses[:, H36Key.RSHOULDER] = np.nan
    flight = np.arange(poses.shape[0])
    total_deg, rot_count, _ = BiomechanicsAnalyzer.compute_rotation_yaw_delta(
        poses, flight, fps=30.0
    )
    assert not (rot_count == 0.0 and np.isfinite(rot_count)), (
        f"BUG: all-NaN shoulders -> false-BAD (0.0, 0.0). got total="
        f"{total_deg!r}, count={rot_count!r}. Full occlusion must be "
        f"flagged as NaN (consumer skips override), not false-zero."
    )


# --------------------------------------------------------------------------- #
# Observable 3: NaN hip but finite shoulder -> finite result, not false-zero.
# Hip is not used by the yaw math (only shoulders), so a NaN hip must not
# poison the count. Locks that the guard is on the shoulder path only.
# --------------------------------------------------------------------------- #


def test_nan_hip_finite_shoulder_yaw_delta_finite_repro():
    """CORRECT behavior: NaN hip (RHIP/LHIP) with finite shoulders must
    yield a finite non-zero rotation_count. The yaw math uses only
    LSHOULDER/RSHOULDER, so a NaN hip must not leak into the count.

    PASSES today (regression guard): locks that the fix targets the
    shoulder path, not the hip path.
    """
    poses = _flight_poses_3d()
    poses[:, H36Key.LHIP] = np.nan
    poses[:, H36Key.RHIP] = np.nan
    flight = np.arange(poses.shape[0])
    total_deg, rot_count, _ = BiomechanicsAnalyzer.compute_rotation_yaw_delta(
        poses, flight, fps=30.0
    )
    assert np.isfinite(total_deg) and np.isfinite(rot_count), (
        f"BUG: NaN hip with finite shoulders leaked non-finite total="
        f"{total_deg!r}, count={rot_count!r}. Hip is not used by the yaw "
        f"math — guard must be on the shoulder path only."
    )
    assert rot_count != 0.0, f"BUG: NaN hip with finite shoulders false-zeroed count={rot_count!r}."


# --------------------------------------------------------------------------- #
# Regression guard: all-finite poses unchanged — known rotation_count
# reproduced. The fix must not regress the valid path.
# --------------------------------------------------------------------------- #


def test_all_valid_yaw_delta_unchanged_repro():
    """Regression guard: all-finite poses must still report a finite,
    nonzero rotation_count. The nanmedian/isfinite guard must not change the
    valid case. PASSES today; locks the contract so the guard cannot
    regress the normal path.
    """
    poses = _flight_poses_3d()
    flight = np.arange(poses.shape[0])
    total_deg, rot_count, _ = BiomechanicsAnalyzer.compute_rotation_yaw_delta(
        poses, flight, fps=30.0
    )
    assert np.isfinite(total_deg) and np.isfinite(rot_count), (
        f"BUG (regression): all-finite should report finite rotation, got "
        f"total={total_deg!r}, count={rot_count!r}."
    )
    assert rot_count != 0.0, (
        f"BUG (regression): all-finite should report nonzero rotation, got count={rot_count!r}."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `np.nanmedian` + `np.isfinite` guard at
# the shoulder-length trust boundary.
# --------------------------------------------------------------------------- #


def test_compute_rotation_yaw_delta_nan_false_zero_source_repro():
    """GREEN contract source check: the false-BAD 0.0 is fixed by
    `np.nanmedian(shoulder_length)` (NaN-ignored median) AND an
    `np.isfinite(median_length)` guard at the shoulder-length trust
    boundary. All-NaN shoulder -> NaN sentinel (not 0.0) -> consumer's
    `abs(rotation_count - nan) > 0.5` is False -> 2D count preserved.
    Mirrors #966 classify_jump isfinite guard.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_rotation_yaw_delta)
    assert "np.nanmedian" in src, (
        "BUG: compute_rotation_yaw_delta must use `np.nanmedian(shoulder_length)` "
        "(NOT np.median) so a few NaN shoulder frames don't poison the median. "
        "np.median(NaN) = NaN -> NaN<1e-6 = False skips the guard -> false-BAD 0.0."
    )
    assert "np.isfinite(median_length)" in src or ("isfinite(median_length)" in src), (
        "BUG: compute_rotation_yaw_delta must guard `median_length` with "
        "`np.isfinite` — all-NaN shoulder -> nanmedian=NaN -> return NaN "
        "sentinel (not 0.0) so the consumer does not override a valid 2D "
        "rotation_count with false-zero."
    )
