"""RED repro — `estimated_score` is declared in metrics_registry but ML never
emits it. Phantom metric → /metrics/trend?metric=estimated_score always empty.
The real ML metric `goe_score` is orphaned (rejected 400 "Unknown metric").
Cross-layer name-contract mismatch (#498 sibling).

BUG #3 (MEDIUM — cross-layer name-contract / phantom-registry-metric,
        #498 sibling):
    backend/app/metrics_registry.py:294  declares
        MetricDef(name="estimated_score", ideal_range=(0,20), direction="higher")
    ml/src/analysis/metrics.py:360  emits
        MetricResult(name="goe_score", value=goe, unit="score")   # NOT estimated_score
    grep `MetricResult(name="estimated_score")` in ml/src = 0 emit sites.

    backend/app/routes/metrics.py:108  /metrics/trend validity check:
        `mdef = METRIC_REGISTRY.get(metric_name); if not mdef: raise 400`
        → /metrics/trend?metric=estimated_score passes (in registry) but
        returns 0 data points (ML never writes it) → always-empty chart.
        → /metrics/trend?metric=goe_score → 400 "Unknown metric" (not in
        registry) → the real ML metric is orphaned in DB, unreachable via API.

    frontend personal-records.tsx:42 reads the registry dynamically →
    estimated_score appears in the UI but never has a PR/trend.

This test asserts the registry metric names are a SUBSET of the ML-emitted
metric names (cross-layer contract). Currently `estimated_score` is in the
registry but NOT ML-emitted → phantom set non-empty → RED.

This is a static-contract assertion (registry vs ML-emit sites), deterministic
without GPU: it reads the registry and the set of names metrics.py emits
(harvested from the source via the analyzer's emit surface — the same set
the analyzer produces on any synthetic input).
"""

from app.metrics_registry import METRIC_REGISTRY

# Names ml/src/analysis/metrics.py actually emits as MetricResult(name=...).
# Harvested from the source (grep `MetricResult(` then `name=`). This is the
# complete emit surface of BiomechanicsAnalyzer — the dict keys a real
# _metrics_to_dict build produces.
ML_EMITTED_METRIC_NAMES: frozenset[str] = frozenset(
    {
        "airtime",
        "approach_direction_change",
        "approach_torso_lean",
        "arm_position_score",
        "edge_change_smoothness",
        "goe_score",
        "hard_landing",
        "ina_bauer_score",
        "jump_type",
        "knee_angle",
        "landing_com_velocity",
        "landing_knee_angle",
        "landing_knee_stability",
        "landing_smoothness",
        "landing_trunk_recovery",
        "max_height",
        "relative_jump_height",
        "rotation_count",
        "rotation_discrepancy",
        "rotation_speed",
        "spin_peak_velocity",
        "spin_type",
        "spiral_indicator",
        "spread_eagle_angle",
        "symmetry",
        "toe_assist_proxy",
        "total_rotation_deg",
        "trunk_lean",
        "under_rotation_deg",
    }
)


def test_registry_metrics_are_ml_emitted():
    """Every metric in the registry MUST be emitted by the ML pipeline.
    Currently `estimated_score` is declared in the registry
    (metrics_registry.py:294) but ML emits `goe_score` (metrics.py:360)
    instead — `estimated_score` has 0 emit sites in ml/src. Registry names
    ⊄ ML-emitted names → phantom set contains estimated_score → RED.
    """
    registry_names = {m.name for m in METRIC_REGISTRY.values()}
    phantom = registry_names - ML_EMITTED_METRIC_NAMES

    assert "estimated_score" not in phantom, (
        f"BUG: estimated_score is in metrics_registry (metrics_registry.py:294) "
        f"but ML never emits it (grep MetricResult(name=estimated_score) in "
        f"ml/src = 0; ML emits goe_score at metrics.py:360 instead). "
        f"/metrics/trend?metric=estimated_score passes the registry validity "
        f"check (routes/metrics.py:108) but returns 0 data points — always "
        f"empty chart. /metrics/trend?metric=goe_score → 400 'Unknown metric' "
        f"(not in registry) → real ML metric orphaned in DB, unreachable via "
        f"API. frontend personal-records.tsx:42 reads the registry dynamically "
        f"→ estimated_score appears in UI with no PR/trend. Cross-layer "
        f"name-contract mismatch (#498 sibling). Full phantom set: {phantom}."
    )
