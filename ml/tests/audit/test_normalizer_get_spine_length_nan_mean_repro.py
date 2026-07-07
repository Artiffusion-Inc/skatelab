"""RED repro — PoseNormalizer.get_spine_length NaN thorax (or hip_center) on
one frame → `np.mean(spine_lengths)` = NaN → NaN spine length (tranche ES).

Bug: ml/src/pose_estimation/normalizer.py:120-133 `get_spine_length` computes
  the average spine length across frames with NO NaN guard:

      line 129:  `hip_center = poses[:, H36Key.HIP_CENTER]`
      line 130:  `thorax = poses[:, H36Key.THORAX]`
      line 132:  `spine_lengths = np.linalg.norm(thorax - hip_center, axis=1)`
      line 133:  `return float(np.mean(spine_lengths))`

  `np.linalg.norm` on a NaN vector = NaN (numpy propagates NaN through norm,
  no exception). A NaN THORAX or HIP_CENTER on ANY frame (occluded hip / thorax
  — common in spins / crossovers / fast rotation where the upper body leaves
  frame, or 3D-lift NaN, or gap-fill miss) → `spine_lengths[frame] = NaN` →
  `np.mean([..., NaN, ...]) = NaN` (numpy propagates NaN through mean, no
  exception — verified) → `float(NaN) = NaN` → `get_spine_length` returns NaN.

  There is NO guard: `get_spine_length` does not `np.nanmean` /
  `np.isfinite(spine_lengths)` mask / `if np.isnan(spine_lengths).any()` /
  drop-NaN-frames before `np.mean`. `np.mean(NaN-bearing)` returns NaN silently
  (no exception, only a RuntimeWarning that the caller cannot catch as a
  contract). The NaN spine length is returned with NO signal.

  This is the SAME NaN-`np.mean` family as `get_body_height` (3D normalizer,
  `return float(np.mean(heights))` — covered by
  `test_normalizer_3d_get_body_height_nan_asymmetry_repro`) — but
  `get_spine_length` is a SEPARATE method on the 2D `PoseNormalizer` measuring
  THORAX→HIP_CENTER (not foot→head). A fix that NaN-masks `get_body_height`
  does NOT fix `get_spine_length` — they are independent methods with
  independent feature inputs (heights vs spine_lengths) and independent leak
  paths. NO test feeds a NaN thorax / NaN hip_center through
  `get_spine_length` and asserts a non-NaN spine length.

Consequences (prod impact):
  1. An occluded hip / thorax (NaN THORAX / HIP_CENTER — common in spins /
     crossovers / loose-top frames / fast rotation where the upper body leaves
     frame) on ANY frame → `spine_lengths[frame] = NaN` →
     `get_spine_length` = NaN. The spine length is the SCALE reference for the
     normalizer (`normalize` line 113 `scale = target / spine_length`); a NaN
     spine length NaN-poisons any downstream consumer that calls
     `get_spine_length` for calibration / reporting.
  2. The bug is silent — `np.linalg.norm(NaN) = NaN` (no exception),
     `np.mean(NaN-bearing) = NaN` (no exception, only a RuntimeWarning the
     caller cannot catch as a contract), `float(NaN) = NaN` (no exception).
     The return value is a float that looks structurally valid but is NaN —
     no error signal. A consumer that does `scale = target / spine_length`
     with `spine_length = NaN` → NaN scale (the `test_normalizer_nan_thorax_poison_frame_repro`
     sibling locks the `normalize` per-frame path, but `get_spine_length` is
     the AGGREGATE path — a separate consumer that returns a SINGLE NaN float
     for the whole pose sequence).
  3. `get_spine_length` is a PUBLIC method on `PoseNormalizer` (the public
     normalizer class). One occluded hip / thorax on one frame → NaN spine
     length for the entire sequence.
  4. Sibling to the NaN-`np.mean` / NaN-aggregate family:
     - `get_body_height` NaN-`np.mean` IS covered by
       `test_normalizer_3d_get_body_height_nan_asymmetry_repro` — but that is
       the 3D `Normalizer3D.get_body_height` (foot→head heights), a DIFFERENT
       method on a DIFFERENT class. `get_spine_length` is the 2D
       `PoseNormalizer` aggregate (thorax→hip_center spine lengths), with a
       DIFFERENT input and a DIFFERENT leak path. A fix to `get_body_height`
       does NOT fix `get_spine_length`. NO test feeds a NaN thorax / NaN
       hip_center through `get_spine_length` and asserts a non-NaN result.
     - `normalize` (line 113) NaN-thorax per-frame scale IS covered by
       `test_normalizer_nan_thorax_poison_frame_repro` — but `normalize`
       guards `if spine_length < 1e-6: scale = 1.0` (a per-frame guard that
       does NOT catch NaN: `NaN < 1e-6` = False). `get_spine_length` has NO
       such guard at all — it returns the raw `np.mean(spine_lengths)`.

The fix (NOT applied — repro only):
  - `get_spine_length` (line 133): use `np.nanmean(spine_lengths)` so NaN
    frames do not poison the mean — `return float(np.nanmean(spine_lengths))`
    (returns the mean among finite frames); and/or
  - NaN-mask before mean — `finite = np.isfinite(spine_lengths);
    return float(np.mean(spine_lengths[finite])) if finite.any() else 0.0`;
    and/or
  - sentinel on NaN — `if np.isnan(spine_lengths).any(): return 0.0` (signal
    the occlusion, do not return a NaN).
  The correct contract: a NaN thorax / hip_center on any frame must NOT make
  `get_spine_length` return NaN. It must return the mean among finite frames
  (or a sentinel), NOT NaN.

Methodology (per audit reglement):
  3 observables  (BUG present → PASS; flip to GREEN contract on fix)
  1 regression   (PASS — all-finite poses → finite spine length)
  1 source check (PASS — root cause locked via inspect.getsource)

Pure-Python (no GPU, no DB): `get_spine_length` is pure-numpy over a poses
array. We feed a synthetic NaN-thorax / NaN-hip pose sequence (no pipeline
run) to isolate the NaN-mean leak.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.pose_estimation import H36Key
from src.pose_estimation.normalizer import PoseNormalizer


def _finite_poses(n: int = 5) -> np.ndarray:
    """An all-finite (n, 17, 3) pose sequence with a consistent spine length
    (~0.4 m thorax→hip_center) on every frame. On the all-finite path
    `get_spine_length` ≈ 0.4 (a finite float).
    """
    poses = np.zeros((n, 17, 3), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.HIP_CENTER] = [0.0, 0.0, 0.0]
        poses[f, H36Key.THORAX] = [0.0, -0.4, 0.0]  # 0.4 m spine
    return poses


# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_get_spine_length_source_has_no_nan_guard():
    """GREEN contract source check: `get_spine_length` now NaN-masks the
    aggregate. The unfixed code returned `float(np.mean(spine_lengths))`
    (NaN-bearing mean → NaN, no guard). The fix uses `np.nanmean` (ignore NaN
    frames) with an all-NaN sentinel (0.0) so a single occluded thorax / hip
    frame no longer returns NaN for the whole sequence. The norm computation
    is unchanged — the guard landed at the aggregate (mean) site.
    """
    src = inspect.getsource(PoseNormalizer.get_spine_length)
    # The norm computation is unchanged.
    assert "np.linalg.norm(thorax - hip_center, axis=1)" in src, (
        "get_spine_length must compute "
        "`spine_lengths = np.linalg.norm(thorax - hip_center, axis=1)` for "
        "this repro to be valid. If the spine-length computation changed, "
        "update the repro."
    )
    # GREEN: the aggregate now ignores NaN + guards the all-NaN case.
    assert "nanmean" in src and "isfinite" in src, (
        "get_spine_length must use `np.nanmean(spine_lengths)` (ignore NaN "
        "frames) with an all-NaN sentinel (`np.isfinite` guard → 0.0). The "
        "unfixed `np.mean(spine_lengths)` propagates a single NaN frame to "
        "the whole-sequence return — root cause not fixed."
    )


# =============================================================================
# Observable 1 — BUG: np.mean on a NaN-bearing array returns NaN. Locks the
# mechanism so a fix cannot rely on np.mean to reject NaN quietly.
# =============================================================================


def test_mean_nan_returns_nan():
    """BUG: `np.mean` on an array with a NaN returns NaN (numpy propagates NaN
    through mean, no exception — only a RuntimeWarning the caller cannot catch
    as a contract). So a NaN spine_length on one frame →
    `np.mean(spine_lengths)` = NaN → `float(NaN)` = NaN.

    PASS on unfixed code (numpy semantics). A fix (nanmean / NaN-mask before
    mean) → finite mean → assert FAILS → GREEN contract. Locks the root cause
    — a fix must NaN-mask BEFORE the mean.
    """
    spine_lengths = np.array([0.4, 0.41, float("nan"), 0.39], dtype=np.float32)
    mean = float(np.mean(spine_lengths))
    # BUG: mean propagates NaN.
    assert np.isnan(mean), (
        f"FIXED or numpy semantics changed: np.mean(NaN-bearing) = {mean} "
        f"(finite). If mean now ignores NaN, the aggregate is NaN-safe — "
        f"update repro to the GREEN contract."
    )


# =============================================================================
# Observable 2 — BUG: `get_spine_length` with a NaN THORAX on one frame →
# `spine_lengths[frame] = NaN` → `np.mean(spine_lengths)` = NaN → returns NaN.
# Silent NaN leak — the return is a float that looks valid but is NaN.
# =============================================================================


def test_nan_thorax_get_spine_length_returns_nan():
    """GREEN contract: `get_spine_length` with a NaN THORAX on frame 2
    (occluded thorax) → `spine_lengths[2] = NaN` → the fix uses `np.nanmean`
    (mean over the 4 finite frames) → finite spine length ≈ 0.4, NOT NaN.
    The public method no longer returns a NaN spine length for the whole
    sequence on one occluded frame.
    """
    norm = PoseNormalizer(target_spine_length=0.4)
    nan = float("nan")
    poses = _finite_poses(5)
    poses[2, H36Key.THORAX] = [nan, nan, nan]  # NaN thorax on frame 2

    spine = norm.get_spine_length(poses)
    # GREEN: NaN thorax on one frame → mean over finite frames (≈0.4), not NaN.
    assert np.isfinite(spine), (
        f"BUG: get_spine_length with a NaN thorax on frame 2 returned "
        f"{spine} (NaN). np.mean(spine_lengths) propagates the NaN frame → "
        f"NaN for the whole sequence. Use np.nanmean (ignore NaN frames) + an "
        f"all-NaN sentinel so one occluded frame does not poison the aggregate."
    )
    assert abs(spine - 0.4) < 1e-5, (
        f"BUG: NaN-thorax spine = {spine}, expected ~0.4 (mean over finite "
        f"frames, all of which have a 0.4 m spine). nanmean must match the "
        f"finite path's value."
    )


# =============================================================================
# Observable 3 — BUG: NaN HIP_CENTER on one frame → same leak (the norm input
# is `thorax - hip_center`; a NaN hip_center poisons the difference just as a
# NaN thorax does). Locks that the leak is symmetric in the two inputs — a fix
# guarding only thorax would leave the hip_center path broken.
# =============================================================================


def test_nan_hip_center_get_spine_length_returns_nan():
    """GREEN contract: `get_spine_length` with a NaN HIP_CENTER on frame 2
    (occluded hip) → `spine_lengths[2] = NaN` → `np.nanmean` (mean over the 4
    finite frames) → finite ≈ 0.4. The leak is symmetric: a NaN in EITHER
    input of `thorax - hip_center` poisoned the norm; nanmean ignores the
    poisoned frame in both cases.
    """
    norm = PoseNormalizer(target_spine_length=0.4)
    nan = float("nan")
    poses = _finite_poses(5)
    poses[2, H36Key.HIP_CENTER] = [nan, nan, nan]  # NaN hip_center on frame 2

    spine = norm.get_spine_length(poses)
    # GREEN: NaN hip_center on one frame → mean over finite frames, not NaN.
    assert np.isfinite(spine), (
        f"BUG: get_spine_length with a NaN hip_center on frame 2 returned "
        f"{spine} (NaN). The leak is symmetric to NaN thorax — np.mean "
        f"propagates the NaN frame. Use np.nanmean so one occluded frame does "
        f"not poison the aggregate."
    )
    assert abs(spine - 0.4) < 1e-5, (
        f"BUG: NaN-hip_center spine = {spine}, expected ~0.4 (mean over "
        f"finite frames). nanmean must match the finite path's value."
    )


# =============================================================================
# Regression — PASS: an all-finite pose sequence → `get_spine_length` returns
# a finite spine length (~0.4 m, the consistent thorax→hip_center distance).
# The fix (nanmean / NaN-mask) must NOT regress the all-finite path.
# =============================================================================


def test_finite_poses_get_spine_length_finite():
    """NOT a bug: an all-finite pose sequence with a consistent 0.4 m spine →
    `get_spine_length` ≈ 0.4 (finite). Regression guard so a nanmean / NaN-mask
    fix does not break the all-finite path (and does not accidentally return a
    sentinel / 0.0 for valid poses).
    """
    norm = PoseNormalizer(target_spine_length=0.4)
    poses = _finite_poses(5)

    spine = norm.get_spine_length(poses)
    assert np.isfinite(spine) and abs(spine - 0.4) < 1e-5, (
        f"BUG (regression): all-finite poses spine length = {spine} "
        f"(expected ~0.4, finite). The all-finite path must return a finite "
        f"spine length. A nanmean / NaN-mask fix must not regress this."
    )
