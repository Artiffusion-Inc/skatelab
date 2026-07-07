"""RED repro — `count_rotations` / `_compute_flight_rotations` ValueError
crash on NaN shoulder (tranche EO).

`_compute_flight_rotations` (phase_detector.py:46-66) builds the shoulder
orientation vector `right_shoulder - left_shoulder`, runs `np.arctan2` →
angles, then `count_rotations(angles)`. NaN LSHOULDER (idx 11) / RSHOULDER
(idx 14) on ANY flight frame (occluded shoulder — common in rotations /
crossovers / fast jumps) → `shoulder_vector = NaN` → `np.arctan2(NaN) =
NaN` (silent, no exception) → `np.unwrap(NaN array) = NaN` →
`total_radians = NaN` → `int(np.ceil(NaN))` (line 43) →
`ValueError: cannot convert float NaN to integer`.

Crash on the LAST line of `count_rotations` — far from the NaN source, no
intermediate signal. `np.arctan2(NaN)` and `np.unwrap(NaN)` return NaN
silently; only `int(NaN)` raises. `count_rotations` is called for EVERY
jump element (phase_detector detect_phases line 304) → one occluded
shoulder aborts the whole jump-level classification (waltz/double/triple/
quad — PRIMARY classification).

Sibling consistency: NaN-propagation family. `compute_total_rotation`
in metrics.py (DIFFERENT function — total rotation DEGREES via metric
path, NOT rotation COUNT via `count_rotations`) is covered by
`test_total_rotation_nan_shoulder_leak_repro`. `count_rotations` in
phase_detector.py is a separate code path with a separate
`int(np.ceil(NaN))` crash — genuine sibling, not covered.

The fix (NOT applied — repro only): guard `count_rotations` top-of-fn —
`if not np.isfinite(total_radians): return 0`. NaN shoulder → 0
rotations (NOT a crash), mirroring the existing `len(angles) < 2 → 0`
degenerate-input guard at line 31. Root-cause fix at the divide site; all
callers (`_compute_flight_rotations`, any future caller) protected.

Contract: NaN shoulder in flight window must NOT crash `count_rotations`
with `int(np.ceil(NaN))` ValueError. Must return a finite int (0 —
unknown rotation count, NOT crash). Mirrors the existing
`len(angles) < 2 → return 0` degenerate-input graceful-return design.

RED now: observable assertions describe CORRECT behavior — NaN angles →
finite int return, no ValueError. They FAIL because `int(np.ceil(NaN))`
raises. The source-check confirms the `np.isfinite` guard is present
(root cause locked).

Pure-Python (no GPU, no DB): `count_rotations` / `_compute_flight_rotations`
are pure-numpy functions on pose arrays — testable with synthetic NaN
shoulder poses.
"""

import inspect

import numpy as np

from src.analysis.phase_detector import _compute_flight_rotations, count_rotations

# --------------------------------------------------------------------------- #
# Observable 1: count_rotations(NaN angles) — no ValueError, returns finite int.
# --------------------------------------------------------------------------- #


def test_count_rotations_nan_angles_no_crash_repro():
    """CORRECT behavior: `count_rotations(angles)` with NaN in the angle
    array (NaN shoulder → np.arctan2(NaN) → NaN angle) must return a
    finite int (0 — unknown rotation count), NOT raise
    `ValueError: cannot convert float NaN to integer`.

    RED now: `int(np.ceil(NaN))` (line 43) raises ValueError. After the
    fix: `if not np.isfinite(total_radians): return 0` → 0.
    """
    angles = np.array([0.0, np.nan, 0.0, 0.0])
    result = count_rotations(angles)
    assert isinstance(result, int) and np.isfinite(result), (
        f"BUG: count_rotations(NaN angles) did not return a finite int (got "
        f"{type(result).__name__}: {result!r}). int(np.ceil(NaN)) raises "
        f"ValueError — one occluded shoulder aborts jump-level classification."
    )


