"""RED repro — `BiomechanicsAnalyzer.compute_spread_eagle_angle` /
`compute_spiral_indicator` / `compute_ina_bauer_score` (metrics.py:1473-1546)
silently propagate NaN from an occluded hip/knee/foot/thorax joint into the
angle/score/indicator series. The three functions have NO NaN guard on their
joint inputs:

    # compute_spread_eagle_angle (line 1483-1490)
    l_leg = poses[:, LKNEE] - poses[:, LHIP]            # NaN hip/knee -> NaN
    r_leg = poses[:, RKNEE] - poses[:, RHIP]
    dot_prod = np.sum(l_leg * r_leg, axis=-1)            # NaN
    norms = norm(l_leg) * norm(r_leg) + 1e-8            # NaN + 1e-8 = NaN
    cos_angle = np.clip(dot_prod / norms, -1.0, 1.0)    # NaN, clip no-op
    return np.degrees(np.arccos(cos_angle))             # arccos(NaN) = NaN

    # compute_spiral_indicator (line 1502)
    return np.abs(poses[:, LFOOT, 1] - poses[:, RFOOT, 1])  # NaN foot -> NaN

    # compute_ina_bauer_score (line 1519-1546)
    se_angle = self.compute_spread_eagle_angle(poses)   # NaN -> NaN
    leg_angle_norm = np.clip((se_angle - 150.0) / 30.0, 0, 1)  # NaN
    trunk = poses[:, THORAX] - poses[:, HIP_CENTER]     # NaN thorax -> NaN
    trunk_norm = trunk / (norm + 1e-8)                 # NaN
    torso_lean = np.degrees(np.arccos(np.clip(-trunk_norm[:, 1], -1, 1)))  # NaN
    knee_diff_norm = np.clip(np.abs(l_knee - r_knee) / 40.0, 0, 1)         # NaN
    return 0.5*leg + 0.3*torso + 0.2*knee              # NaN (any NaN -> NaN)

`+ 1e-8` epsilon does NOT mask NaN (`NaN + 1e-8 = NaN`), `np.clip(NaN) = NaN`,
`np.arccos(NaN) = NaN`. A single occluded joint poisons the entire per-frame
series, which then leaks NaN into `MetricResult` via `_analyze_step`'s
`np.max(se_angle)` / `np.max(ib_score)` / `np.max(spiral)` aggregations — a
silent NaN metric leak (no crash, no guard). The HUD then renders
"spread_eagle_angle: nan°", `is_good = NaN >= 150 = False` (silent false-bad).

The contract: an occluded hip/knee/foot/thorax joint must NOT silently yield
NaN `spread_eagle_angle` / `ina_bauer_score` / `spiral_indicator`. Each
function must guard its joint inputs with `np.isfinite` / `np.nan_to_num`
(NaN -> 0.0 sentinel, mirroring the #978 `compute_goe_score` nan_to_num
guards and the #868 `compute_knee_angle_series` finite-frame mask). NaN
must not propagate as NaN in the returned series.

Pure-Python (no GPU, no DB): all three functions are pure-data over a poses
array. NaN is injected directly into the poses array at one joint index —
this isolates the input-trust-boundary guard from any upstream source.
"""

import inspect

import numpy as np

from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import H36Key


