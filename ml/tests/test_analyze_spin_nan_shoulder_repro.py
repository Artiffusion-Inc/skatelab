"""RED repro — `BiomechanicsAnalyzer._analyze_spin` (metrics.py:572-668)
leaks NaN into `spin_peak_velocity` / `total_rotation_deg` /
`rotation_count` when the shoulder keypoint is NaN on any frame of the
spin element (occlusion). Issue #912.

Root cause (metrics.py:594-648):

    left_shoulder  = poses[:, LSHOULDER]
    right_shoulder = poses[:, RSHOULDER]
    shoulder_vector = right_shoulder - left_shoulder
    angles = np.arctan2(shoulder_vector[:, 1], shoulder_vector[:, 0])
    unwrapped = np.unwrap(angles)
    angular_velocity = np.abs(np.gradient(unwrapped) * fps) * (180.0 / np.pi)
    ...
    peak_velocity = float(np.max(angular_velocity[spin_mask]))   # np.max, NOT
                                                                  # np.nanmax -> NaN
    ...
    total_rotation_deg, rotation_count = compute_total_rotation(unwrapped, fps)
        # leaf helper: abs(unwrapped[-1] - unwrapped[0]) -> NaN on NaN endpoints

NaN in either shoulder on any frame -> `shoulder_vector` NaN ->
`np.arctan2(nan, x)` = NaN -> `np.unwrap(NaN)` = NaN ->
`np.gradient(NaN)` = NaN -> `angular_velocity` carries NaN frames.

- `np.max(angular_velocity[spin_mask])` (np.max, NOT np.nanmax) propagates
  NaN -> `spin_peak_velocity` = NaN.
- `compute_total_rotation(unwrapped, fps)` -> `abs(unwrapped[-1] -
  unwrapped[0])` = NaN on NaN endpoints -> `(NaN, NaN)` ->
  `total_rotation_deg`, `rotation_count` = NaN. Same leaf-helper endpoint
  pattern as CJ (#909), but `_analyze_spin` builds `unwrapped` inline with NO
  upstream NaN guard (unlike `compute_total_rotation_from_poses`, which #913
  guarded).

The `if is_spin and np.any(spin_mask)` guard (line 616) does NOT cover NaN —
length is valid, the data is NaN. Neither `_analyze_spin` nor the leaf
`compute_total_rotation` has an `np.isnan` / `np.nanmax` / `np.isfinite` guard
on this path.

Consumer / prod-impact: `BiomechanicsAnalyzer.analyze` (metrics.py:152)
dispatches spin elements to `_analyze_spin`. NaN shoulder on any spin frame
-> 3 NaN metrics -> recommender -> report JSON -> GOE proxy. `spin_peak_velocity`
is the PRIMARY spin-quality signal; `rotation_count` is the PRIMARY spin
identifier — NaN breaks spin classification.

Fix (NOT applied — repro only): mirror #913 (`compute_total_rotation_from_poses`)
— guard the inline `unwrapped` series BEFORE delegating to the leaf
`compute_total_rotation`, AND replace the bare `np.max(angular_velocity[spin_mask])`
with `np.nanmax` + `np.isfinite` fallback (mirrors #962 `_analyze_step`,
#903 `compute_rotation_speed`, #993 `get_spine_length`). NaN shoulder on any
spin frame must NOT NaN-poison the three spin metrics. Lazy: one guard on the
unwrapped series + one nanmax at the peak aggregation.

The leaf `compute_total_rotation` stays unguarded by design (#913 guards
upstream, not the leaf). `_analyze_spin` builds its own `unwrapped` inline,
so the guard belongs here — the trust boundary is the inline-built series.

Pure-Python (no GPU, no DB): `_analyze_spin` is pure-data over a poses array.
"""

import inspect

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _analyzer() -> BiomechanicsAnalyzer:
    return BiomechanicsAnalyzer(get_element_def("upright_spin"))


