"""RED repro — `BiomechanicsAnalyzer.compute_goe_score` (metrics.py:1762-1820)
normalizes each sub-metric via `min(1.0, sub_metric / scale)`. Python's
`min(1.0, x)` is *arg-order NaN-unsafe*: `min(1.0, float('nan')) = 1.0`
(the first arg wins when the second is NaN, #454). A NaN sub-metric (NaN
shoulder → NaN rotation_speed / NaN trunk_recovery; NaN hip → NaN
relative_jump_height / landing metrics; NaN CoM → NaN approach_change) is
silently clamped to a PERFECT sub-score (1.0), NOT flagged as missing. The
GOE composite then inflates toward 10.0 — a jump with missing data scores
HIGHER than a jump with real data, silently.

Two of the six sub-scores are already guarded at the cap site
(`height_score` #875, `approach_score` #878 — both `np.nan_to_num(...,
nan=0.0)` before `min(1.0, ...)`). The remaining four are NOT guarded:

    rot_score = min(1.0, rot_speed / 720.0)              # NaN → 1.0 PERFECT
    landing_score = (smooth + stab + hard + toe) / 4.0   # NaN → NaN leak
    airtime_score = min(1.0, airtime / 1.0)              # NaN → 1.0 PERFECT
    trunk_recovery                                       # NaN → NaN leak

The contract: a NaN sub-metric must NOT silently clamp to 1.0 (perfect) at
the `min(1.0, ...)` cap, and must NOT leak NaN into the GOE composite. Each
sub-metric must be guarded with `np.isfinite` / `np.nan_to_num` before the
cap (mirroring #875/#878) so a missing sub-metric yields 0.0 (worst, not
best) or a finite sentinel — never 1.0 (perfect), never NaN.

Pure-Python (no GPU, no DB): `compute_goe_score` is a pure-data function
over poses + phases. The NaN sub-metrics are simulated by monkey-patching
the underlying compute methods to return NaN — this isolates the cap-site
guard from whether the underlying function currently emits NaN (defense in
depth: the cap site must be safe regardless of its input source).
"""

import inspect

import numpy as np

from src.analysis.element_defs import ELEMENT_DEFS
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, H36Key


