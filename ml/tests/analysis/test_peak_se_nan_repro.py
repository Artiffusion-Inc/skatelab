"""Regression test — `_analyze_step` peak aggregations must be NaN-safe.

Locks the GREEN contract from #1275 (tranche MX): `peak_se`,
`peak_ib`, and `max_spiral` MUST stay finite even when the underlying
series (`se_angle`, `ib_score`, `spiral_ind`) carry NaN frames.

Pre-#1275 root cause (metrics.py:506, 519, 524):

    se_angle = self.compute_spread_eagle_angle(poses)
    peak_se = float(np.max(se_angle))                # NaN-propagate
    ...
    ib_score = self.compute_ina_bauer_score(poses, se_angle=se_angle)
    peak_ib = float(np.max(ib_score))                # NaN-propagate
    ...
    max_spiral = float(np.max(spiral_ind))           # NaN-propagate

`np.max(NaN-array) = NaN` (numpy is not NaN-aware). The NaN then leaks
into `MetricResult.value` and triggers `_is_bad(NaN, ref_range) = True`
in the recommender (sibling to MW), producing a false-worst
recommendation for a non-existent problem.

The fix (already on master via #1275) uses `np.nanmax(...) if
np.isfinite(...).any() else 0.0` at each peak site, mirroring the
#912 / #903 / #993 NaN-safe aggregation idiom.

These tests inject NaN into the series via monkeypatch and assert
each `MetricResult.value` is finite. They are GREEN on master and
would have been RED pre-#1275.
"""

from __future__ import annotations

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _step_def():
    return get_element_def("three_turn")


def _step_poses(n: int = 10) -> np.ndarray:
    """Standing pose — same synthetic data as the spin repro tests."""
    from tests.conftest import SyntheticPoseFactory

    return SyntheticPoseFactory.make_standing_pose(n_frames=n)


def _step_phase(n: int = 10) -> ElementPhase:
    return ElementPhase(
        name="three_turn",
        start=0,
        takeoff=0,
        peak=n // 2,
        landing=0,
        end=n - 1,
    )


def _run_with_se_override(se_series: np.ndarray | None = None) -> dict[str, float]:
    """Run `_analyze_step` with the spread-eagle angle series overridden.

    The override happens at the class level (BiomechanicsAnalyzer) so
    that the inline `se_angle = self.compute_spread_eagle_angle(poses)`
    call inside `_analyze_step` returns our NaN-contaminated series.
    The override series length must match the pose length.
    """
    from contextlib import contextmanager

    poses = _step_poses()
    n = len(poses)

    @contextmanager
    def _patch():
        # Capture the original staticmethod object from __dict__ (not
        # via attribute access, which unwraps it to a plain function).
        orig = BiomechanicsAnalyzer.__dict__["compute_spread_eagle_angle"]

        def fake(poses):
            return se_series if se_series is not None else orig.__func__(poses)

        BiomechanicsAnalyzer.compute_spread_eagle_angle = staticmethod(fake)
        try:
            yield
        finally:
            BiomechanicsAnalyzer.compute_spread_eagle_angle = orig

    with _patch():
        analyzer = BiomechanicsAnalyzer(_step_def())
        results = analyzer._analyze_step(poses, _step_phase(n), fps=30.0)
    return {r.name: r.value for r in results}


def _run_with_ib_override(ib_series: np.ndarray) -> dict[str, float]:
    """Run `_analyze_step` with the ina-bauer score series overridden."""
    from contextlib import contextmanager

    poses = _step_poses()
    n = len(poses)

    @contextmanager
    def _patch():
        orig = BiomechanicsAnalyzer.__dict__["compute_ina_bauer_score"]

        def fake(poses, se_angle=None):
            return ib_series

        BiomechanicsAnalyzer.compute_ina_bauer_score = staticmethod(fake)
        try:
            yield
        finally:
            BiomechanicsAnalyzer.compute_ina_bauer_score = orig

    with _patch():
        analyzer = BiomechanicsAnalyzer(_step_def())
        results = analyzer._analyze_step(poses, _step_phase(n), fps=30.0)
    return {r.name: r.value for r in results}


# --------------------------------------------------------------------------- #
# Observable 1: NaN frame in se_angle must not poison peak_se.
# --------------------------------------------------------------------------- #


