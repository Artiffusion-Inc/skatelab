"""RED repro — `BiomechanicsAnalyzer.compute_edge_indicator` (metrics.py:1320-1360)
silently propagates NaN from an occluded hip/shoulder joint into the edge
indicator series. The function has NO NaN guard on its hip/shoulder inputs:

    # compute_edge_indicator (line 1344-1360)
    hip = poses[:, H36Key.LHIP]                          # NaN hip -> NaN
    shoulder = poses[:, H36Key.LSHOULDER]                # NaN shoulder -> NaN
    spine_vector = shoulder - hip                        # NaN - finite = NaN
    angle = np.arctan2(spine_vector[:, 0], -spine_vector[:, 1])  # arctan2(NaN)=NaN
    edge_indicator = np.clip(angle / (np.pi / 6), -1, 1).astype(np.float32)  # clip(NaN)=NaN
    return edge_indicator                                # NaN series

The NaN edge series then leaks into `edge_change_smoothness` via the
`_analyze_step` caller (line 491-502):

    edge_ind = self.compute_edge_indicator(poses, side="left")
    edge_change = float(np.std(edge_ind))   # np.std NOT NaN-aware -> NaN
    results.append(MetricResult(name="edge_change_smoothness", value=edge_change, ...))

`np.arctan2(NaN)=NaN`, `np.clip(NaN)=NaN`, `np.std(NaN)=NaN`. A single
occluded hip/shoulder poisons the entire per-frame series -> NaN metric leak
(no crash, no guard). The HUD renders "edge_change_smoothness: nan",
`is_good=False` (silent false-bad).

The contract: an occluded hip/shoulder joint must NOT silently yield NaN
`compute_edge_indicator`. The function must guard its hip/shoulder inputs
with `np.isfinite` / `np.nan_to_num` (NaN -> 0.0 sentinel, mirroring the
#978 `compute_goe_score` nan_to_num guards and the #868
`compute_knee_angle_series` finite-frame mask). NaN must not propagate as
NaN in the returned series.

Pure-Python (no GPU, no DB): the function is pure-data over a poses array.
NaN is injected directly into the poses array at one joint index — this
isolates the input-trust-boundary guard from any upstream source.
"""

import inspect

import numpy as np

from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import H36Key


