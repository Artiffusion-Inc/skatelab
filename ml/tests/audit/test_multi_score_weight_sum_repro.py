"""RED repro — multi_score weights sum to 1.05, not 1.0 → perfect session overall=10.5 (#512).

multi_score.py:95-96:
    weights = [0.30, 0.25, 0.15, 0.25, 0.10]   # sum = 1.05, NOT 1.0
    overall = sum(s.value * w for s, w in zip(subscores, weights, strict=True))

For a perfect session where all 5 subscores hit their 10.0 ceiling,
overall = 10 * 1.05 = 10.5, exceeding the documented /10 maximum.

Prod impact (HIGH):
- Gamification check_skill_unlocks uses score >= 8.0 (gold). A true 7.62
  session inflates to 8.0 → premature gold skill unlock (300 XP + jumps_gold).
- Display renders "10.5 / 10" (above max).
- Same economy #437 corrected (XP 10x); now re-broken via weight-sum vector.

Bug class: weight-vector-sum-not-1.0 / score-deflation-inversion (#432-class at
the composition site — perfect input exceeds the ceiling instead of being
capped). Fix: normalize the weighted sum by the weight total, OR correct the
weight values to sum to 1.0. Normalization preserves the relative balance and
guarantees overall <= 10.0 regardless of the weight vector.

This test MUST fail (RED) against the current code. Repro, not a fix.
"""

from src.analysis.multi_score import compute_subscores


def _perfect_metrics() -> dict[str, float]:
    """Metrics at ideal maxima so every subscore evaluates to 1.0 → value 10.0.

    Derived from multi_score.py:23-55:
      takeoff:  airtime=0.7 (0.7/0.7*0.4=0.4), relative_jump_height=1.0
                (1.0/1.0*0.4=0.4), approach_consistency=0 ((1-0/90)*0.2=0.2) → 1.0
      rotation: rotation_speed=720 (min(720/720,1)*0.4=0.4),
                total_rotation_deg=1620 (min(1620/1620,1)*0.3=0.3),
                under_rotation_deg=0 ((1-0/90)*0.3=0.3) → 1.0
      arms:     arm_position_score=1.0 (*0.6), symmetry=1.0 (*0.4) → 1.0
      landing:  landing_knee_angle=110 ((1-0/40)*0.3=0.3),
                landing_knee_stability=1.0 (*0.3), landing_smoothness=1.0 (*0.2),
                hard_landing=1.0 (*0.2) → 1.0
      core:     landing_trunk_recovery=1.0 (*0.5), approach_torso_lean=0
                ((1-0/20)*0.25=0.25), trunk_lean=0 ((1-0/20)*0.25=0.25) → 1.0
    """
    return {
        "airtime": 0.7,
        "relative_jump_height": 1.0,
        "approach_consistency": 0.0,
        "rotation_speed": 720.0,
        "total_rotation_deg": 1620.0,
        "under_rotation_deg": 0.0,
        "arm_position_score": 1.0,
        "symmetry": 1.0,
        "landing_knee_angle": 110.0,
        "landing_knee_stability": 1.0,
        "landing_smoothness": 1.0,
        "hard_landing": 1.0,
        "landing_trunk_recovery": 1.0,
        "approach_torso_lean": 0.0,
        "trunk_lean": 0.0,
    }


def test_perfect_session_overall_does_not_exceed_ceiling():
    """A perfect session (all subscores 10.0) must NOT exceed the /10 max.
    RED now: overall = 10 * 1.05 = 10.5.
    """
    result = compute_subscores(_perfect_metrics())

    # Sanity: every subscore must be at its 10.0 ceiling (confirms the metrics
    # dict drives each subscore to 1.0; the test cannot pass for the wrong reason).
    for s in result.subscores:
        assert abs(s.value - 10.0) < 1e-9, (
            f"test fixture broken: subscore '{s.name}' = {s.value}, expected 10.0 "
            f"(perfect metrics must drive every subscore to its ceiling)."
        )

    assert result.overall <= 10.0, (
        f"BUG #512: perfect-session overall = {result.overall}, exceeds the /10 "
        f"ceiling. multi_score.py:95 weights [0.30,0.25,0.15,0.25,0.10] sum to "
        f"1.05, so 10.0 * 1.05 = 10.5. Gamification check_skill_unlocks "
        f"(score>=8.0 gold) crosses early; display renders '10.5 / 10'. "
        f"Fix: normalize the weighted sum by the weight total (preserve relative "
        f"balance, guarantee overall <= 10.0)."
    )


def test_weights_sum_to_one():
    """The effective weight total must be 1.0 so overall stays in [0, 10].

    RED now: weights sum to 1.05. We assert via the ratio of a perfect-session
    overall to the per-subscore ceiling (10.0): with weights summing to 1.0,
    overall/10.0 == 1.0; with 1.05 it is 1.05.
    """
    result = compute_subscores(_perfect_metrics())
    weight_total = result.overall / 10.0  # overall = 10 * weight_total
    assert abs(weight_total - 1.0) < 1e-9, (
        f"BUG #512: effective weight total = {weight_total}, expected 1.0. "
        f"multi_score.py:95 weights sum to 1.05 (not 1.0) → perfect-session "
        f"overall = {result.overall} (10 * {weight_total})."
    )