# --------------------------------------------------------------------------- #
# Observable 2: all-NaN angles — same finite int, no crash.
# --------------------------------------------------------------------------- #


def test_count_rotations_all_nan_angles_no_crash_repro():
    """CORRECT behavior: `count_rotations` on an all-NaN angle array (both
    shoulders NaN across the whole flight window) must return a finite
    int, NOT crash. Locks the degenerate edge.
    """
    angles = np.array([np.nan, np.nan, np.nan])
    result = count_rotations(angles)
    assert isinstance(result, int) and np.isfinite(result), (
        "BUG: count_rotations(all-NaN angles) crashed. int(np.ceil(NaN)) "
        "ValueError; both-shoulders-NaN flight window must return 0."
    )


# --------------------------------------------------------------------------- #
# Observable 3: _compute_flight_rotations(NaN shoulder) — no crash, finite int.
# The real prod path: occluded LSHOULDER/RSHOULDER on a flight frame.
# --------------------------------------------------------------------------- #


def test_compute_flight_rotations_nan_shoulder_no_crash_repro():
    """CORRECT behavior: `_compute_flight_rotations` with a NaN shoulder
    (LSHOULDER idx 11 / RSHOULDER idx 14) on a flight frame must return a
    finite int rotation count, NOT raise ValueError. This is the prod
    path: occluded shoulder in rotations/crossovers/fast jumps.

    RED now: shoulder_vector = NaN → np.arctan2(NaN) = NaN →
    count_rotations → int(np.ceil(NaN)) ValueError → PhaseDetector.
    detect_phases raise → whole pipeline `analyze` raise. After the fix:
    0 rotations.
    """
    poses = np.zeros((20, 17, 2), dtype=np.float32)
    # Valid shoulders on most frames, NaN LSHOULDER on one flight frame.
    poses[:, 11, :] = [0.4, 0.3]  # LSHOULDER
    poses[:, 14, :] = [0.6, 0.3]  # RSHOULDER
    poses[10, 11, :] = np.nan  # occluded LSHOULDER mid-flight
    result = _compute_flight_rotations(poses, takeoff_idx=5, landing_idx=15)
    assert isinstance(result, int) and np.isfinite(result), (
        f"BUG: _compute_flight_rotations(NaN shoulder) crashed (got "
        f"{type(result).__name__}: {result!r}). Occluded shoulder mid-flight "
        f"→ int(np.ceil(NaN)) ValueError → pipeline abort."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid angles unchanged — finite nonzero for real rotation.
# --------------------------------------------------------------------------- #


def test_count_rotations_valid_angles_unchanged_repro():
    """Regression guard: a 2-full-turn (4pi rad) angle trajectory must
    return 2. The NaN guard must not change the valid-finite case. PASSES
    today; locks the contract.
    """
    # 0 → 4pi (two full turns, unwrapped).
    angles = np.linspace(0.0, 4.0 * np.pi, 50)
    result = count_rotations(angles)
    assert result == 2, (
        f"BUG (regression): a 2-full-turn trajectory must give 2, got "
        f"{result!r}. The NaN guard must not change the valid-finite case."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — np.isfinite guard at the divide site.
# --------------------------------------------------------------------------- #


def test_count_rotations_nan_guard_source_repro():
    """GREEN contract source check: the NaN-shoulder crash is fixed by a
    `np.isfinite(total_radians)` guard at the divide site in
    `count_rotations` (before `int(np.ceil(...))`), returning 0 on NaN —
    mirroring the existing `len(angles) < 2 → return 0` degenerate-input
    graceful-return design. Root-cause fix; all callers protected.
    """
    src = inspect.getsource(count_rotations)
    assert "np.isfinite" in src, (
        "BUG: count_rotations must guard `if not np.isfinite(total_radians): "
        "return 0` before `int(np.ceil(...))` (line 43). NaN shoulder → "
        "np.arctan2(NaN) → np.unwrap(NaN) → total_radians=NaN → "
        "int(np.ceil(NaN)) ValueError. Mirror the len(angles)<2 → 0 guard."
    )
