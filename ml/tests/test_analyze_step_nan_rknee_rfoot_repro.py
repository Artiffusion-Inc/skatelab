"""RED repro — `BiomechanicsAnalyzer._analyze_step` (metrics.py:460-555)
aggregates the per-frame `spread_eagle_angle` / `ina_bauer_score` /
`spiral_indicator` series with bare `np.max`:

    se_angle = self.compute_spread_eagle_angle(poses)
    peak_se = float(np.max(se_angle))                    # NaN -> np.max = NaN
    ib_score = self.compute_ina_bauer_score(poses, se_angle=se_angle)
    peak_ib = float(np.max(ib_score))                    # NaN -> NaN
    spiral_ind = self.compute_spiral_indicator(poses)
    max_spiral = float(np.max(spiral_ind))               # NaN -> NaN

`np.max` (unlike `np.nanmax`) propagates NaN: a single NaN frame collapses
the whole series to NaN, then `float(NaN) = nan` -> `MetricResult(value=nan)`
silently leaks into the session report / JSON serialization / GOE composite.

The producer functions were guarded by #976 (nan_to_num on their joint
inputs), so on master the three series are usually finite and `np.max` happens
to return finite. BUT the leak path is in `_analyze_step` itself: if a
producer ever regresses (or a caller-supplied `se_angle` carries NaN, or a
future joint path is added without the guard), the bare `np.max` collapses the
metric to NaN with NO defense at the aggregation trust boundary. This locks
the contract: the aggregation must be NaN-safe (`np.nanmax` + `np.isfinite`
fallback to 0.0), mirroring the #903 `compute_rotation_speed` pattern and the
#993 `get_spine_length` nanmean pattern. Lazy: one guard at the aggregation,
not at every producer.

Pure-Python (no GPU, no DB): `_analyze_step` is pure-data over a poses array.
NaN-bearing series are injected by stubbing the producer methods (simulating a
producer regression / occluded-frame leak), isolating the aggregation guard
from the producer guards (#976). A direct-RKNEE/RFOOT-NaN path is also
covered to lock the end-to-end contract.
"""

import inspect

import numpy as np

