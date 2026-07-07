"""RED repro — `compute_subscores` (ml/src/analysis/multi_score.py) inflates
a subscore to 10.0 (PERFECT) when a contributed metric is non-finite (NaN or
inf). #850 added a `math.isnan` guard in `_normalize` that catches NaN, but
`math.isnan(float('inf'))` is False, so an inf metric still passes through
`max(0.0, min(1.0, inf)) = 1.0` → subscore 10.0 → inflated `overall` →
false gamification skill unlock (silver 6.5 / gold 8.0 threshold). This is
the same #454 arg-order / non-finite family as #978 (`compute_goe_score`),
which was fixed with `np.nan_to_num` / `np.isfinite` (catches both NaN AND
inf). #850's `math.isnan` is the incomplete sibling — it leaves inf leaking
to PERFECT.

Contract: a non-finite metric (NaN or inf) must NOT silently clamp to 1.0
(perfect) at the `_normalize` cap. A missing / broken metric must yield 0.0
(neutral / worst), never 1.0 (perfect) and never NaN. Mirror #978's
`np.isfinite` / `np.nan_to_num` pattern at the cap site so both NaN and inf
are guarded.

Pure-Python (no GPU, no DB): `compute_subscores` is a pure-data function
over a metrics dict. Non-finite metrics are injected directly — defense in
depth: the cap site must be safe regardless of its input source.
"""

from __future__ import annotations

import inspect

import numpy as np

from ml.src.analysis.multi_score import _normalize, compute_subscores

# ponytail: shared finite baseline — every NaN/inf test mutates one key, so a
# single mutation reliably localizes inflation to the touched subscore.
_BASE_FINITE = {
    "airtime": 0.5,
    "relative_jump_height": 0.4,
    "approach_direction_change": 5.0,
    "rotation_speed": 360.0,
    "total_rotation_deg": 1080.0,
    "under_rotation_deg": 10.0,
    "arm_position_score": 0.7,
    "symmetry": 0.6,
    "landing_knee_angle": 110.0,
    "landing_knee_stability": 0.7,
    "landing_smoothness": 0.6,
    "hard_landing": 0.8,
    "landing_trunk_recovery": 0.7,
    "approach_torso_lean": 5.0,
    "trunk_lean": 5.0,
}


def _subscore(score, name: str):
    return next(s for s in score.subscores if s.name == name)


# --------------------------------------------------------------------------- #
# Observable 1: a NaN metric must NOT inflate its subscore to 10.0 (perfect).
# #850 closed the NaN path; this is the regression lock.
# --------------------------------------------------------------------------- #


def test_nan_airtime_does_not_inflate_takeoff_to_perfect_repro():
    """#924: NaN airtime must NOT push takeoff_power to the 10.0 ceiling via
    NaN→1.0 clipping. Missing metric → 0.0 (neutral), not 10.0 (perfect)."""
    nan = float("nan")
    metrics = dict(_BASE_FINITE, airtime=nan)
    score = compute_subscores(metrics)
    takeoff = _subscore(score, "takeoff_power")
    assert takeoff.value != 10.0, (
        f"#924 RED: takeoff_power={takeoff.value} — NaN airtime inflated "
        "subscore to 10.0 (perfect) via NaN→1.0 clip."
    )
    assert np.isfinite(takeoff.value), (
        f"#924: takeoff_power={takeoff.value} leaked NaN/inf into the subscore."
    )


# --------------------------------------------------------------------------- #
# Observable 2: an INF metric must NOT inflate its subscore to 10.0. #850's
# `math.isnan` guard misses inf — `math.isnan(inf)=False` → inf passes through
# `min(1.0, inf)=1.0` → subscore 10.0. This is the #924 RED path.
# --------------------------------------------------------------------------- #


def test_inf_airtime_does_not_inflate_takeoff_to_perfect_repro():
    """#924 RED: inf airtime must NOT push takeoff_power to 10.0 (perfect).
    `math.isnan(inf)=False`, so #850's guard lets inf through to
    `min(1.0, inf)=1.0` → 10.0. Mirror #978: use `np.isfinite`/`np.nan_to_num`
    (catches NaN AND inf) at the cap site."""
    inf = float("inf")
    metrics = dict(_BASE_FINITE, airtime=inf)
    score = compute_subscores(metrics)
    takeoff = _subscore(score, "takeoff_power")
    assert takeoff.value != 10.0, (
        f"#924 RED: takeoff_power={takeoff.value} — inf airtime inflated "
        "subscore to 10.0 (perfect) via inf→1.0 clip (math.isnan misses inf)."
    )
    assert np.isfinite(takeoff.value), (
        f"#924: takeoff_power={takeoff.value} leaked NaN/inf into the subscore."
    )


