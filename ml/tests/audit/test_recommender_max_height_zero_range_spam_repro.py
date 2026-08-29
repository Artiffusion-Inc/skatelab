"""Repro tests — recommender force-fires on max_height with sentinel (0,0) range (#856).

``_analyze_jump`` (metrics.py:202) creates ``max_height`` with
``reference_range=(0, 0)``. ``analyze`` overrides the range ONLY for metrics in
``element_def.ideal_metrics``. ``toe_loop`` and ``flip`` deliberately omit
``max_height`` (they use ``relative_jump_height``), so ``max_height`` keeps the
sentinel ``(0, 0)``.

The recommender's shared ``_COMMON_JUMP_RULES`` has a ``max_height`` rule
applied to every jump. ``_is_bad(value, (0, 0))`` = ``not (0 <= value <= 0)`` =
True for any ``value != 0`` → the rule fires on every real jump, spamming
«Следи за высотой прыжка.» for a normal height. ``is_good`` stays False too
(the override loop skips metrics outside ideal_metrics).

Fix (#856, option b): a ``reference_range`` of ``(0, 0)`` means "no ideal range
defined for this element" — the recommender must skip such metrics instead of
force-firing, and ``is_good`` must not be left False (no data = neutral, not bad).
"""

from __future__ import annotations

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.analysis.recommender import Recommender
from src.types import ElementPhase, MetricResult


def _metric(
    name: str, value: float, ref: tuple[float, float], is_good: bool = False
) -> MetricResult:
    return MetricResult(name=name, value=value, unit="norm", is_good=is_good, reference_range=ref)


def test_toe_loop_normal_height_does_not_spam_max_height_rec_repro():
    """#856: a normal max_height with sentinel (0,0) must not fire a recommendation."""
    rec = Recommender()
    # Normal single-rotation height; toe_loop has no max_height ideal_metrics → (0,0).
    metric = _metric("max_height", 0.1735, (0, 0))
    recs = rec.recommend([metric], "toe_loop")
    height_recs = [r for r in recs if ("высот" in r or "высок" in r)]
    assert not height_recs, (
        f"#856 RED: toe_loop normal height (0.1735) with sentinel (0,0) spammed "
        f"{height_recs} — _is_bad((0,0)) is True for any nonzero value, the shared "
        "rule force-fires. Sentinel (0,0) means 'no range defined' → skip."
    )


def test_flip_normal_height_does_not_spam_max_height_rec_repro():
    """#856: same for flip (also omits max_height from ideal_metrics)."""
    rec = Recommender()
    metric = _metric("max_height", 0.1735, (0, 0))
    recs = rec.recommend([metric], "flip")
    height_recs = [r for r in recs if ("высот" in r or "высок" in r)]
    assert not height_recs, (
        f"#856 RED: flip normal height (0.1735) with sentinel (0,0) spammed {height_recs}."
    )


def test_real_range_still_fires_when_bad_repro():
    """#856 regression guard: a real (non-sentinel) range still fires when the value is bad."""
    rec = Recommender()
    # salchow max_height would have a real range; low value below it must fire.
    metric = _metric("max_height", 0.05, (0.15, 0.4))
    recs = rec.recommend([metric], "salchow")
    height_recs = [r for r in recs if ("высот" in r or "высок" in r)]
    assert height_recs, (
        "#856: real range (0.15, 0.4) with low value 0.05 must still fire — the "
        "sentinel skip must not suppress legitimately-bad metrics."
    )


def test_toe_loop_analyze_max_height_is_good_not_false_repro():
    """#856: BiomechanicsAnalyzer.analyze for toe_loop must not leave max_height.is_good=False.

    A metric with no ideal range for the element is not 'bad' — there is no data
    to judge it. Downstream (multi_score subscores, GOE) reads is_good and would
    treat a normal height as a defect.
    """
    analyzer = BiomechanicsAnalyzer(get_element_def("toe_loop"))
    # Minimal poses: build a synthetic jump so analyze() runs the jump path.
    import numpy as np

    n = 30
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    com_y = 0.5 - np.sin(np.linspace(0, np.pi, n)) * 0.2  # Y-down: peak = min y
    poses[:, :, 0] = 0.5
    poses[:, :, 1] = com_y[:, None]
    phases = ElementPhase(name="toe_loop", start=0, takeoff=5, peak=15, landing=25, end=n)
    results = analyzer.analyze(poses, phases, fps=30.0)
    max_height = next((r for r in results if r.name == "max_height"), None)
    assert max_height is not None, "#856: max_height metric not produced by analyze()."
    assert max_height.is_good is not False, (
        f"#856 RED: toe_loop max_height.is_good={max_height.is_good} with "
        f"reference_range={max_height.reference_range} — a metric the element def "
        "does not bond to an ideal range is left flagged 'bad', lying to downstream."
    )