from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _step_poses(n: int = 8) -> np.ndarray:
    """An 8-frame all-finite pose sequence (N, 17, 2) with legs abducted so
    `spread_eagle_angle` is well-defined. Base for NaN-injection tests.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.HIP_CENTER] = [0.0, 0.5]
        poses[f, H36Key.LHIP] = [-0.1, 0.5]
        poses[f, H36Key.RHIP] = [0.1, 0.5]
        poses[f, H36Key.LKNEE] = [-0.3, 0.9]
        poses[f, H36Key.RKNEE] = [0.3, 0.9]
        poses[f, H36Key.LFOOT] = [-0.35, 1.1]
        poses[f, H36Key.RFOOT] = [0.35, 1.1]
        poses[f, H36Key.THORAX] = [0.0, 0.2]
    return poses


def _step_phase(n: int = 8) -> ElementPhase:
    """A trivial ElementPhase covering all frames (step/turn: no takeoff)."""
    return ElementPhase(name="three_turn", start=0, takeoff=0, peak=n // 2, landing=0, end=n - 1)


def _make_analyzer() -> BiomechanicsAnalyzer:
    """Build a BiomechanicsAnalyzer without the ElementDef init (only the
    analysis methods are exercised; element_def is unused by _analyze_step).
    """
    return BiomechanicsAnalyzer.__new__(BiomechanicsAnalyzer)


def _step_results(poses: np.ndarray) -> dict[str, float]:
    """Run _analyze_step and return a {name: value} dict for the three
    step-metric series under test.
    """
    analyzer = _make_analyzer()
    results = analyzer._analyze_step(poses, _step_phase(len(poses)), fps=30.0)
    by_name = {r.name: r.value for r in results}
    return {
        "spread_eagle_angle": by_name["spread_eagle_angle"],
        "ina_bauer_score": by_name["ina_bauer_score"],
        "spiral_indicator": by_name["spiral_indicator"],
    }


# --------------------------------------------------------------------------- #
# Observable 1: a NaN-bearing spread_eagle_angle series (producer regression /
# occluded RKNEE frame slipping past the #976 guard) must NOT collapse the
# aggregated spread_eagle_angle / ina_bauer_score metrics to NaN.
# --------------------------------------------------------------------------- #


def test_nan_se_angle_series_does_not_collapse_step_metrics_repro():
    """CORRECT behavior: when `compute_spread_eagle_angle` returns a series
    containing a NaN frame (occluded RKNEE on one frame, or a producer
    regression), `_analyze_step`'s `np.nanmax` aggregation must skip the NaN
    frame and emit a finite `spread_eagle_angle` (and the `ina_bauer_score`
    that consumes it), NOT NaN. Bare `np.max(NaN_array) = NaN` silently leaks
    NaN into MetricResult. Guard at the aggregation trust boundary.

    RED now: stub the producer to return a NaN-bearing series -> np.max =
    NaN -> MetricResult(value=nan). After the fix: np.nanmax skips the NaN
    frame -> finite.
    """
    analyzer = _make_analyzer()
    poses = _step_poses()

    finite_se = BiomechanicsAnalyzer.compute_spread_eagle_angle(poses)
    nan_se = finite_se.copy()
    nan_se[3] = np.nan  # one occluded-RKNEE frame leaks NaN into the series

    analyzer.compute_spread_eagle_angle = lambda p: nan_se  # type: ignore[assignment]
    analyzer.compute_ina_bauer_score = lambda p, se_angle=None: (
        BiomechanicsAnalyzer.compute_ina_bauer_score(  # noqa: E731
            analyzer, p, se_angle=nan_se
        )
    )

    results = analyzer._analyze_step(poses, _step_phase(len(poses)), fps=30.0)
    by_name = {r.name: r.value for r in results}

    assert np.isfinite(by_name["spread_eagle_angle"]), (
        "BUG: _analyze_step emitted NaN spread_eagle_angle from a NaN-bearing "
        "se_angle series. np.max(NaN_array) = NaN collapses the whole metric. "
        "Use np.nanmax + np.isfinite fallback (mirrors #903 / #993). (#962)"
    )
    assert np.isfinite(by_name["ina_bauer_score"]), (
        "BUG: _analyze_step emitted NaN ina_bauer_score from a NaN-bearing "
        "se_angle series. np.max(NaN_array) = NaN. Use np.nanmax + np.isfinite "
        "fallback. (#962)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: a NaN-bearing spiral_indicator series (occluded RFOOT frame
# slipping past the #976 guard) must NOT collapse spiral_indicator to NaN.
# --------------------------------------------------------------------------- #


def test_nan_spiral_series_does_not_collapse_spiral_metric_repro():
    """CORRECT behavior: when `compute_spiral_indicator` returns a series
    containing a NaN frame (occluded RFOOT on one frame, or a producer
    regression), `_analyze_step`'s `np.nanmax` aggregation must skip the NaN
    frame and emit a finite `spiral_indicator`, NOT NaN. Bare
    `np.max(NaN_array) = NaN`.

    RED now: stub the producer to return a NaN-bearing series -> np.max = NaN
    -> MetricResult(value=nan). After the fix: np.nanmax -> finite.
    """
    analyzer = _make_analyzer()
    poses = _step_poses()

    finite_sp = BiomechanicsAnalyzer.compute_spiral_indicator(poses)
    nan_sp = finite_sp.copy()
    nan_sp[5] = np.nan  # one occluded-RFOOT frame leaks NaN into the series

    analyzer.compute_spiral_indicator = lambda p: nan_sp  # type: ignore[assignment]

    results = analyzer._analyze_step(poses, _step_phase(len(poses)), fps=30.0)
    by_name = {r.name: r.value for r in results}

    assert np.isfinite(by_name["spiral_indicator"]), (
        "BUG: _analyze_step emitted NaN spiral_indicator from a NaN-bearing "
        "spiral series. np.max(NaN_array) = NaN collapses the whole metric. "
        "Use np.nanmax + np.isfinite fallback (mirrors #903 / #993). (#962)"
    )


# --------------------------------------------------------------------------- #
# Observable 3: direct end-to-end — NaN RKNEE on one frame + NaN RFOOT on
# another must NOT leak NaN into the three step-metric MetricResults. This
# locks the contract on the real input path (producers + aggregation together).
# --------------------------------------------------------------------------- #


def test_nan_rknee_rfoot_one_frame_each_step_metrics_finite_repro():
    """CORRECT behavior: an occluded RKNEE on one frame and RFOOT on another
    must NOT leak NaN into `spread_eagle_angle` / `ina_bauer_score` /
    `spiral_indicator` MetricResults. The #976 producer guards convert NaN
    joints to 0.0 sentinels AND the #962 aggregation guard (np.nanmax) skips
    any NaN frame that nonetheless slips through. Defense in depth.

    RED now (master): the producer guards already make the series finite, so
    this PASSES today — it locks the end-to-end contract so a future producer
    regression cannot re-leak NaN through the aggregation.
    """
    poses = _step_poses()
    poses[3, H36Key.RKNEE] = np.nan  # occluded right knee on frame 3
    poses[5, H36Key.RFOOT] = np.nan  # occluded right foot on frame 5

    values = _step_results(poses)

    for name, value in values.items():
        assert np.isfinite(value), (
            f"BUG: _analyze_step emitted NaN {name} with an occluded RKNEE "
            "and RFOOT frame. The aggregation must be NaN-safe "
            "(np.nanmax + np.isfinite fallback). (#962)"
        )


# --------------------------------------------------------------------------- #
# Regression: all-finite poses -> finite step metrics. The NaN-safe
# aggregation must not change the no-NaN case (np.nanmax is identity on
# all-finite input).
# --------------------------------------------------------------------------- #


def test_all_finite_step_metrics_unchanged_repro():
    """Regression guard: an all-finite pose sequence must still report finite
    spread_eagle_angle, ina_bauer_score, and spiral_indicator. The NaN-safe
    aggregation (np.nanmax) is identity on all-finite input, so the no-NaN
    case is unchanged.
    """
    poses = _step_poses()
    values = _step_results(poses)

    for name, value in values.items():
        assert np.isfinite(value), (
            f"BUG (regression): all-finite poses reported non-finite {name}. "
            "The no-NaN case must be unchanged by the NaN-safe aggregation."
        )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — _analyze_step aggregates the three
# step-metric series with a NaN-safe reduction (np.nanmax / np.nanmean) and
# an np.isfinite fallback, NOT bare np.max.
# --------------------------------------------------------------------------- #


def test_analyze_step_has_nanmax_guard_at_aggregation_repro():
    """GREEN contract source check: `_analyze_step` aggregates the
    `spread_eagle_angle` / `ina_bauer_score` / `spiral_indicator` series with
    a NaN-safe reduction (`np.nanmax` / `np.nanmean`) plus an `np.isfinite`
    fallback (to 0.0 on all-NaN), mirroring the #903 `compute_rotation_speed`
    nanmax+isfinite pattern and the #993 `get_spine_length` nanmean pattern.
    The root cause (bare `np.max(NaN_array) = NaN`, no trust-boundary guard)
    must be locked out at the source.
    """
    src = inspect.getsource(BiomechanicsAnalyzer._analyze_step)

    assert "np.nanmax" in src or "np.nanmean" in src, (
        "BUG: _analyze_step uses bare np.max (NOT np.nanmax) to aggregate the "
        "step-metric series. np.max(NaN_array) = NaN collapses the whole "
        "metric on a single NaN frame (occluded RKNEE/RFOOT, producer "
        "regression). Use np.nanmax + np.isfinite fallback (mirrors #903 / "
        "#993). (#962)"
    )
    assert "np.isfinite" in src, (
        "BUG: _analyze_step has no np.isfinite fallback after the NaN-safe "
        "reduction. An all-NaN series yields np.nanmax -> RuntimeWarning + "
        "NaN, which still leaks. Mirror #903: `peak = float(np.nanmax(...)); "
        "if not np.isfinite(peak): peak = 0.0`. (#962)"
    )
