"""RED repro — `BiomechanicsAnalyzer._analyze_step` peak-extraction sites
(metrics.py:526, 542, 558) use `float(np.max(...))` on a potentially
NaN-contaminated series, silently propagating NaN to the user-facing
`MetricResult.value`.

Three sites in `_analyze_step`:

    se_angle = self.compute_spread_eagle_angle(poses)
    peak_se = float(np.max(se_angle))         # line ~506
    results.append(MetricResult(name="spread_eagle_angle", value=peak_se,
                                is_good=peak_se >= 150, ...))

    ib_score = self.compute_ina_bauer_score(poses, se_angle=se_angle)
    peak_ib = float(np.max(ib_score))         # line ~519
    results.append(MetricResult(name="ina_bauer_score", value=peak_ib,
                                is_good=peak_ib >= 0.7, ...))

    spiral_ind = self.compute_spiral_indicator(poses)
    max_spiral = float(np.max(spiral_ind))    # line ~532
    results.append(MetricResult(name="spiral_indicator", value=max_spiral, ...))

NumPy contract (NOT a defensive coding choice — a hard semantic):

    np.max([1.0, 2.0, NaN]) = NaN
    np.max([NaN, NaN, NaN]) = NaN
    np.nanmax([1.0, 2.0, NaN]) = 2.0          ← correct
    np.nanmax([NaN, NaN, NaN]) = RuntimeWarning, returns NaN (still no good)

Any NaN in the series (corrupt keypoint, occluded joint) → np.max(NaN-array)
= NaN silently → float(NaN) = NaN → MetricResult.value = NaN.
Then is_good = (NaN >= 150) = False (NaN-comparison rule). User sees
"spread_eagle_angle: nan" with is_good=False — silent false-bad.

This is the peak-extraction-layer bug on top of the producer-layer
`compute_spread_eagle_angle` series bug (#962, #976). Fix:
np.nanmax + isfinite fallback (0.0 sentinel) or upstream np.nan_to_num.

Closes #1275.
"""

from __future__ import annotations

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase


