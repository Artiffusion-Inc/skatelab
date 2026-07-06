"""RED repro — `BiomechanicsAnalyzer.compute_arm_position`
(ml/src/analysis/metrics.py:1111) silently returns a FALSE-GOOD 0.0 score when
a wrist or shoulder keypoint is NaN — `max(0, 1 - nan)` clamps to 0.0 (the
Python `max` NaN-arg-order trap, ticket #454), which is the BEST possible
arm-position score ("arms close to body, good for jumps"). A NaN occlusion
becomes a perfect-arm-position reward, not a degraded/flagged metric.

Root cause (ml/src/analysis/metrics.py:1111-1126):
  `compute_arm_position` computes the wrist-to-shoulder distance with NO NaN
  guard:
    line 1119: `left_dist = np.linalg.norm(poses[:, LWRIST] - poses[:, LSHOULDER], axis=1)`
    line 1120: `right_dist = np.linalg.norm(poses[:, RWRIST] - poses[:, RSHOULDER], axis=1)`
    line 1122: `avg_dist = float(np.mean(left_dist + right_dist) / 2)`
    line 1124: `return float(max(0, 1 - avg_dist))`
  With NaN in a wrist or shoulder on ANY frame: `np.linalg.norm` of a
  NaN-containing diff = NaN → `left_dist`/`right_dist` contain NaN →
  `np.mean(... + NaN ...)` = NaN → `avg_dist` = NaN → `1 - NaN` = NaN →
  `max(0, 1 - NaN)` = 0.0 (the Python `max` NaN-arg-order trap, #454:
  `max(0, nan)` returns the first arg `0`, NOT NaN). The `max(0, ...)` clamp
  was meant to floor NEGATIVE scores at 0 (arms very far), but it ALSO floors
  NaN at 0 — silently turning an occlusion into the BEST score.

  The metric has NO NaN check: it does not `np.isnan`-mask the distances, does
  not `np.nanmean`, does not return a NaN sentinel or a degraded score. It
  returns the clamp-floored 0.0.

Consumer (ml/src/analysis/metrics.py:226):
  `BiomechanicsAnalyzer.analyze` calls
  `arm_score = self.compute_arm_position(poses)` (line 226) and packs it into
  `MetricResult(name="arm_position_score", value=arm_score, ...)`. A NaN wrist
  or shoulder on any frame → `arm_position_score` = 0.0 → the recommender reads
  "arms close to body, excellent" → the GOE proxy is INFLATED (arm position is
  one of the OOFSkate proxy features) → the Russian text report praises the arm
  position when it was actually occluded/unknown. The user gets a false
  excellent-arm-position report instead of a flagged/unknown arm score.

Consequences (prod impact):
  1. A NaN wrist or shoulder on ANY frame (wrist frequently occluded during
     rotation — arms cross the body) silently gives `arm_position_score = 0.0`
     — the BEST score. The metric REWARDS occlusion. A skater with occluded
     wrists scores BETTER on arm position than a skater with visible
     arms-extended (arms-out valid ≈ 0.70; NaN → 0.0, lower = better).
  2. The false-good score flows into the GOE proxy (`compute_goe_score`,
     line 1524) — arm position is one of the OOFSkate proxy features —
     inflating the overall GOE. The report praises arm position that was
     unknown.
  3. The `max(0, ...)` clamp is the same #454 trap that bit the CoM tranches
     (BV/BW/CE): `max(0, nan) = 0` (first-arg-wins). The clamp was meant for
     negatives, not NaN; it silently floors NaN.
  4. Existing tests (`test_metrics*` / `test_biomechanics*`) feed all-valid
     poses. No test feeds a NaN wrist/shoulder and asserts the arm score
     degrades (NaN sentinel or a flagged/finite degraded score), not a
     false-good 0.0.

The fix (NOT applied — repro only):
  - `compute_arm_position`: NaN-mask the distances before the mean —
    `np.nanmean` of the finite distances, or skip NaN frames; if NO finite
    frames, return a NaN sentinel (or 0.5 neutral, NOT 0.0 best); and/or
  - guard `avg_dist` before the clamp: `if not np.isfinite(avg_dist): return
    <sentinel>` (NaN, 0.5, or flag) BEFORE `max(0, 1 - avg_dist)`; and/or
  - replace `max(0, ...)` with a NaN-safe clamp:
    `np.clip(np.nan_to_num(1 - avg_dist, nan=<sentinel>), 0, 1)` — but
    `nan_to_num(nan, nan=0.0)` would still give the false-good 0.0; the
    sentinel must be a neutral/flag value, not 0.0.
  - The deeper fix is in gap-filling/smoothing (ensure no NaN reaches the
    metric), but the metric must still be defensive — and must NOT reward NaN
    with the best score.

The correct contract: a NaN wrist or shoulder must NOT produce a false-good
0.0 arm-position score. The metric must return a NaN sentinel (flag the
occlusion) or a neutral finite degraded score (e.g. 0.5), NOT 0.0 — and must
NOT score BETTER than a valid arms-extended skater.

RED now: the observable assertions below describe the CORRECT behavior — a NaN
wrist/shoulder must NOT give a score better-or-equal to a valid arms-extended
case, and must not be a false-good 0.0. They FAIL because `max(0, 1 - nan)`
= 0.0. After the fix: NaN is guarded and the score is a sentinel/neutral
degraded value. The source-check test confirms the unguarded
`np.linalg.norm` + `np.mean` + `max(0, 1 - avg_dist)` clamp — root cause
locked.

Pure-Python (no GPU, no DB): `compute_arm_position` is a pure-data function
over pose arrays.
"""