def _step_poses(n: int = 8) -> np.ndarray:
    """An 8-frame all-finite pose sequence (N, 17, 2) with legs abducted so
    `spread_eagle_angle` is well-defined and `ina_bauer_score`'s knee-angle
    branch is exercised. Used for the all-finite regression guard and as the
    base for NaN-injection tests.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.HIP_CENTER] = [0.0, 0.5]
        poses[f, H36Key.LHIP] = [-0.1, 0.5]
        poses[f, H36Key.RHIP] = [0.1, 0.5]
        # Legs abducted outward (spread-eagle-ish) so leg vectors are non-zero.
        poses[f, H36Key.LKNEE] = [-0.3, 0.9]
        poses[f, H36Key.RKNEE] = [0.3, 0.9]
        poses[f, H36Key.LFOOT] = [-0.35, 1.1]
        poses[f, H36Key.RFOOT] = [0.35, 1.1]
        poses[f, H36Key.THORAX] = [0.0, 0.2]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: a NaN LHIP joint must NOT leak NaN into spread_eagle_angle.
# --------------------------------------------------------------------------- #


def test_nan_hip_does_not_leak_nan_into_spread_eagle_angle_repro():
    """CORRECT behavior: when an occluded LHIP joint (NaN) flows into
    `compute_spread_eagle_angle`, the returned per-frame series must be finite
    (NaN -> 0.0 sentinel), NOT NaN. `+ 1e-8` does NOT mask NaN, `np.clip(NaN)`
    is no-op, `np.arccos(NaN) = NaN` — so the NaN joint silently poisons the
    whole angle series. Guard the leg-vector inputs at the trust boundary
    (np.nan_to_num / np.isfinite) so NaN -> 0.0, mirroring #978 / #868.

    RED now: NaN LHIP -> NaN leg -> NaN cos -> arccos(NaN) = NaN series. After
    the fix: NaN LHIP -> 0.0 sentinel -> finite angle.
    """
    poses = _step_poses()
    poses[:, H36Key.LHIP, :] = np.nan  # occluded left hip on every frame

    angle = BiomechanicsAnalyzer.compute_spread_eagle_angle(poses)

    assert np.all(np.isfinite(angle)), (
        "BUG: compute_spread_eagle_angle returned non-finite values "
        "(nan present) for an occluded LHIP joint. A NaN hip -> NaN leg -> "
        "NaN cos_angle -> np.arccos(NaN)=NaN silently leaks NaN into the "
        "angle series. +1e-8 does NOT mask NaN, np.clip(NaN) is no-op. Guard "
        "the joint inputs at the trust boundary (np.nan_to_num / np.isfinite, "
        "NaN->0.0 sentinel, mirrors #978/#868). (#976)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: a NaN LFOOT joint must NOT leak NaN into spiral_indicator.
# --------------------------------------------------------------------------- #


def test_nan_foot_does_not_leak_nan_into_spiral_indicator_repro():
    """CORRECT behavior: when an occluded LFOOT joint (NaN) flows into
    `compute_spiral_indicator` (`|LFOOT_y - RFOOT_y|`), the returned series
    must be finite (NaN -> 0.0 sentinel), NOT NaN. No guard exists today —
    `np.abs(NaN - finite) = NaN`. Guard the foot inputs at the trust boundary.

    RED now: NaN LFOOT -> NaN |NaN - RFOOT_y| = NaN series. After the fix:
    NaN LFOOT -> 0.0 sentinel -> finite indicator.
    """
    poses = _step_poses()
    poses[:, H36Key.LFOOT, :] = np.nan  # occluded left foot on every frame

    spiral = BiomechanicsAnalyzer.compute_spiral_indicator(poses)

    assert np.all(np.isfinite(spiral)), (
        "BUG: compute_spiral_indicator returned non-finite values "
        "(nan present) for an occluded LFOOT joint. "
        "np.abs(NaN - RFOOT_y) = NaN silently leaks NaN into the indicator "
        "series. Guard the foot inputs at the trust boundary (np.nan_to_num "
        "/ np.isfinite, NaN->0.0 sentinel). (#976)"
    )


# --------------------------------------------------------------------------- #
# Observable 3: a NaN THORAX joint must NOT leak NaN into ina_bauer_score.
# --------------------------------------------------------------------------- #


def test_nan_thorax_does_not_leak_nan_into_ina_bauer_score_repro():
    """CORRECT behavior: when an occluded THORAX joint (NaN) flows into
    `compute_ina_bauer_score` (trunk = THORAX - HIP_CENTER -> NaN trunk ->
    NaN trunk_norm -> arccos(NaN) = NaN torso_lean -> NaN composite), the
    returned series must be finite (NaN -> 0.0 sentinel), NOT NaN. No guard
    exists today — NaN poisons the weighted composite (0.5*leg + 0.3*NaN +
    0.2*knee = NaN). Guard the trunk / knee inputs at the trust boundary.

    RED now: NaN THORAX -> NaN trunk -> NaN torso_lean -> NaN composite. After
    the fix: NaN THORAX -> 0.0 sentinel -> finite score.
    """
    analyzer = BiomechanicsAnalyzer.__new__(BiomechanicsAnalyzer)
    poses = _step_poses()
    poses[:, H36Key.THORAX, :] = np.nan  # occluded thorax on every frame

    score = analyzer.compute_ina_bauer_score(poses)

    assert np.all(np.isfinite(score)), (
        "BUG: compute_ina_bauer_score returned non-finite values "
        "(nan present) for an occluded THORAX joint. NaN THORAX -> NaN trunk "
        "-> NaN trunk_norm -> arccos(NaN)=NaN torso_lean -> NaN composite "
        "(0.5*leg + 0.3*NaN + 0.2*knee = NaN). Guard the trunk / knee inputs "
        "at the trust boundary (np.nan_to_num / np.isfinite, NaN->0.0 "
        "sentinel, mirrors #978). (#976)"
    )


# --------------------------------------------------------------------------- #
# Regression: all-finite poses -> finite angle / indicator / score. The NaN
# guards must not change the no-NaN case.
# --------------------------------------------------------------------------- #


def test_all_finite_step_metrics_unchanged_repro():
    """Regression guard: an all-finite pose sequence must still report finite
    spread_eagle_angle, spiral_indicator, and ina_bauer_score. The NaN guards
    (np.nan_to_num / np.isfinite) must not change the no-NaN case —
    `nan_to_num(x, nan=0.0)` is identity on finite x, `np.isfinite(x)` is True
    on finite x.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the all-finite case.
    """
    analyzer = BiomechanicsAnalyzer.__new__(BiomechanicsAnalyzer)
    poses = _step_poses()

    angle = BiomechanicsAnalyzer.compute_spread_eagle_angle(poses)
    spiral = BiomechanicsAnalyzer.compute_spiral_indicator(poses)
    score = analyzer.compute_ina_bauer_score(poses)

    assert np.all(np.isfinite(angle)), (
        "BUG (regression): all-finite poses reported non-finite "
        "spread_eagle_angle. The no-NaN case must be unchanged by the fix."
    )
    assert np.all(np.isfinite(spiral)), (
        "BUG (regression): all-finite poses reported non-finite "
        "spiral_indicator. The no-NaN case must be unchanged by the fix."
    )
    assert np.all(np.isfinite(score)), (
        "BUG (regression): all-finite poses reported non-finite "
        "ina_bauer_score. The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — all three functions guard their joint
# inputs against NaN before the angle/score/indicator math.
# --------------------------------------------------------------------------- #


def test_step_metrics_have_nan_guard_on_joint_inputs_repro():
    """GREEN contract source check: `compute_spread_eagle_angle`,
    `compute_spiral_indicator`, and `compute_ina_bauer_score` each guard their
    joint inputs against NaN (np.isfinite / np.nan_to_num) before the
    angle / score / indicator math — mirroring the #978 `compute_goe_score`
    nan_to_num guards and the #868 `compute_knee_angle_series` finite-frame
    mask. The root cause (NaN joint -> NaN series, no trust-boundary guard)
    must be locked out at the source.
    """
    se_src = inspect.getsource(BiomechanicsAnalyzer.compute_spread_eagle_angle)
    spiral_src = inspect.getsource(BiomechanicsAnalyzer.compute_spiral_indicator)
    ib_src = inspect.getsource(BiomechanicsAnalyzer.compute_ina_bauer_score)

    assert "np.nan_to_num" in se_src or "np.isfinite" in se_src, (
        "BUG: compute_spread_eagle_angle has no NaN guard on its leg-vector "
        "joint inputs. NaN hip/knee -> NaN leg -> NaN cos -> arccos(NaN)=NaN "
        "(+1e-8 does NOT mask NaN, np.clip(NaN) is no-op). Guard at the trust "
        "boundary (np.nan_to_num / np.isfinite, NaN->0.0). (#976)"
    )
    assert "np.nan_to_num" in spiral_src or "np.isfinite" in spiral_src, (
        "BUG: compute_spiral_indicator has no NaN guard on its foot joint "
        "inputs. np.abs(NaN - RFOOT_y) = NaN leaks NaN into the indicator. "
        "Guard at the trust boundary (np.nan_to_num / np.isfinite). (#976)"
    )
    assert "np.nan_to_num" in ib_src or "np.isfinite" in ib_src, (
        "BUG: compute_ina_bauer_score has no NaN guard on its trunk / knee "
        "joint inputs. NaN THORAX -> NaN trunk -> arccos(NaN)=NaN torso_lean "
        "-> NaN composite. Guard at the trust boundary (np.nan_to_num / "
        "np.isfinite, mirrors #978). (#976)"
    )
