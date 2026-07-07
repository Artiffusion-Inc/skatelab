"""RED repro -> GREEN after fix: `BiomechanicsAnalyzer._analyze_spin`
(metrics.py:665) `mean_velocity = float(np.mean(angular_velocity)) if
len(angular_velocity) > 0 else 0.0` silently propagates NaN into
`classify_spin(angular_velocity_mean=mean_velocity, ...)` when any
shoulder keypoint is NaN on a spin frame. Issue #1328 (tranche MT).

Root cause (metrics.py:601-607):

    shoulder_vector = right_shoulder - left_shoulder   # NaN-array if either
                                                       # shoulder is NaN
    angles = np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])
    unwrapped = np.unwrap(angles)
    angular_velocity = np.abs(np.gradient(unwrapped) * fps) * (180.0 / np.pi)
    ...
    # #912 only guards `unwrapped` (for compute_total_rotation path) and
    # aggregates peak via np.nanmax. mean_velocity at line 665 is a bare
    # np.mean(angular_velocity) — numpy mean is NOT NaN-aware.
    mean_velocity = float(np.mean(angular_velocity)) if len(angular_velocity) > 0 else 0.0

NaN in either shoulder -> `shoulder_vector` NaN -> `np.arctan2(NaN, x) = NaN`
-> `np.unwrap(NaN) = NaN` -> `np.gradient(NaN) = NaN` -> `angular_velocity`
carries NaN frames. `np.mean(NaN_array) = NaN` (numpy mean is not NaN-aware,
unlike np.nanmean). The `len(angular_velocity) > 0` guard catches empty
arrays but does NOT catch NaN frames in a non-empty array.

`classify_spin` (spin_classifier.py:42-47) has an isfinite guard that returns
`("unknown", 0.0)` when any input is NaN — so the BUG is silent: NaN mean
silently degrades spin_type to "unknown"/0.0 (wrong branch under
NaN-comparison) instead of "no data" sentinel. The metric value
`spin_type` (the 0.0 confidence) flows into the GOE composite, biomech
report, and recommender.

Fix (NOT applied — repro only): guard `mean_velocity` with
`math.isfinite(angular_velocity).all()` filter, or use `np.nanmean` +
`np.isfinite` fallback (mirrors #912 peak_velocity path with np.nanmax +
isfinite), at the same trust boundary. ponytail: fix the root cause ONCE
on the inline `angular_velocity` series (so mean and any future sibling
consumer inherit the guard), not a one-line `if isnan(mean_velocity):
0.0` after the fact. The existing #912 guard on `unwrapped` (line 622)
runs AFTER `angular_velocity` is built (line 607) — extend it to also
sanitize the velocity series so both downstream aggregations
(np.nanmax for peak, np.nanmean for mean) see a clean series.

Pure-Python (no GPU, no DB): `_analyze_spin` is pure-data over a poses array.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _analyzer() -> BiomechanicsAnalyzer:
    return BiomechanicsAnalyzer(get_element_def("upright_spin"))


def _spin_poses(n: int = 30) -> np.ndarray:
    """30-frame pose sequence where shoulders rotate around the spine so
    `detect_spin` fires: shoulder vector angle sweeps linearly -> uniform
    angular velocity well above the 200 deg/s threshold over 1.0 s at 30 fps,
    so `is_spin=True` and `spin_mask` covers all frames. Base for NaN
    injection tests.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    t = np.linspace(0, 2 * np.pi, n)
    poses[:, H36Key.LSHOULDER, 0] = 0.5 + 0.1 * np.cos(t)
    poses[:, H36Key.LSHOULDER, 1] = 0.5 + 0.1 * np.sin(t)
    poses[:, H36Key.RSHOULDER, 0] = 0.5 - 0.1 * np.cos(t)
    poses[:, H36Key.RSHOULDER, 1] = 0.5 - 0.1 * np.sin(t)
    # Hips: keep level (upright spin — minimal hip_y_range).
    poses[:, H36Key.LHIP] = [-0.1, 0.5]
    poses[:, H36Key.RHIP] = [0.1, 0.5]
    return poses