def _edge_poses(n: int = 8) -> np.ndarray:
    """An 8-frame all-finite pose sequence (N, 17, 2) with a non-zero
    spine_vector (shoulder above hip, slight lean) so `compute_edge_indicator`
    is well-defined and non-trivial. Used for the all-finite regression guard
    and as the base for NaN-injection tests.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.LHIP] = [-0.1, 0.5]
        poses[f, H36Key.RHIP] = [0.1, 0.5]
        poses[f, H36Key.LSHOULDER] = [-0.1, 0.2]
        poses[f, H36Key.RSHOULDER] = [0.1, 0.2]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: a NaN LHIP joint must NOT leak NaN into edge_indicator (left).
# --------------------------------------------------------------------------- #


def test_nan_hip_does_not_leak_nan_into_edge_indicator_repro():
    """CORRECT behavior: when an occluded LHIP joint (NaN) flows into
    `compute_edge_indicator` (side='left'), the returned per-frame series
    must be finite (NaN -> 0.0 sentinel), NOT NaN. `np.arctan2(NaN)=NaN`,
    `np.clip(NaN)=NaN` — so the NaN hip silently poisons the whole edge
    series -> `np.std(NaN)=NaN` -> `edge_change_smoothness = MetricResult(NaN)`.
    Guard the hip/shoulder inputs at the trust boundary (np.nan_to_num /
    np.isfinite) so NaN -> 0.0, mirroring #978 / #868.

    RED now: NaN LHIP -> NaN spine -> arctan2(NaN)=NaN -> clip(NaN)=NaN series.
    After the fix: NaN LHIP -> 0.0 sentinel -> finite edge_indicator.
    """
    analyzer = BiomechanicsAnalyzer.__new__(BiomechanicsAnalyzer)
    poses = _edge_poses()
    poses[:, H36Key.LHIP, :] = np.nan  # occluded left hip on every frame

    edge_ind = analyzer.compute_edge_indicator(poses, side="left")

    assert np.all(np.isfinite(edge_ind)), (
        "BUG: compute_edge_indicator returned non-finite values (nan present) "
        "for an occluded LHIP joint. NaN hip -> NaN spine_vector -> "
        "arctan2(NaN)=NaN -> np.clip(NaN)=NaN silently leaks NaN into the edge "
        "series -> np.std(NaN)=NaN -> edge_change_smoothness=MetricResult(NaN). "
        "Guard the hip/shoulder inputs at the trust boundary (np.nan_to_num / "
        "np.isfinite, NaN->0.0 sentinel, mirrors #978/#868). (#977)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: a NaN LSHOULDER joint must NOT leak NaN into edge_indicator.
# --------------------------------------------------------------------------- #


def test_nan_shoulder_does_not_leak_nan_into_edge_indicator_repro():
    """CORRECT behavior: when an occluded LSHOULDER joint (NaN) flows into
    `compute_edge_indicator` (side='left'), the returned per-frame series
    must be finite (NaN -> 0.0 sentinel), NOT NaN. No guard exists today —
    `NaN - finite = NaN` -> `arctan2(NaN)=NaN`. Guard the shoulder inputs at
    the trust boundary.

    RED now: NaN LSHOULDER -> NaN spine -> NaN edge series. After the fix:
    NaN LSHOULDER -> 0.0 sentinel -> finite edge_indicator.
    """
    analyzer = BiomechanicsAnalyzer.__new__(BiomechanicsAnalyzer)
    poses = _edge_poses()
    poses[:, H36Key.LSHOULDER, :] = np.nan  # occluded left shoulder on every frame

    edge_ind = analyzer.compute_edge_indicator(poses, side="left")

    assert np.all(np.isfinite(edge_ind)), (
        "BUG: compute_edge_indicator returned non-finite values (nan present) "
        "for an occluded LSHOULDER joint. NaN shoulder -> NaN spine_vector -> "
        "arctan2(NaN)=NaN -> np.clip(NaN)=NaN leaks NaN into the edge series. "
        "Guard the hip/shoulder inputs at the trust boundary (np.nan_to_num / "
        "np.isfinite, NaN->0.0 sentinel). (#977)"
    )


# --------------------------------------------------------------------------- #
# Observable 3: right-side NaN RHIP must NOT leak NaN into edge_indicator.
# --------------------------------------------------------------------------- #


def test_nan_right_hip_does_not_leak_nan_into_edge_indicator_repro():
    """CORRECT behavior: when an occluded RHIP joint (NaN) flows into
    `compute_edge_indicator` (side='right'), the returned per-frame series
    must be finite (NaN -> 0.0 sentinel), NOT NaN. The right-side branch must
    be guarded the same as the left.

    RED now: NaN RHIP -> NaN spine -> NaN edge series. After the fix:
    NaN RHIP -> 0.0 sentinel -> finite edge_indicator.
    """
    analyzer = BiomechanicsAnalyzer.__new__(BiomechanicsAnalyzer)
    poses = _edge_poses()
    poses[:, H36Key.RHIP, :] = np.nan  # occluded right hip on every frame

    edge_ind = analyzer.compute_edge_indicator(poses, side="right")

    assert np.all(np.isfinite(edge_ind)), (
        "BUG: compute_edge_indicator(side='right') returned non-finite values "
        "(nan present) for an occluded RHIP joint. NaN hip -> NaN spine_vector "
        "-> arctan2(NaN)=NaN -> clip(NaN)=NaN leaks NaN into the edge series. "
        "Guard the right-side hip/shoulder inputs at the trust boundary. (#977)"
    )


# --------------------------------------------------------------------------- #
# Regression: all-finite poses -> finite edge_indicator. The NaN guards must
# not change the no-NaN case.
# --------------------------------------------------------------------------- #


def test_all_finite_edge_indicator_unchanged_repro():
    """Regression guard: an all-finite pose sequence must still report finite
    edge_indicator for both sides. The NaN guards (np.nan_to_num /
    np.isfinite) must not change the no-NaN case — `nan_to_num(x, nan=0.0)`
    is identity on finite x, `np.isfinite(x)` is True on finite x.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the all-finite case.
    """
    analyzer = BiomechanicsAnalyzer.__new__(BiomechanicsAnalyzer)
    poses = _edge_poses()

    left = analyzer.compute_edge_indicator(poses, side="left")
    right = analyzer.compute_edge_indicator(poses, side="right")

    assert np.all(np.isfinite(left)), (
        "BUG (regression): all-finite poses reported non-finite "
        "edge_indicator(left). The no-NaN case must be unchanged by the fix."
    )
    assert np.all(np.isfinite(right)), (
        "BUG (regression): all-finite poses reported non-finite "
        "edge_indicator(right). The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — compute_edge_indicator guards its
# hip/shoulder inputs against NaN before the edge-indicator math.
# --------------------------------------------------------------------------- #


def test_compute_edge_indicator_has_nan_guard_on_joint_inputs_repro():
    """GREEN contract source check: `compute_edge_indicator` guards its
    hip/shoulder joint inputs against NaN (np.isfinite / np.nan_to_num) before
    the spine_vector / arctan2 / clip math — mirroring the #978
    `compute_goe_score` nan_to_num guards and the #868
    `compute_knee_angle_series` finite-frame mask. The root cause (NaN joint
    -> NaN series, no trust-boundary guard) must be locked out at the source.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_edge_indicator)

    assert "np.nan_to_num" in src or "np.isfinite" in src, (
        "BUG: compute_edge_indicator has no NaN guard on its hip/shoulder "
        "joint inputs. NaN hip/shoulder -> NaN spine_vector -> "
        "arctan2(NaN)=NaN -> np.clip(NaN)=NaN leaks NaN into the edge series "
        "-> np.std(NaN)=NaN -> edge_change_smoothness=MetricResult(NaN). "
        "Guard at the trust boundary (np.nan_to_num / np.isfinite, "
        "NaN->0.0 sentinel, mirrors #978/#868). (#977)"
    )
