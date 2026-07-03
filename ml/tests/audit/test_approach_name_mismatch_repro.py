"""RED repro — multi_score reads `approach_consistency` but ML emits
`approach_direction_change`. Cross-layer name-contract mismatch → takeoff_power
term CONSTANT (always 0.2) → inflates bad approaches, ignores creative ones,
affects overall_score + gamification XP.

BUG #1 (HIGH — cross-layer name-contract mismatch, #498 sibling):
    ml/src/analysis/metrics.py:348  emits
        MetricResult(name="approach_direction_change", value=approach_curve, unit="deg")
    ml/src/analysis/multi_score.py:26  reads
        metrics.get("approach_consistency", 0)   # WRONG name → always 0
    takeoff_power term (multi_score.py:26):
        (1 - abs(metrics.get("approach_consistency", 0)) / 90) * 0.2
        = (1 - abs(0)/90) * 0.2 = 0.2   CONSTANT for every jump

    Prod flow: worker.py:497 → analyzer_save._metrics_to_dict builds a dict
    keyed `approach_direction_change` (the ML emit name) → compute_subscores
    reads `approach_consistency` (the multi_score read name) → 0 → term
    constant 0.2. A 60-degree creative approach and a 0-degree straight
    approach score IDENTICAL takeoff_power.

    Existing test_multi_score.py:30 feeds `approach_consistency` directly
    (a fake key ML NEVER produces) — masking the mismatch. The real ML
    metrics dict has `approach_direction_change`, never `approach_consistency`.

This test builds metrics dicts with the REAL ML key name
(`approach_direction_change`) at 60deg vs 0deg and asserts takeoff_power
DIFFERS. Currently takeoff_power is IDENTICAL (approach_consistency always 0)
→ RED.
"""

from ml.src.analysis.multi_score import compute_subscores


def _takeoff_power(metrics: dict) -> float:
    """Extract the takeoff_power subscore value."""
    score = compute_subscores(metrics)
    sub = next(s for s in score.subscores if s.name == "takeoff_power")
    return sub.value


# Real ML metric dict keys (the names metrics.py actually emits). Only the
# keys multi_score.get() reads need to be populated; the rest are included
# to mirror a real jump metrics dict.
_BASE = {
    "airtime": 0.5,
    "relative_jump_height": 0.4,
    "rotation_speed": 450,
    "total_rotation_deg": 720,
    "under_rotation_deg": 30,
    "arm_position_score": 0.7,
    "symmetry": 0.75,
    "landing_knee_angle": 110,
    "landing_knee_stability": 0.8,
    "landing_smoothness": 0.6,
    "hard_landing": 0.2,
    "landing_trunk_recovery": 0.9,
    "approach_torso_lean": 5,
    "trunk_lean": 10,
}


def test_takeoff_power_responds_to_approach_direction_change():
    """takeoff_power MUST differ between a 60deg creative approach and a 0deg
    straight approach. ML emits `approach_direction_change`
    (metrics.py:348); multi_score reads `approach_consistency`
    (multi_score.py:26) — a name it never finds → always 0 → the
    `(1 - abs(x)/90) * 0.2` term is constant 0.2 → takeoff_power IDENTICAL
    for both. RED.
    """
    # ML emits `approach_direction_change` (metrics.py:348), NOT
    # `approach_consistency` (the key multi_score.py:26 reads).
    metrics_creative = dict(_BASE, approach_direction_change=60.0)
    metrics_straight = dict(_BASE, approach_direction_change=0.0)

    tp_creative = _takeoff_power(metrics_creative)
    tp_straight = _takeoff_power(metrics_straight)

    assert tp_creative != tp_straight, (
        f"BUG: takeoff_power IDENTICAL ({tp_creative} == {tp_straight}) for "
        f"approach_direction_change=60 vs =0. ML emits name "
        f"`approach_direction_change` (metrics.py:348) but multi_score.py:26 "
        f"reads `metrics.get('approach_consistency', 0)` — WRONG name, always "
        f"0. The takeoff_power term `(1 - abs(0)/90) * 0.2 = 0.2` is CONSTANT "
        f"→ doesn't respond to approach variability → inflates bad approaches "
        f"(free 0.2), ignores creative approaches (40+ deg). Affects "
        f"MultiDimensionalScore.overall → SessionScore.overall → "
        f"award_session_xp. Cross-layer name-contract mismatch (#498 "
        f"name-mismatch sibling of the #432 deflation class). Existing "
        f"test_multi_score.py:30 feeds `approach_consistency` directly (a fake "
        f"key ML never produces), masking the bug."
    )
