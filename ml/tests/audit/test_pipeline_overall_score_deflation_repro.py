"""RED repro: ML pipeline _compute_overall_score deflated by unregistered descriptive metrics.

Bug (#432-class at ML pipeline composition site, NOT the fixed session_saver #432):
  ml/src/pipeline.py:608-629 _compute_overall_score computes
    score = (good_count / total_count) * 10
  over ALL metrics returned by BiomechanicsAnalyzer.analyze. But that list mixes
    (a) REGISTERED metrics   — in element_def.ideal_metrics -> is_good set from range
    (b) UNREGISTERED metrics — total_rotation_deg, rotation_count, rotation_discrepancy,
        under_rotation_deg, jump_type — no ideal range. They keep their init
        is_good=False + reference_range=(0,0) (metrics.py:197/209...). The goodness
        loop at metrics.py:162-167 only updates metrics whose name is in
        element_def.ideal_metrics, never touching the unregistered ones.

  => every unregistered descriptive metric permanently counts as BAD in BOTH
     numerator and denominator, deflating the score.

  waltz_jump returns 21 metrics (16 registered + 5 unregistered). A perfect
  execution (all 16 registered good) -> good_count=16, total_count=21 ->
  score = 16/21*10 = 7.6, NOT 10.0. ~24% deflation.

This feeds backend session_saver + gamification XP (#437 was a 10x scale mismatch
on this same score — a deflated base compounds the gamification error). The
existing #432 fix lived in backend/app/session_saver.py and did NOT touch
pipeline.py:608 — this is an independent composition site.

Existing test test_pipeline.py::test_compute_overall_score uses all-good /
all-bad / 1-bad metrics with EXPLICIT non-zero reference_range and never mixes
registered (non-zero range) with unregistered ((0,0) sentinel) — that is the gap.

Pure-Python, no GPU/ONNX: the method only reads .is_good and len(metrics), so a
list of MetricResult stand-ins is a faithful repro of the production composition.
"""

from src.pipeline import AnalysisPipeline
from src.types import MetricResult


def _make(name, value, is_good, ref_range, unit="s"):
    return MetricResult(
        name=name,
        value=value,
        unit=unit,
        is_good=is_good,
        reference_range=ref_range,
    )


def test_compute_overall_score_excludes_unregistered_descriptive_metrics():
    """Perfect registered execution must score 10.0, not be capped by unregistered descriptives.

    Mimics BiomechanicsAnalyzer.analyze('waltz_jump') output composition:
    16 registered metrics (is_good=True, non-zero ideal range from ideal_metrics)
    + 5 unregistered descriptive metrics (is_good=False, reference_range=(0,0) —
    the sentinel for "no ideal range, not gradable"; metrics.py:162-167 leaves
    them untouched). _compute_overall_score must EXCLUDE the unregistered from
    both good_count and total_count. It currently does NOT — it counts them as
    BAD in the denominator -> 16/21*10 = 7.6 instead of 10.0.
    """
    pipeline = AnalysisPipeline()

    # 16 registered metrics (matches waltz_jump ideal_metrics keys), all GOOD.
    registered = [
        _make("airtime", 0.5, True, (0.3, 0.7)),
        _make("max_height", 0.3, True, (0.2, 0.5)),
        _make("landing_knee_angle", 90, True, (70, 110), unit="deg"),
        _make("arm_position_score", 0.8, True, (0.6, 1.0)),
        _make("takeoff_angle", 78, True, (70, 85), unit="deg"),
        _make("landing_knee_stability", 0.8, True, (0.5, 1.0)),
        _make("landing_trunk_recovery", 0.8, True, (0.5, 1.0)),
        _make("relative_jump_height", 0.9, True, (0.3, 1.5)),
        _make("rotation_speed", 180, True, (0, 360), unit="deg/s"),
        _make("landing_com_velocity", -1.0, True, (-2.0, 0.0)),
        _make("landing_smoothness", 0.8, True, (0.5, 1.0)),
        _make("approach_torso_lean", 5, True, (-30, 30), unit="deg"),
        _make("approach_direction_change", 30, True, (0, 90), unit="deg"),
        _make("symmetry", 0.9, True, (0.6, 1.0)),
        _make("toe_assist_proxy", 0.8, True, (0.5, 1.0)),
        _make("hard_landing", 0.8, True, (0.5, 1.0)),
        # goe_score registered too (ideal_metrics includes it) — include for 17th reg
        _make("goe_score", 7.5, True, (5.0, 10.0)),
    ]

    # 5 unregistered descriptive metrics — no ideal range, sentinel (0,0).
    # metrics.py:162-167 goodness loop only touches metrics in ideal_metrics,
    # so these keep init is_good=False + reference_range=(0,0).
    unregistered = [
        _make("total_rotation_deg", 180, False, (0, 0), unit="deg"),
        _make("rotation_count", 1, False, (0, 0)),
        _make("rotation_discrepancy", 0.0, False, (0, 0), unit="deg"),
        _make("under_rotation_deg", 0.0, False, (0, 0), unit="deg"),
        _make("jump_type", 0, False, (0, 0)),
    ]

    metrics = registered + unregistered  # 22 total: 17 registered + 5 unregistered
    score = pipeline._compute_overall_score(metrics)

    assert score == 10.0, (
        f"BUG: _compute_overall_score deflated by unregistered descriptive "
        f"metrics (is_good=False, reference_range=(0,0)) counted as BAD in the "
        f"denominator — perfect registered execution caps below 10.0 "
        f"(got {score}, expected 10.0). #432-class at ML pipeline composition "
        f"site (pipeline.py:608), NOT the fixed session_saver. "
        f"good_count=17, total_count=22 -> 17/22*10={17 / 22 * 10:.1f} (deflation)."
    )


def test_compute_overall_score_zero_range_is_unregistered_sentinel():
    """reference_range==(0,0) is the unregistered-metric sentinel — must not count as BAD.

    A metric with reference_range=(0,0) is by construction unregistered (no
    ideal_metrics entry uses (0,0) as a legit range — every ideal range in
    element_defs.py has min_good < max_good for at least one metric, and the
    init (0,0) is the "not graded" marker). Counting it as BAD deflates every
    jump analysis. Minimal 2-metric repro: one registered good + one (0,0).
    """
    pipeline = AnalysisPipeline()

    metrics = [
        _make("airtime", 0.5, True, (0.3, 0.7)),  # registered good
        _make("jump_type", 0, False, (0, 0)),  # unregistered descriptive sentinel
    ]
    score = pipeline._compute_overall_score(metrics)

    assert score == 10.0, (
        f"BUG: unregistered descriptive (reference_range=(0,0)) counted as BAD -> "
        f"score {score} != 10.0. Perfect registered execution should not be "
        f"deflated by non-gradable descriptive metrics."
    )