import inspect

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import H36Key


def _poses_arms_out(n: int = 12) -> np.ndarray:
    """A 12-frame NormalizedPose (17, 2) with arms EXTENDED (wrists far from
    shoulders). The all-valid arm-position score is ~0.70 (finite, mid-range
    — NOT 0.0 best, NOT 1.0 worst). This is the baseline: a visible
    arms-extended skater scores mid-range.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.1]
        poses[f, H36Key.RSHOULDER] = [0.2, 0.1]
        poses[f, H36Key.LWRIST] = [-0.25, 0.4]   # arms out (far from shoulder)
        poses[f, H36Key.RWRIST] = [0.25, 0.4]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: a NaN wrist on the flight frames must NOT give a false-good
# 0.0 arm-position score. The NaN-occlusion score must be WORSE than (or a
# flagged sentinel distinct from) a valid arms-extended skater — not the BEST
# score.
# --------------------------------------------------------------------------- #


def test_nan_wrist_arm_position_not_false_good_repro():
    """CORRECT behavior: `compute_arm_position` with a NaN LWRIST on the flight
    frames (3..6 — wrists frequently occluded during rotation, arms cross the
    body) must NOT return 0.0 — the BEST arm-position score ("arms close to
    body, excellent"). It must return a NaN sentinel (flag the occlusion) or a
    neutral/degraded finite score (e.g. 0.5), and must NOT score BETTER than a
    valid arms-extended skater (≈0.70).

    RED now: NaN LWRIST → `np.linalg.norm(nan - shoulder)` = NaN →
    `np.mean(NaN)` = NaN → `1 - NaN` = NaN → `max(0, NaN)` = 0.0 (the Python
    `max` NaN-arg-order trap, #454: `max(0, nan)` returns the first arg 0). The
    metric REWARDS occlusion with the best score — a skater with occluded
    wrists (0.0) scores BETTER than a skater with visible arms-extended
    (≈0.70). `analyze` (line 226) packs this into `MetricResult(name="
    arm_position_score", value=0.0)` → the recommender → the GOE proxy is
    INFLATED → the report praises arm position that was unknown. After the
    fix: NaN guarded (sentinel / neutral degraded score), not false-good 0.0.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))

    # Baseline: all-valid arms-extended → finite mid-range score (~0.70).
    valid_out = an.compute_arm_position(_poses_arms_out())
    assert np.isfinite(valid_out) and valid_out > 0.1, (
        f"test fixture broken: all-valid arms-extended arm score {valid_out} "
        f"is non-finite or ~0; expected finite mid-range (~0.70). The fixture "
        f"needs wrists far from shoulders so the score is mid-range, not the "
        f"best (0.0) or worst (1.0)."
    )

    poses = _poses_arms_out()
    for f in range(3, 7):
        poses[f, H36Key.LWRIST] = [np.nan, np.nan]  # NaN LWRIST on flight frames

    score = an.compute_arm_position(poses)

    # The NaN-occlusion score must NOT be 0.0 (the false-good best score).
    assert score != 0.0, (
        f"BUG: compute_arm_position returned 0.0 (the BEST arm-position score, "
        f"\"arms close to body, excellent\") for a NaN LWRIST on the flight "
        f"frames 3..6 (occlusion during rotation). `np.linalg.norm(nan - "
        f"shoulder)` = NaN → `np.mean(NaN)` = NaN → `1 - NaN` = NaN → "
        f"`max(0, NaN)` = 0.0 (the Python `max` NaN-arg-order trap, #454: "
        f"`max(0, nan)` returns the first arg 0, NOT NaN). The metric REWARDS "
        f"occlusion with the best score — a skater with occluded wrists (0.0) "
        f"scores BETTER than a skater with visible arms-extended ({valid_out:.3f}). "
        f"`analyze` (line 226) packs this into `MetricResult(name="
        f"\"arm_position_score\", value=0.0)` → the recommender → the GOE proxy "
        f"is INFLATED → the report praises arm position that was unknown. The "
        f"metric must return a NaN sentinel (flag the occlusion) or a neutral "
        f"degraded score, NOT 0.0."
    )

    # The NaN-occlusion score must NOT score BETTER than a valid arms-extended
    # skater (lower = better here; 0.0 < 0.70 = false better).
    assert not (np.isfinite(score) and score < valid_out), (
        f"BUG: compute_arm_position returned {score} for a NaN LWRIST on the "
        f"flight frames — BETTER than the all-valid arms-extended score "
        f"{valid_out:.3f} (lower = better). A NaN occlusion must NOT score "
        f"better than a visible arms-extended skater. The metric must flag the "
        f"occlusion (NaN sentinel) or return a neutral degraded score, not a "
        f"false-good clamp-floored 0.0."
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY of the four keypoints (LWRIST,
# RWRIST, LSHOULDER, RSHOULDER) — the norm poisons on any NaN endpoint.
# --------------------------------------------------------------------------- #


def test_nan_any_keypoint_arm_position_not_false_good_repro():
    """CORRECT behavior: a NaN in ANY of the four arm keypoints (LWRIST, RWRIST,
    LSHOULDER, RSHOULDER) on the flight frames must NOT give a false-good 0.0.
    `np.linalg.norm(wrist - shoulder)` poisons on NaN in EITHER endpoint, so
    any occluded arm keypoint triggers the bug. Wide blast radius.

    RED now: NaN in LWRIST, RWRIST, LSHOULDER, RSHOULDER each → 0.0. After the
    fix: sentinel / neutral degraded score on any occluded keypoint.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    valid_out = an.compute_arm_position(_poses_arms_out())
    for kp in (H36Key.LWRIST, H36Key.RWRIST, H36Key.LSHOULDER, H36Key.RSHOULDER):
        poses = _poses_arms_out()
        for f in range(3, 7):
            poses[f, kp] = [np.nan, np.nan]
        score = an.compute_arm_position(poses)
        assert score != 0.0 or (np.isfinite(score) and score >= valid_out), (
            f"BUG: compute_arm_position returned {score} (false-good 0.0, or "
            f"better than valid arms-extended {valid_out:.3f}) for a NaN "
            f"keypoint ({kp.name}) on the flight frames 3..6. "
            f"`np.linalg.norm(wrist - shoulder)` poisons on NaN in EITHER "
            f"endpoint, so any occluded arm keypoint triggers the false-good "
            f"clamp. Wide blast radius — a fix that only guards one keypoint "
            f"leaves the other three broken."
        )


# --------------------------------------------------------------------------- #
# Observable 3: the false-good 0.0 flows through `analyze` into the
# `arm_position_score` MetricResult — the real prod-impact path (GOE inflation).
# --------------------------------------------------------------------------- #


def test_analyze_arm_position_metric_not_false_good_on_nan_repro():
    """CORRECT behavior: `BiomechanicsAnalyzer.analyze` with a NaN LWRIST on the
    flight frames must produce an `arm_position_score` metric that is NOT the
    false-good 0.0 — it must be a NaN sentinel (flag the occlusion) or a
    neutral/degraded finite score, and must NOT score better than a valid
    arms-extended skater. `analyze` (line 226) packs the score into
    `MetricResult(name="arm_position_score", value=arm_score)` → the recommender
    → the GOE proxy. A 0.0 inflates the GOE and praises unknown arm position.

    RED now: NaN LWRIST → `arm_position_score` metric value = 0.0. After the
    fix: sentinel / neutral degraded score.
    """
    from src.types import ElementPhase

    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))
    phases = ElementPhase(name="j", start=0, takeoff=2, peak=5, landing=7, end=10)

    # Baseline: all-valid arms-extended → finite mid-range metric.
    res_valid = an.analyze(_poses_arms_out(), phases, fps=30.0)
    valid_metric = next(r for r in res_valid if r.name == "arm_position_score")
    assert np.isfinite(valid_metric.value) and valid_metric.value > 0.1, (
        f"test fixture broken: all-valid arm_position_score metric "
        f"{valid_metric.value} is non-finite or ~0; expected mid-range."
    )

    poses = _poses_arms_out()
    for f in range(3, 7):
        poses[f, H36Key.LWRIST] = [np.nan, np.nan]

    results = an.analyze(poses, phases, fps=30.0)
    arm_metric = next(
        (r for r in results if r.name == "arm_position_score"), None
    )
    assert arm_metric is not None, (
        "BUG: analyze() did not produce an `arm_position_score` metric; the "
        "metric name or the analyze() output changed — update the repro "
        "fixture."
    )
    assert arm_metric.value != 0.0 or (
        np.isfinite(arm_metric.value) and arm_metric.value >= valid_metric.value
    ), (
        f"BUG: analyze() `arm_position_score` metric value = "
        f"{arm_metric.value} (false-good 0.0, or better than valid "
        f"arms-extended {valid_metric.value:.3f}) for a NaN LWRIST on the "
        f"flight frames 3..6. The false-good 0.0 flows into the recommender → "
        f"the GOE proxy (`compute_goe_score`, line 1524 — arm position is one "
        f"of the OOFSkate proxy features) → the GOE is INFLATED → the report "
        f"praises arm position that was unknown. The metric must flag the "
        f"occlusion (NaN sentinel) or return a neutral degraded score, not a "
        f"false-good 0.0."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid arms-extended still produces a finite mid-range
# score; all-valid arms-tight produces a high (near-1.0) score.
# --------------------------------------------------------------------------- #


def test_all_valid_arm_position_unchanged_repro():
    """Regression guard: all-valid poses must still produce a finite
    arm-position score (mid-range for arms-extended, near-1.0 for arms-tight).
    The fix (NaN guard / NaN-mask / sentinel) must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the all-valid case.
    """
    an = BiomechanicsAnalyzer(get_element_def("waltz_jump"))

    # Arms-extended → finite mid-range.
    out = an.compute_arm_position(_poses_arms_out())
    assert np.isfinite(out) and 0.1 < out < 0.95, (
        f"BUG (regression): all-valid arms-extended arm score {out} is "
        f"non-finite or out of mid-range; expected ~0.70. The no-NaN case "
        f"must be unchanged by the fix."
    )

    # Arms-tight (wrists near shoulders) → near-1.0 (worst — arms not extended).
    poses_tight = _poses_arms_out()
    poses_tight[:, H36Key.LWRIST] = [-0.21, 0.11]
    poses_tight[:, H36Key.RWRIST] = [0.21, 0.11]
    tight = an.compute_arm_position(poses_tight)
    assert np.isfinite(tight) and tight > out, (
        f"BUG (regression): all-valid arms-tight arm score {tight} is "
        f"non-finite or not greater than arms-extended {out}; expected "
        f"near-1.0 (arms not extended = worse). The no-NaN case must be "
        f"unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — unguarded np.linalg.norm + np.mean +
# max(0, 1 - avg_dist) clamp (#454 trap).
# --------------------------------------------------------------------------- #


def test_arm_position_nan_false_good_source_repro():
    """Source check: `compute_arm_position` computes the wrist-to-shoulder
    distance with unguarded `np.linalg.norm`, averages with `np.mean` (NOT
    `np.nanmean`), and clamps with `max(0, 1 - avg_dist)` (the #454 NaN-arg
    trap: `max(0, nan) = 0`). NO NaN guard. Root cause locked.

    RED now: the unguarded norm + mean + clamp are present (PASS — root cause
    locked). After the fix: a NaN guard (`np.isnan` / `np.nanmean` /
    `np.isfinite` / sentinel) appears — this test FAILS, signaling the
    observable tests above should flip to GREEN.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_arm_position)
    # The unguarded np.linalg.norm wrist-shoulder distance is present.
    assert "np.linalg.norm(poses[:, H36Key.LWRIST] - poses[:, H36Key.LSHOULDER]" in src, (
        "BUG: compute_arm_position must compute `np.linalg.norm(poses[:, "
        "H36Key.LWRIST] - poses[:, H36Key.LSHOULDER], axis=1)` (unguarded, "
        "line 1119) for this repro to be valid. If a NaN guard / nanmean was "
        "added, the false-good bug is fixed — update the observable tests to "
        "the GREEN contract."
    )
    # The np.mean (NOT np.nanmean) average is present.
    assert "np.mean(left_dist + right_dist)" in src, (
        "BUG: compute_arm_position must average with `np.mean(left_dist + "
        "right_dist)` (NOT `np.nanmean`, line 1122) for this repro to be "
        "valid. If it was changed to `np.nanmean`, the false-good bug is "
        "fixed — update the observable tests to the GREEN contract."
    )
    # The max(0, 1 - avg_dist) clamp (#454 trap) is present.
    assert "max(0, 1 - avg_dist)" in src, (
        "BUG: compute_arm_position must clamp with `max(0, 1 - avg_dist)` "
        "(line 1124, the #454 NaN-arg trap: `max(0, nan) = 0`) for this repro "
        "to be valid. If the clamp was changed to a NaN-safe form "
        "(`np.clip`, `nan_to_num` with a non-0 sentinel, or a NaN guard before "
        "the clamp), the false-good bug is fixed — update the observable tests "
        "to the GREEN contract."
    )
    assert "np.isnan" not in src and "np.nanmean" not in src and \
           "np.isfinite" not in src and "np.nan_to_num" not in src, (
        "BUG: a NaN guard (`np.isnan` / `np.nanmean` / `np.isfinite` / "
        "`np.nan_to_num`) appeared in compute_arm_position — the false-good "
        "NaN bug is fixed; update the observable tests to the GREEN contract."
    )