def _spin_phase(n: int = 30) -> ElementPhase:
    """ElementPhase covering all frames (spin: no takeoff/landing)."""
    return ElementPhase(name="upright_spin", start=0, takeoff=0, peak=n // 2, landing=0, end=n - 1)


def _spin_results(poses: np.ndarray) -> dict[str, float]:
    """Run _analyze_spin and return {name: value} for the spin_type metric
    (the consumer of mean_velocity).
    """
    analyzer = _analyzer()
    results = analyzer._analyze_spin(poses, _spin_phase(len(poses)), fps=30.0)
    by_name = {r.name: r.value for r in results}
    return {"spin_type": by_name["spin_type"]}


# --------------------------------------------------------------------------- #
# Observable 1: NaN RSHOULDER on one spin frame must NOT poison mean_velocity
# into NaN. np.mean(NaN_array) = NaN -> classify_spin receives NaN -> isfinite
# guard returns ("unknown", 0.0) silently -> spin_type collapses to 0.0
# sentinel, NOT the true spin-type score. The bug is silent, so the test
# catches the regression: spin_type must remain > 0.0 (the all-finite input
# yields a real score, so a NaN frame must not collapse it to 0.0).
# --------------------------------------------------------------------------- #


def test_nan_rshoulder_one_frame_spin_type_unchanged_repro():
    """CORRECT behavior: NaN RSHOULDER on a single spin frame (occlusion)
    must NOT collapse `spin_type` confidence to 0.0 (the silent "unknown"
    branch). The NaN-safe aggregation (np.nanmean + isfinite fallback) at
    the trust boundary on `angular_velocity` keeps the metric finite AND
    reflects the underlying spin (not the silent "unknown" sentinel from
    classify_spin's NaN-cmp rule).

    RED now: `np.mean(angular_velocity) = NaN` (np.mean, NOT nanmean)
    -> classify_spin(angular_velocity_mean=NaN) -> isfinite guard ->
    ("unknown", 0.0) -> spin_type=0.0 silently.
    """
    poses = _spin_poses()
    poses[5, H36Key.RSHOULDER] = np.nan  # occlusion on frame 5

    values = _spin_results(poses)

    # The all-finite reference case below yields spin_type > 0.0 (real score).
    # A NaN frame that collapses the metric to 0.0 is the silent-NaN bug.
    assert values["spin_type"] > 0.0, (
        f"BUG (#1328): _analyze_spin emitted spin_type={values['spin_type']!r} "
        f"from a NaN RSHOULDER on one frame. np.mean(NaN_array) = NaN -> "
        f"classify_spin(angular_velocity_mean=NaN) -> isfinite guard returns "
        f"('unknown', 0.0) silently. The NaN-cmp rule in classify_spin "
        f"silently degrades the spin_type metric. Use np.nanmean + "
        f"np.isfinite fallback on angular_velocity (mirror #912 peak_velocity "
        f"path with np.nanmax + isfinite). (#1328 MT)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: NaN LSHOULDER + RSHOULDER (one NaN each, different frames) ->
# mean_velocity must stay finite. Same root cause, mirrored on the other
# shoulder. Locks that the guard is symmetric, not just RSHOULDER-specific.
# --------------------------------------------------------------------------- #


def test_nan_either_shoulder_spin_type_finite_repro():
    """CORRECT behavior: NaN on EITHER shoulder (LSHOULDER or RSHOULDER) on
    a single spin frame must keep `spin_type` finite. The shoulder_vector
    subtraction is symmetric — a NaN on either side NaN-poisons
    angular_velocity -> mean_velocity -> classify_spin.

    RED now: NaN LSHOULDER -> shoulder_vector NaN -> arctan2/unwrap/gradient
    all-NaN -> np.mean = NaN -> classify_spin NaN -> spin_type=0.0 silently.
    """
    poses = _spin_poses()
    poses[3, H36Key.LSHOULDER] = np.nan  # occlusion on frame 3
    poses[7, H36Key.RSHOULDER] = np.nan  # occlusion on frame 7

    values = _spin_results(poses)

    assert values["spin_type"] > 0.0, (
        f"BUG (#1328): _analyze_spin emitted spin_type={values['spin_type']!r} "
        f"from NaN on either shoulder. NaN in shoulder_vector = NaN - NaN = "
        f"NaN -> mean_velocity=NaN -> classify_spin NaN -> silent 0.0. Fix "
        f"must sanitize angular_velocity before np.mean, not just RSHOULDER. "
        f"(#1328 MT)"
    )


# --------------------------------------------------------------------------- #
# Observable 3 (regression guard): NaN hip + finite shoulders -> the fix
# does not change this path. Hips feed detect_spin (hip_y) -> hip_y_range
# -> classify_spin's isfinite guard returns ("unknown", 0.0) on NaN
# hip_y_range. That pre-existing behavior is correct (silent sentinel for
# "no data" — same code path classify_spin already handles). This test
# pins the contract: #1328 MT fix must NOT alter the hip-NaN path. Any
# regression in this assertion means the fix accidentally introduced a
# new guard on the hip path.
# --------------------------------------------------------------------------- #


def test_nan_hip_finite_shoulder_spin_type_path_stable_repro():
    """CORRECT behavior: NaN hip with finite shoulders yields the existing
    `classify_spin` isfinite-guard sentinel `spin_type=0.0` (not affected
    by #1328 MT). The hip path is a separate, pre-existing concern
    (`hip_y_range=NaN` -> classify_spin NaN guard -> 0.0), NOT in scope
    of the #1328 MT fix (shoulder mean_velocity path).

    PASSES today (regression guard): locks that the fix targets the
    shoulder path, not the hip path. The fix must not change this value.
    """
    poses = _spin_poses()
    poses[:, H36Key.LHIP] = np.nan
    poses[:, H36Key.RHIP] = np.nan

    values = _spin_results(poses)

    # Pre-existing behavior: hip_y_range=NaN -> classify_spin isfinite
    # guard -> ("unknown", 0.0). Out of scope for #1328 MT (which is
    # the shoulder path). Lock the contract so a future fix doesn't
    # accidentally regress this path.
    assert values["spin_type"] == 0.0, (
        f"BUG (#1328 regression): NaN hips with finite shoulders yielded "
        f"spin_type={values['spin_type']!r}, expected 0.0 (existing "
        f"classify_spin NaN sentinel). #1328 MT fix must not alter the "
        f"hip-NaN path. (#1328 MT)"
    )


# --------------------------------------------------------------------------- #
# Regression: all-finite poses must yield a real spin_type (not 0.0). The
# NaN-safe aggregation (np.nanmean) is identity on all-finite input.
# --------------------------------------------------------------------------- #


def test_all_finite_spin_type_unchanged_repro():
    """Regression guard: an all-finite pose sequence must report a real
    `spin_type` confidence (> 0.0). np.nanmean is identity on all-finite
    input, so the no-NaN case is unchanged.
    """
    poses = _spin_poses()
    values = _spin_results(poses)

    assert values["spin_type"] > 0.0, (
        f"BUG (#1328 regression): all-finite spin reported spin_type="
        f"{values['spin_type']!r}. The guard must not zero out a real "
        f"spin-type score. (#1328 MT)"
    )


# --------------------------------------------------------------------------- #
# Source check 1: mean_velocity aggregation must be NaN-safe. Either
# (a) `np.mean(angular_velocity)` is preceded by a guard that sanitizes
# `angular_velocity` to finite values, OR (b) the call site uses
# `np.nanmean` (NaN-aware reduction). Bare `np.mean(NaN_array) = NaN` is
# the root cause — must be locked out at the source.
# --------------------------------------------------------------------------- #


def test_source_mean_velocity_uses_nanmean_or_isfinite_repro():
    """GREEN contract source check: `_analyze_spin` aggregates
    `angular_velocity` for `mean_velocity` in a NaN-safe way. Two
    acceptable idioms:

    1. Sanitize `angular_velocity` to finite values upstream
       (`angular_velocity = np.where(np.isfinite(angular_velocity), ...)`,
       or `angular_velocity = angular_velocity[np.isfinite(...)]`)
       — root-cause fix at the trust boundary, covers all downstream
       consumers.
    2. Use `np.nanmean` (NaN-aware reduction) at the mean call site —
       per-call-site fix, mirrors #912 peak_velocity path.

    Bare `np.mean(NaN_array) = NaN` is the root cause — locked out at
    the source.
    """
    src = inspect.getsource(BiomechanicsAnalyzer._analyze_spin)

    # Locate the mean_velocity computation block.
    m = re.search(r"mean_velocity\s*=.*", src)
    assert m, "Could not locate `mean_velocity = ...` in _analyze_spin"
    line = m.group(0)

    # Path A: nanmean at the call site (per-call-site fix, mirrors #912).
    uses_nanmean = "np.nanmean" in line
    # Path B: angular_velocity sanitized upstream (root-cause fix at the
    # trust boundary — covers mean + any future sibling consumer).
    sanitizes_velocity = bool(
        re.search(
            r"angular_velocity\s*=\s*np\.where\(\s*np\.isfinite\(angular_velocity\)",
            src,
        )
    ) or bool(re.search(r"angular_velocity\[np\.isfinite\(angular_velocity\)\]", src))

    assert uses_nanmean or sanitizes_velocity, (
        f"BUG (#1328 MT): `_analyze_spin` mean_velocity computation at "
        f"`{line!r}` is NOT NaN-safe. Either: (A) use `np.nanmean` at the "
        f"call site (mirrors #912 peak_velocity path), or (B) sanitize "
        f"`angular_velocity` to finite values at the trust boundary "
        f"(`angular_velocity = np.where(np.isfinite(angular_velocity), ...)`) "
        f"so all downstream aggregations inherit the guard. Bare "
        f"np.mean(NaN_array) = NaN is the root cause. (#1328 MT)"
    )


# --------------------------------------------------------------------------- #
# Source check 2: the angular_velocity series must be sanitized at the
# trust boundary (mirrors the #912 `unwrapped` guard on line 622).
# RED on master (no such guard on angular_velocity).
# --------------------------------------------------------------------------- #


def test_source_angular_velocity_sanitized_at_trust_boundary_repro():
    """Root cause locked: `angular_velocity` carries NaN frames when any
    shoulder is NaN. The #912 guard on `unwrapped` (line 622) sanitizes
    the series used by `compute_total_rotation`, but the sibling
    aggregation path (peak via np.nanmax, mean via np.mean) was only
    partially guarded — `mean_velocity` (line 665) used a bare np.mean.
    The fix must sanitize the inline `angular_velocity` series at the
    same trust boundary as `unwrapped`, so all downstream consumers
    (np.nanmax for peak, np.mean for mean) inherit the guard.
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "metrics.py"
    text = src_path.read_text(encoding="utf-8")
    # The trust-boundary guard idiom (mirrors #912 unwrapped guard).
    has_guard = bool(
        re.search(
            r"angular_velocity\s*=\s*np\.where\(\s*np\.isfinite\(angular_velocity\)",
            text,
        )
    ) or bool(re.search(r"angular_velocity\[np\.isfinite\(angular_velocity\)\]", text))
    assert has_guard, (
        "BUG (#1328 MT): metrics.py lacks an `angular_velocity` "
        "sanitization guard at the trust boundary. NaN frames in "
        "angular_velocity propagate through np.mean into classify_spin's "
        "silent NaN-cmp branch. Add `if not np.all(np.isfinite(angular_velocity)): "
        "angular_velocity = np.where(np.isfinite(angular_velocity), angular_velocity, 0.0)` "
        "right after the existing #912 `unwrapped` guard. (#1328 MT)"
    )