def test_peak_se_nan_in_se_angle_finite():
    """One NaN in `se_angle` must not poison `peak_se` into NaN.

    Pre-#1275: `np.max([150, 155, NaN, 160, 158]) = NaN` -> peak_se = NaN
    -> MetricResult.value = NaN -> _is_bad triggers false-worst rule.
    Post-#1275: `np.nanmax` skips the NaN frame -> peak_se = 160.0.
    """
    by_name = _run_with_se_override(
        np.array([150.0, 155.0, np.nan, 160.0, 158.0, 152.0, 158.0, 159.0, 157.0, 156.0])
    )
    peak_se = by_name["spread_eagle_angle"]
    assert np.isfinite(peak_se), (
        f"BUG (#1275 MX): NaN in se_angle poisoned peak_se = {peak_se!r}. "
        f"np.max(NaN-array) is NaN. Use np.nanmax + np.isfinite fallback."
    )
    assert peak_se == 160.0, (
        f"BUG (#1275 MX): peak_se = {peak_se!r}, expected 160.0 (np.nanmax skips NaN frame)."
    )


# --------------------------------------------------------------------------- #
# Observable 2: NaN frame in ib_score must not poison peak_ib.
# --------------------------------------------------------------------------- #


def test_peak_ib_nan_in_ib_score_finite():
    """One NaN in `ib_score` must not poison `peak_ib` into NaN.

    Pre-#1275: `np.max(ib_score) = NaN` -> peak_ib = NaN -> cascading
    NaN in MetricResult chain.
    Post-#1275: `np.nanmax` skips the NaN frame -> peak_ib finite.
    """
    by_name = _run_with_ib_override(
        np.array([0.8, 0.9, np.nan, 0.85, 0.7, 0.6, 0.75, 0.82, 0.88, 0.71])
    )
    peak_ib = by_name["ina_bauer_score"]
    assert np.isfinite(peak_ib), (
        f"BUG (#1275 MX): NaN in ib_score poisoned peak_ib = {peak_ib!r}. "
        f"np.max(NaN-array) = NaN. Use np.nanmax + np.isfinite fallback."
    )


# --------------------------------------------------------------------------- #
# Observable 3: all-NaN se_angle -> 0.0 sentinel, not NaN.
# --------------------------------------------------------------------------- #


def test_peak_se_all_nan_returns_zero_sentinel():
    """All-NaN se_angle must yield peak_se = 0.0 (sentinel), not NaN.

    Pre-#1275: peak_se = NaN. JSON serialization of NaN breaks the GOE
    composite. Post-#1275: `np.isfinite(...).any() else 0.0` fallback.
    """
    by_name = _run_with_se_override(np.full(10, np.nan))
    peak_se = by_name["spread_eagle_angle"]
    assert peak_se == 0.0, (
        f"BUG (#1275 MX): all-NaN se_angle yielded peak_se = {peak_se!r}, "
        f"expected 0.0 sentinel (no data)."
    )


# --------------------------------------------------------------------------- #
# Regression: clean (all-finite) input must not change.
# --------------------------------------------------------------------------- #


def test_peak_se_clean_input_unchanged():
    """All-finite se_angle must yield correct peak_se (regression guard).

    np.nanmax is identity on all-finite input. The fix must not corrupt
    the happy path.
    """
    by_name = _run_with_se_override(
        np.array([150.0, 155.0, 160.0, 158.0, 152.0, 156.0, 159.0, 158.0, 157.0, 153.0])
    )
    assert by_name["spread_eagle_angle"] == 160.0, (
        f"BUG (regression): clean se_angle yielded peak_se = "
        f"{by_name['spread_eagle_angle']!r}, expected 160.0 (max of input)."
    )


# --------------------------------------------------------------------------- #
# Source check: peak aggregations use np.nanmax + isfinite fallback.
# Locks the GREEN contract at the source.
# --------------------------------------------------------------------------- #


def test_source_peak_aggregations_use_nanmax():
    """GREEN contract source check: peak_se / peak_ib / max_spiral use
    `np.nanmax` + `np.isfinite(...).any() else 0.0` idiom (mirrors #912
    peak_velocity path). Bare `np.max` is locked out at the source.
    """
    from pathlib import Path

    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "metrics.py"
    text = src_path.read_text(encoding="utf-8")

    # Each peak site must use nanmax with an isfinite fallback to 0.0.
    import re

    for name in ("peak_se", "peak_ib", "max_spiral"):
        # Locate the line that computes this peak (with leading indent).
        m = re.search(rf"^\s*{name}\s*=.*$", text, re.MULTILINE)
        assert m, f"Could not locate `{name} = ...` in metrics.py"
        line = m.group(0)
        assert "np.nanmax" in line, (
            f"BUG (#1275 MX): `{name}` uses bare np.max at `{line!r}`. "
            f"NaN frames will silently propagate. Use `np.nanmax(...) if "
            f"np.isfinite(...).any() else 0.0` (mirrors #912 peak_velocity)."
        )