def _spin_poses(n: int = 30) -> np.ndarray:
    """A 30-frame all-finite pose sequence (N, 17, 2) where the shoulders
    rotate around the spine so `detect_spin` fires: shoulder vector angle
    sweeps linearly -> uniform angular velocity ~372 deg/s (>200 threshold)
    over 1.0 s at 30 fps, so `is_spin=True` and `spin_mask` covers all frames.
    Base for NaN-injection tests.
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
    """Run _analyze_spin and return {name: value} for the three spin-metric
    series under test (spin_peak_velocity, total_rotation_deg,
    rotation_count).
    """
    analyzer = _analyzer()
    results = analyzer._analyze_spin(poses, _spin_phase(len(poses)), fps=30.0)
    by_name = {r.name: r.value for r in results}
    return {
        "spin_peak_velocity": by_name["spin_peak_velocity"],
        "total_rotation_deg": by_name["total_rotation_deg"],
        "rotation_count": by_name["rotation_count"],
    }


# --------------------------------------------------------------------------- #
# Observable 1: NaN RSHOULDER on one spin frame must NOT collapse the three
# spin metrics to NaN. np.max(NaN_array) = NaN -> MetricResult(value=nan).
# --------------------------------------------------------------------------- #


def test_nan_rshoulder_one_frame_spin_metrics_finite_repro():
    """CORRECT behavior: NaN RSHOULDER on a single spin frame (occlusion)
    must NOT NaN-poison `spin_peak_velocity` / `total_rotation_deg` /
    `rotation_count`. `np.nanmax` skips the NaN frame; the inline `unwrapped`
    series is NaN-guarded before the leaf `compute_total_rotation`.

    RED now: `np.max(angular_velocity[spin_mask]) = NaN` (np.max, NOT nanmax)
    -> spin_peak_velocity=NaN. `compute_total_rotation(unwrapped, fps)` ->
    abs(NaN[-1] - NaN[0]) = NaN -> total_rotation_deg=NaN, rotation_count=NaN.
    """
    poses = _spin_poses()
    poses[5, H36Key.RSHOULDER] = np.nan  # occlusion on frame 5

    values = _spin_results(poses)

    for name, value in values.items():
        assert np.isfinite(value), (
            f"BUG: _analyze_spin emitted NaN {name} from a NaN RSHOULDER on "
            "one frame. np.max(NaN_array) = NaN collapses the metric; the inline "
            "unwrapped series is unguarded before compute_total_rotation. Use "
            "np.nanmax + np.isfinite fallback AND guard the unwrapped series "
            "(mirrors #913 / #962). (#912)"
        )


# --------------------------------------------------------------------------- #
# Observable 2: all-NaN shoulders (both LSHOULDER + RSHOULDER every frame) ->
# finite sentinel (0.0), NOT NaN. Blast radius: full occlusion still must
# not NaN-poison the metrics / break JSON serialization.
# --------------------------------------------------------------------------- #


def test_nan_any_shoulder_spin_metrics_finite_repro():
    """CORRECT behavior: all-NaN shoulders (LSHOULDER + RSHOULDER every spin
    frame) must yield finite (0.0 sentinel) spin metrics, NOT NaN. Full
    occlusion must not collapse the metric series or break JSON / GOE proxy.

    RED now: every frame NaN -> shoulder_vector all-NaN -> arctan2/unwrap/
    gradient all-NaN -> np.max = NaN -> 3 NaN metrics. After fix: nanmax of
    all-NaN -> isfinite fallback -> 0.0; unwrapped all-NaN -> guard -> 0.0
    sentinel from compute_total_rotation path.
    """
    poses = _spin_poses()
    poses[:, H36Key.LSHOULDER] = np.nan
    poses[:, H36Key.RSHOULDER] = np.nan

    values = _spin_results(poses)

    for name, value in values.items():
        assert np.isfinite(value), (
            f"BUG: all-NaN shoulders -> NaN {name}. Full occlusion must yield "
            "the 0.0 sentinel (neutral 'no data'), not NaN. Mirrors #913 "
            "compute_total_rotation_from_poses all-NaN guard. (#912)"
        )


# --------------------------------------------------------------------------- #
# Observable 3: NaN hip but finite shoulders -> finite result. Hips feed
# detect_spin (hip_y) but the rotation math uses only shoulders; a NaN hip
# must not poison the rotation metrics. Locks that the guard is on the
# shoulder path only.
# --------------------------------------------------------------------------- #


def test_nan_hip_finite_shoulder_spin_metrics_finite_repro():
    """CORRECT behavior: NaN hip (RHIP/LHIP) with finite shoulders must yield
    finite spin metrics. The rotation math (shoulder_vector -> arctan2 ->
    unwrap -> gradient -> total_rotation) uses only LSHOULDER/RSHOULDER, so a
    NaN hip must not leak into the three rotation metrics.

    PASSES today (regression guard): locks that the fix targets the shoulder
    path, not the hip path.
    """
    poses = _spin_poses()
    poses[:, H36Key.LHIP] = np.nan
    poses[:, H36Key.RHIP] = np.nan

    values = _spin_results(poses)

    for name, value in values.items():
        assert np.isfinite(value), (
            f"BUG: NaN hip with finite shoulders leaked non-finite {name}. "
            "Hip is not used by the rotation math — guard must be on the "
            "shoulder path only. (#912)"
        )


# --------------------------------------------------------------------------- #
# Regression guard: all-finite poses unchanged — known spin metrics
# reproduced. The NaN-safe aggregation (np.nanmax) is identity on all-finite
# input, so the no-NaN case is unchanged.
# --------------------------------------------------------------------------- #


def test_all_finite_spin_metrics_unchanged_repro():
    """Regression guard: an all-finite pose sequence must still report finite
    `spin_peak_velocity` / `total_rotation_deg` / `rotation_count`. The
    NaN-safe aggregation (np.nanmax) is identity on all-finite input, so the
    no-NaN case is unchanged.
    """
    poses = _spin_poses()
    values = _spin_results(poses)

    for name, value in values.items():
        assert np.isfinite(value), (
            f"BUG (regression): all-finite poses reported non-finite {name}. "
            "The no-NaN case must be unchanged by the NaN-safe aggregation."
        )
    # spin_peak_velocity must be nonzero (real rotation in the fixture).
    assert values["spin_peak_velocity"] > 0.0, (
        f"BUG (regression): all-finite spin reported zero peak_velocity="
        f"{values['spin_peak_velocity']!r}. The guard must not zero out a "
        "real spin."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `_analyze_spin` aggregates the
# spin-metric series with a NaN-safe reduction (`np.nanmax`) + `np.isfinite`
# fallback AND guards the inline `unwrapped` series before delegating to the
# leaf `compute_total_rotation`. NOT bare `np.max`; NOT an unguarded
# `compute_total_rotation` call on a NaN-bearing series.
# --------------------------------------------------------------------------- #


def test_analyze_spin_has_nanmax_and_unwrapped_guard_source_repro():
    """GREEN contract source check: `_analyze_spin` aggregates
    `angular_velocity[spin_mask]` with `np.nanmax` + `np.isfinite` fallback
    (mirrors #962 `_analyze_step`, #903 `compute_rotation_speed`), AND guards
    the inline `unwrapped` series with `np.isfinite` before delegating to the
    leaf `compute_total_rotation` (mirrors #913
    `compute_total_rotation_from_poses`). The root cause (bare
    `np.max(NaN_array) = NaN` + unguarded `compute_total_rotation(NaN_series)`)
    must be locked out at the source.
    """
    src = inspect.getsource(BiomechanicsAnalyzer._analyze_spin)

    assert "np.nanmax" in src, (
        "BUG: _analyze_spin uses bare np.max (NOT np.nanmax) to aggregate "
        "angular_velocity over the spin mask. np.max(NaN_array) = NaN "
        "collapses the whole metric on a single NaN shoulder frame. Use "
        "np.nanmax + np.isfinite fallback (mirrors #962 / #903). (#912)"
    )
    assert "np.isfinite" in src, (
        "BUG: _analyze_spin has no np.isfinite guard. The nanmax of an "
        "all-NaN series yields NaN (+ RuntimeWarning), and the inline "
        "unwrapped series is unguarded before compute_total_rotation. "
        "Mirror #913: `if not np.all(np.isfinite(unwrapped)): return 0.0, "
        "0.0`. (#912)"
    )