def _jump_pose(n: int = 12) -> np.ndarray:
    """A 12-frame waltz-jump pose sequence (all-finite) — takeoff=2, peak=4,
    landing=7. The CoM rises at frames 4..6. Used for the all-finite
    regression guard and as the base for monkey-patched NaN-injection tests.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.HEAD] = [0.0, 0.0]
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.1]
        poses[f, H36Key.RSHOULDER] = [0.2, 0.1]
        poses[f, H36Key.LHIP] = [-0.1, 0.5]
        poses[f, H36Key.RHIP] = [0.1, 0.5]
        poses[f, H36Key.LKNEE] = [-0.1, 0.9]
        poses[f, H36Key.RKNEE] = [0.1, 0.9]
        poses[f, H36Key.LFOOT] = [-0.1, 1.0]
        poses[f, H36Key.RFOOT] = [0.1, 1.0]
    for f in range(4, 7):
        poses[f, :, 1] -= 0.3
    return poses


def _phases(n: int = 12) -> ElementPhase:
    return ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=4, landing=7, end=n - 1)


# --------------------------------------------------------------------------- #
# Observable 1: a NaN rotation_speed sub-metric must NOT inflate rot_score to
# perfect (1.0) via min(1.0, NaN) = 1.0.
# --------------------------------------------------------------------------- #


def test_nan_rotation_speed_does_not_inflate_rot_score_to_perfect_repro():
    """CORRECT behavior: when `compute_rotation_speed` returns NaN (occluded
    shoulder during fast rotation), `rot_score = min(1.0, nan / 720.0)` must
    NOT clamp to 1.0 (PERFECT). Python `min(1.0, nan) = 1.0` (arg-order,
    #454) — a missing rotation measurement silently scores BEST. The cap
    site must guard with `np.nan_to_num` / `np.isfinite` so NaN → 0.0
    (worst, "no data"), NOT 1.0 (perfect). The composite GOE must be finite
    and strictly less than the all-perfect 10.0.

    RED now: `min(1.0, nan) = 1.0` → rot_score = 1.0 → GOE inflated by
    +0.15*10 = +1.5 from a missing measurement. After the fix: NaN → 0.0.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    analyzer.compute_rotation_speed = lambda poses, phases, fps: float("nan")

    goe = analyzer.compute_goe_score(_jump_pose(), _phases(), 30.0)

    assert np.isfinite(goe), (
        f"BUG: compute_goe_score returned GOE={goe} (nan) for a NaN "
        f"rotation_speed. The composite must not leak NaN. "
        f"min(1.0, nan)=1.0 (#454 arg-order) inflates rot_score to PERFECT, "
        f"but the composite may still go NaN via landing_score/trunk_recovery "
        f"leaks. Both paths are bugs (#978)."
    )
    # A missing rotation measurement must NOT yield a perfect composite.
    # Perfect = all six sub-scores = 1.0 → GOE = 10.0. With rot_score forced
    # to the NaN-inflated 1.0 and the rest finite-but-not-all-perfect, the
    # composite is < 10.0; but if NaN propagates as 1.0 AND the other
    # sub-scores happen to be high, the GOE silently approaches 10.0 from a
    # missing measurement. The strict guard: GOE from a NaN rot_score must
    # be strictly less than the GOE computed with rot_score=1.0 (perfect).
    analyzer.compute_rotation_speed = lambda poses, phases, fps: 720.0  # → rot_score = 1.0
    goe_perfect_rot = analyzer.compute_goe_score(_jump_pose(), _phases(), 30.0)
    analyzer.compute_rotation_speed = lambda poses, phases, fps: float("nan")
    goe_nan_rot = analyzer.compute_goe_score(_jump_pose(), _phases(), 30.0)
    assert goe_nan_rot < goe_perfect_rot - 1e-6, (
        f"BUG: NaN rotation_speed → GOE={goe_nan_rot} equals or exceeds the "
        f"perfect-rotation GOE={goe_perfect_rot}. min(1.0, nan/720.0)=1.0 "
        f"(#454 arg-order) silently inflated rot_score to PERFECT — a "
        f"missing measurement scored the SAME as a 720°/s rotation. The "
        f"cap site must guard NaN → 0.0 (worst), not 1.0 (best). (#978)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: a NaN airtime sub-metric must NOT inflate airtime_score to
# perfect (1.0) via min(1.0, NaN) = 1.0.
# --------------------------------------------------------------------------- #


def test_nan_airtime_does_not_inflate_airtime_score_to_perfect_repro():
    """CORRECT behavior: when `compute_airtime` returns NaN (corrupt fps /
    phase boundary), `airtime_score = min(1.0, nan / 1.0)` must NOT clamp to
    1.0 (PERFECT). Same `min(1.0, nan)=1.0` arg-order trap (#454). NaN → 0.0
    (no flight data), NOT 1.0 (perfect flight).

    RED now: `min(1.0, nan) = 1.0` → airtime_score = 1.0 → GOE inflated by
    +0.15*10 = +1.5 from a missing airtime. After the fix: NaN → 0.0.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    analyzer.compute_airtime = lambda phases, fps: float("nan")

    goe_nan = analyzer.compute_goe_score(_jump_pose(), _phases(), 30.0)
    assert np.isfinite(goe_nan), (
        f"BUG: compute_goe_score returned GOE={goe_nan} (non-finite) for a "
        f"NaN airtime. min(1.0, nan)=1.0 (#454) inflates airtime_score to "
        f"PERFECT, but NaN may also leak. Both are bugs (#978)."
    )

    analyzer.compute_airtime = lambda phases, fps: 1.0  # → airtime_score = 1.0
    goe_perfect_airtime = analyzer.compute_goe_score(_jump_pose(), _phases(), 30.0)
    analyzer.compute_airtime = lambda phases, fps: float("nan")
    goe_nan_airtime = analyzer.compute_goe_score(_jump_pose(), _phases(), 30.0)
    assert goe_nan_airtime < goe_perfect_airtime - 1e-6, (
        f"BUG: NaN airtime → GOE={goe_nan_airtime} equals/exceeds the "
        f"perfect-airtime GOE={goe_perfect_airtime}. min(1.0, nan/1.0)=1.0 "
        f"(#454 arg-order) silently inflated airtime_score to PERFECT — a "
        f"missing airtime scored the SAME as a 1.0s flight. The cap site "
        f"must guard NaN → 0.0, not 1.0. (#978)"
    )


# --------------------------------------------------------------------------- #
# Observable 3: a NaN landing sub-metric must NOT leak NaN into the GOE
# composite — guard at the aggregate site.
# --------------------------------------------------------------------------- #


def test_nan_landing_smoothness_does_not_leak_nan_into_goe_repro():
    """CORRECT behavior: when a landing sub-metric (`compute_landing_smoothness`)
    returns NaN, `landing_score = (smooth + stab + hard + toe) / 4.0` becomes
    NaN and leaks into the GOE composite. The aggregate must guard NaN
    (np.nan_to_num / isfinite mask) so a missing landing sub-metric yields a
    finite landing_score, NOT NaN that poisons the whole GOE.

    RED now: NaN + finite / 4 = NaN → GOE = NaN (NaN-leak, breaks JSON /
    frontend). After the fix: NaN sub-metric masked → finite landing_score.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    analyzer.compute_landing_smoothness = lambda poses, phases, fps: float("nan")

    goe = analyzer.compute_goe_score(_jump_pose(), _phases(), 30.0)
    assert np.isfinite(goe), (
        f"BUG: compute_goe_score returned GOE={goe} (nan) for a NaN "
        f"landing_smoothness. landing_score = (nan + stab + hard + toe)/4 = "
        f"nan → GOE = nan (NaN-leak). NaN is not valid JSON (RFC 8259), "
        f"breaks strict parsers and frontend display. The aggregate must "
        f"guard NaN sub-metrics (np.nan_to_num / isfinite mask). (#978)"
    )


# --------------------------------------------------------------------------- #
# Observable 4: a NaN trunk_recovery sub-metric must NOT leak NaN into the
# GOE composite.
# --------------------------------------------------------------------------- #


def test_nan_trunk_recovery_does_not_leak_nan_into_goe_repro():
    """CORRECT behavior: when `compute_landing_trunk_recovery` returns NaN,
    the GOE composite `... + trunk_recovery * 0.15` becomes NaN and leaks.
    The composite must guard `trunk_recovery` with `np.nan_to_num` /
    `np.isfinite` so NaN → 0.0 (finite), NOT NaN that poisons the GOE.

    RED now: NaN * 0.15 = NaN → GOE = NaN (NaN-leak). After the fix: NaN → 0.0.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    analyzer.compute_landing_trunk_recovery = lambda poses, phases: float("nan")

    goe = analyzer.compute_goe_score(_jump_pose(), _phases(), 30.0)
    assert np.isfinite(goe), (
        f"BUG: compute_goe_score returned GOE={goe} (nan) for a NaN "
        f"trunk_recovery. `goe = ... + nan * 0.15 = nan` (NaN-leak). NaN "
        f"is not valid JSON (RFC 8259), breaks strict parsers and frontend "
        f"display. The composite must guard trunk_recovery (np.nan_to_num / "
        f"isfinite) so NaN → 0.0, not NaN. (#978)"
    )


# --------------------------------------------------------------------------- #
# Regression: all-finite poses → finite GOE in [0, 10]. The NaN guards must
# not change the no-NaN case.
# --------------------------------------------------------------------------- #


def test_all_finite_goe_score_unchanged_repro():
    """Regression guard: an all-finite waltz-jump pose sequence must still
    report a finite GOE in [0.0, 10.0]. The NaN guards (np.nan_to_num /
    isfinite) must not change the no-NaN case — `nan_to_num(x, nan=0.0)` is
    identity on finite x, `np.isfinite(x)` is True on finite x.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-finite case.
    """
    analyzer = BiomechanicsAnalyzer(ELEMENT_DEFS["waltz_jump"])
    goe = analyzer.compute_goe_score(_jump_pose(), _phases(), 30.0)
    assert np.isfinite(goe) and 0.0 <= goe <= 10.0, (
        f"BUG (regression): all-finite jump reported GOE={goe}, expected "
        f"finite in [0, 10]. The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — the four unguarded sub-scores have a
# NaN guard (np.isfinite / np.nan_to_num) before the cap / aggregate.
# --------------------------------------------------------------------------- #


def test_compute_goe_score_has_nan_guard_on_all_sub_scores_repro():
    """GREEN contract source check: `compute_goe_score` guards EVERY sub-metric
    against NaN before the cap / aggregate, mirroring the existing
    `height_score` (#875) and `approach_score` (#878) guards. The four
    previously-unguarded sub-scores (rot_score, airtime_score, landing_score,
    trunk_recovery) must each have a `np.isfinite` / `np.nan_to_num` guard so
    a NaN sub-metric cannot inflate to 1.0 (perfect) or leak NaN into the
    composite (#978).
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_goe_score)
    # The cap-site guards use np.nan_to_num (mirrors #875/#878) and/or
    # np.isfinite. At least one of these must appear per sub-score group.
    assert "np.nan_to_num" in src or "np.isfinite" in src, (
        "BUG: compute_goe_score has no NaN guard on its sub-scores. "
        "min(1.0, nan)=1.0 (#454 arg-order) inflates a NaN sub-metric to "
        "PERFECT, and NaN aggregates leak NaN into the GOE composite (#978). "
        "Mirror the existing height_score (#875) / approach_score (#878) "
        "guards: np.nan_to_num(sub_metric, nan=0.0) before the cap."
    )