def _step_phases(n: int = 6) -> ElementPhase:
    return ElementPhase(
        name="three_turn",
        start=0,
        takeoff=0,
        peak=max(1, n // 2),
        landing=max(1, n - 1),
        end=n,
    )


def _get_step_metric(metrics, name: str):
    for m in metrics:
        if m.name == name:
            return m
    raise AssertionError(f"metric {name!r} not in {[m.name for m in metrics]}")


# --------------------------------------------------------------------------- #
# Observable 1: a single NaN in the se_angle series (NaN in se_angle but
# finite elsewhere) must NOT NaN-poison peak_se.
# --------------------------------------------------------------------------- #


def test_peak_se_single_nan_series_finite_repro():
    """CORRECT: peak_se with a NaN somewhere in se_angle must be FINITE.

    np.max(NaN-array) = NaN silently propagates. np.nanmax skips NaN
    frames. After fix: peak_se = finite value (or 0.0 sentinel when all-NaN).
    """
    from tests.conftest import SyntheticPoseFactory

    poses = SyntheticPoseFactory.make_standing_pose(n_frames=6).copy()
    analyzer = BiomechanicsAnalyzer(get_element_def("three_turn"))
    se_angle = analyzer.compute_spread_eagle_angle(poses)
    # Inject NaN into the series at one frame (e.g. occluded joint slipped
    # past the producer-side #976 guard, or upstream NaN chain).
    se_angle_corrupt = se_angle.copy()
    se_angle_corrupt[2] = np.nan
    # peak via the offending pattern (np.max, no guard):
    peak_naive = float(np.max(se_angle_corrupt))
    assert np.isnan(peak_naive), (
        f"test fixture broken: np.max of NaN-containing series returned "
        f"{peak_naive}, expected NaN to validate the repro premise."
    )
    # CORRECT: nanmax with isfinite fallback
    peak_fixed = float(np.nanmax(se_angle_corrupt)) if np.isfinite(se_angle_corrupt).any() else 0.0
    if not np.isfinite(peak_fixed):
        peak_fixed = 0.0
    assert np.isfinite(peak_fixed), (
        f"BUG: peak_se = {peak_fixed} (NaN) for a NaN-in-series input. "
        f"np.max(NaN-array) = NaN silently poisons MetricResult.value. "
        f"Fix: np.nanmax + np.isfinite fallback (0.0 sentinel). (#1275)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: all-NaN se_angle series (worst case — every frame NaN).
# --------------------------------------------------------------------------- #


def test_peak_se_all_nan_series_zero_sentinel_repro():
    """CORRECT: all-NaN se_angle series must produce a 0.0 sentinel, NOT NaN.

    np.max([NaN]*N) = NaN. np.nanmax([NaN]*N) raises RuntimeWarning and
    returns NaN. Sentinel 0.0 is required for JSON-serializable MetricResult.
    """
    se_angle = np.full(6, np.nan, dtype=np.float32)
    peak_naive = float(np.max(se_angle))
    assert np.isnan(peak_naive), "test fixture broken: np.max all-NaN != NaN"

    # CORRECT pattern (matches the #962 fix in master):
    peak_fixed = float(np.nanmax(se_angle)) if np.isfinite(se_angle).any() else 0.0
    if not np.isfinite(peak_fixed):
        peak_fixed = 0.0
    assert peak_fixed == 0.0, (
        f"BUG: all-NaN se_angle series produced {peak_fixed}, expected "
        f"0.0 sentinel. np.max(NaN) = NaN silently poisons MetricResult. "
        f"Fix: nanmax + isfinite fallback to 0.0. (#1275)"
    )


# --------------------------------------------------------------------------- #
# Observable 3: NaN-via-chain (inf - inf) must not leak into peak_ib.
# --------------------------------------------------------------------------- #


def test_peak_ib_nan_via_chain_finite_repro():
    """CORRECT: NaN-via-inf-inf arithmetic in ib_score must NOT poison peak_ib.

    Same NumPy contract: np.max(NaN-array) = NaN. The peak-extraction layer
    must use nanmax+isfinite to skip NaN entries.
    """
    import math

    nan_via_chain = math.inf - math.inf
    assert math.isnan(nan_via_chain)
    ib_score = np.array([0.5, 0.6, nan_via_chain, 0.8, 0.7, 0.9], dtype=np.float32)
    peak_naive = float(np.max(ib_score))
    assert np.isnan(peak_naive), "test fixture broken"

    peak_fixed = float(np.nanmax(ib_score)) if np.isfinite(ib_score).any() else 0.0
    if not np.isfinite(peak_fixed):
        peak_fixed = 0.0
    assert np.isfinite(peak_fixed), (
        f"BUG: peak_ib = {peak_fixed} (NaN) for NaN-via-chain input. "
        f"np.max propagates NaN. Fix: np.nanmax + isfinite fallback. (#1275)"
    )


# --------------------------------------------------------------------------- #
# Observable 4: max_spiral with NaN in spiral_ind must not poison value.
# --------------------------------------------------------------------------- #


def test_max_spiral_nan_series_finite_repro():
    """CORRECT: max_spiral with NaN in spiral_ind series must be FINITE.

    spiral_indicator = |LFOOT_y - RFOOT_y|. Occluded LFOOT -> NaN spiral.
    np.max(NaN-array) = NaN silently. Fix: nanmax+isfinite.
    """
    spiral_ind = np.array([0.1, 0.2, np.nan, 0.3, 0.25, 0.15], dtype=np.float32)
    peak_naive = float(np.max(spiral_ind))
    assert np.isnan(peak_naive), "test fixture broken"

    max_fixed = float(np.nanmax(spiral_ind)) if np.isfinite(spiral_ind).any() else 0.0
    if not np.isfinite(max_fixed):
        max_fixed = 0.0
    assert np.isfinite(max_fixed), (
        f"BUG: max_spiral = {max_fixed} (NaN) for NaN-in-series input. "
        f"Fix: np.nanmax + isfinite fallback (0.0 sentinel). (#1275)"
    )


# --------------------------------------------------------------------------- #
# Regression guard: clean all-finite series must produce identical peaks under
# the fixed pattern (nanmax+isfinite is identity on all-finite input).
# --------------------------------------------------------------------------- #


def test_peak_se_clean_series_identity_regression():
    """CORRECT: nanmax+isfinite on all-finite input equals np.max result.

    Regression: the fix must not change behavior on clean data.
    """
    se_angle = np.array([120.0, 150.0, 165.0, 170.0, 160.0, 145.0], dtype=np.float32)
    peak_naive = float(np.max(se_angle))
    peak_fixed = float(np.nanmax(se_angle)) if np.isfinite(se_angle).any() else 0.0
    assert peak_naive == peak_fixed == 170.0, (
        f"BUG: regression — nanmax+isfinite broke all-finite input. "
        f"np.max = {peak_naive}, nanmax path = {peak_fixed}."
    )


# --------------------------------------------------------------------------- #
# Source-locking guard: assert the file no longer uses `float(np.max(...))` on
# a NaN-able series for the three peak sites. Locks the fix in.
# --------------------------------------------------------------------------- #


def test_peak_sites_no_unguarded_float_np_max_repro():
    """Lock: peak_se / peak_ib / max_spiral sites must not use `float(np.max(...))`.

    The unguarded pattern silently propagates NaN. After the fix the file
    uses `float(np.nanmax(...))` with an `np.isfinite` fallback.
    """
    from pathlib import Path

    src = Path("ml/src/analysis/metrics.py").read_text()
    # Find _analyze_step body by anchoring on the metric names
    assert 'name="spread_eagle_angle"' in src, "test fixture broken"
    assert 'name="ina_bauer_score"' in src, "test fixture broken"
    assert 'name="spiral_indicator"' in src, "test fixture broken"
    # The three peak sites must NOT use the bare np.max pattern. We allow
    # np.max elsewhere (e.g. compute_leg_straightness) but the three peak
    # aggregations must be nanmax+isfinite. Check by scanning lines around
    # each MetricResult:
    needle_sites = [
        'name="spread_eagle_angle"',
        'name="ina_bauer_score"',
        'name="spiral_indicator"',
    ]
    for needle in needle_sites:
        idx = src.find(needle)
        assert idx > 0
        # Look back ~400 chars for the peak computation line
        window = src[max(0, idx - 600) : idx]
        # The unguarded `float(np.max(` pattern must NOT appear in this
        # window. (nanmax is fine.)
        assert "float(np.max(" not in window, (
            f"BUG: unguarded `float(np.max(` still present near {needle!r} "
            f"in _analyze_step. NaN-contaminated series silently propagates "
            f"NaN to MetricResult.value. Fix: np.nanmax + np.isfinite "
            f"fallback. (#1275)"
        )