def test_inf_rotation_speed_does_not_inflate_rotation_to_perfect_repro():
    """#924 RED: inf rotation_speed must NOT push rotation_axis to 10.0.
    `min(inf/720, 1.0)=1.0` → `_normalize(1.0)=1.0` → 10.0. Inf must be
    treated as missing (0.0), not perfect."""
    inf = float("inf")
    metrics = dict(_BASE_FINITE, rotation_speed=inf)
    score = compute_subscores(metrics)
    rotation = _subscore(score, "rotation_axis")
    assert rotation.value != 10.0, (
        f"#924 RED: rotation_axis={rotation.value} — inf rotation_speed "
        "inflated subscore to 10.0 (perfect)."
    )
    assert np.isfinite(rotation.value), f"#924: rotation_axis={rotation.value} leaked NaN/inf."


# --------------------------------------------------------------------------- #
# Observable 3: all-non-finite metrics — defined behavior, no crash, no silent
# 10.0, no NaN/inf in overall. Missing session must score low, not perfect.
# --------------------------------------------------------------------------- #


def test_all_non_finite_metrics_not_perfect_no_crash_repro():
    """#924: a session where every metric is non-finite (NaN/inf mix) must
    not crash, must not yield overall=10.0, and must not leak NaN/inf into
    overall. A broken session must NOT farm max XP / gold skills."""
    nan = float("nan")
    inf = float("inf")
    metrics = {
        "airtime": nan,
        "relative_jump_height": inf,
        "approach_direction_change": nan,
        "rotation_speed": inf,
        "total_rotation_deg": nan,
        "under_rotation_deg": inf,
        "arm_position_score": nan,
        "symmetry": inf,
        "landing_knee_angle": nan,
        "landing_knee_stability": inf,
        "landing_smoothness": nan,
        "hard_landing": inf,
        "landing_trunk_recovery": nan,
        "approach_torso_lean": inf,
        "trunk_lean": nan,
    }
    score = compute_subscores(metrics)
    assert np.isfinite(score.overall), (
        f"#924: all-non-finite → overall={score.overall} leaked NaN/inf."
    )
    assert score.overall < 10.0, (
        f"#924 RED: all-non-finite metrics → overall={score.overall} "
        "(perfect 10.0) — broken session farms max XP + gold skills."
    )
    for s in score.subscores:
        assert s.value < 10.0, (
            f"#924 RED: subscore {s.name}={s.value} — non-finite metric clipped to 1.0 → 10.0."
        )
        assert np.isfinite(s.value), f"#924: subscore {s.name}={s.value} leaked NaN/inf."


# --------------------------------------------------------------------------- #
# Observable 4: finite metrics unchanged (regression — the guard must not
# perturb the clean baseline).
# --------------------------------------------------------------------------- #


def test_finite_metrics_subscores_unchanged_repro():
    """#924 regression: the finite baseline must produce the same subscores
    before and after the inf guard — the guard only affects non-finite
    inputs."""
    score = compute_subscores(dict(_BASE_FINITE))
    for s in score.subscores:
        assert 0.0 <= s.value <= 10.0, (
            f"#924: finite baseline subscore {s.name}={s.value} out of [0,10]."
        )
        assert np.isfinite(s.value), (
            f"#924: finite baseline subscore {s.name}={s.value} not finite."
        )
    assert np.isfinite(score.overall) and 0.0 <= score.overall <= 10.0


# --------------------------------------------------------------------------- #
# Source-asserting: `_normalize` must guard non-finite (NaN AND inf) before
# the clamp — root-cause lock. `math.isnan` alone is insufficient (misses
# inf); require `isfinite` / `nan_to_num` / `isfinite`-equivalent.
# --------------------------------------------------------------------------- #


def test_normalize_source_guards_non_finite_repro():
    """#924 GREEN: `_normalize` source must guard non-finite (NaN AND inf)
    before the `min(1.0, ...)` cap. `math.isnan` alone misses inf — require
    `isfinite` / `nan_to_num` (handles both)."""
    src = inspect.getsource(_normalize)
    assert "isfinite" in src or "nan_to_num" in src, (
        "#924: _normalize guards NaN only (math.isnan) — inf still leaks to "
        "min(1.0, inf)=1.0 → 10.0. Use math.isfinite / np.nan_to_num to guard "
        "both NaN and inf before the cap (mirror #978 compute_goe_score)."
    )


def test_normalize_inf_is_neutral_zero_repro():
    """#924 RED: `_normalize(float('inf'))` must be 0.0 (missing = neutral),
    not 1.0 (perfect). `math.isnan(inf)=False` → inf passes through
    `min(1.0, inf)=1.0` → 1.0 (PERFECT)."""
    val = _normalize(float("inf"))
    assert val == 0.0, (
        f"#924 RED: _normalize(inf)={val} — inf clips to 1.0 (perfect), "
        "should be 0.0 (neutral). math.isnan misses inf; use isfinite."
    )
