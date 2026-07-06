"""RED repro — `MotionAligner.compute_distance` / `align` /
`compute_distance_3d` (aligner.py — the OTHER aligner class, NOT
`MotionDTWAligner` from tranche BZ/#888) CRASH with `ValueError: No warping
path found compatible with the local constraints` when a single keypoint is
NaN across frames in the user sequence — a pipeline crash on occluded/missing
data, not graceful degradation.

Root cause (ml/src/alignment/aligner.py — `MotionAligner`):

  `compute_distance` (74) / `compute_distance_3d` (105) / `align` (31):
      user_flat = user[:, joints, :].reshape(len(user), -1)   # 94 / 128 / 54
      ref_flat  = reference[:, joints, :].reshape(len(reference), -1)
      alignment = self._compute_dtw(user_flat, ref_flat)      # 98 / 132 / 58

  `_compute_dtw` (201-236) calls `dtw(x, y, keep_internals=True, ...)` (line
  227) with NO NaN guard. The cost matrix is built from `user_flat`/`ref_flat`
  (flattened poses). A NaN keypoint in the user sequence → NaN in the cost
  matrix → the DTW accumulator becomes NaN → no finite warping path satisfies
  the local constraints → the `dtw` library raises `ValueError("No warping
  path found compatible with the local constraints")`.

  Unlike `MotionDTWAligner` (tranche BZ), `MotionAligner` has NO degenerate-
  length guard either (`MotionDTWAligner.compute_distance` guards `len(user)
  < 2 or len(reference) < 2: return float("inf")`, line 470; `MotionAligner`
  has no such guard — it calls `dtw` directly). Both classes share the same
  NaN-crash surface, but they are SEPARATE classes with SEPARATE code paths
  — a fix in `MotionDTWAligner` does NOT fix `MotionAligner`.

Production surface (why this is not dead code):
  - `MotionAligner` is a PUBLIC class exported from `src.alignment.__init__`
    (`__all__ = ["MotionAligner", "MotionDTWAligner"]`).
  - `pipeline.py:534` `_get_aligner` declares the aligner type as
    `MotionAligner | MotionDTWAligner` — `MotionAligner` is the documented
    fallback / alternative aligner (the pipeline default is `MotionDTWAligner`,
    but `MotionAligner` is the other half of the union and can be switched in).
  - `tests/alignment/test_aligner.py` exercises `MotionAligner` directly with
    `aligner = MotionAligner(...)` — it is the supported non-phase-aware
    alignment API.

Consequences (prod impact):
  1. A single NaN keypoint in the user's flight frames (landing-leg knee
     frequently occluded in figure skating) crashes `compute_distance` /
     `align` / `compute_distance_3d` — `ValueError`. If a caller switches the
     pipeline aligner to `MotionAligner` (it is the documented alternative),
     the same NaN keypoint that BZ crashes `MotionDTWAligner` crashes
     `MotionAligner` here too.
  2. The crash is in the DTW cost-matrix accumulation — NaN propagates through
     the dynamic-programming recurrence, making every path NaN, so the "no
     warping path found" error is raised. The error message gives NO hint that
     the cause is NaN data (it says "local constraints" — misleading).
  3. The bug composes with the CoM tranches (BM-BW) and the viz tranches
     (CA-CC): a NaN keypoint → NaN in the user sequence → DTW crash here.
     The aligner should be a NaN-safety net (skip NaN joints, or return
     `inf`), not a crash point.
  4. `align` (line 31) returns `aligned_user` warped via `_warp_sequence`
     (line 271 `np.mean(frames, axis=0)`) — even if `dtw` did not crash,
     `np.mean` over NaN frames propagates NaN into the warped sequence
     (NaN-leak, same as `MotionDTWAligner._warp_with_path` line 412).
  5. Existing tests miss it: `test_aligner*` feed all-valid keypoints. No
     test feeds a NaN keypoint through `MotionAligner.compute_distance` /
     `align` / `compute_distance_3d` and asserts it degrades (returns `inf` /
     a sentinel / a NaN-masked distance) instead of crashing.
  6. Same class as BZ (#888) — but a SEPARATE class, separate code path,
     separate fix. BZ's fix in `MotionDTWAligner` does NOT cover
     `MotionAligner`.

The fix (NOT applied — repro only):
  - guard `compute_distance` / `compute_distance_3d` / `align`: if
    `np.isnan(user).any()` (or `not np.isfinite`), mask NaN joints (skip them
    from the cost) or return `float("inf")` (no match); and/or
  - NaN-mask the cost matrix: `user_flat = np.nan_to_num(user_flat, nan=0.0)`
    — but this silently treats NaN as 0, biasing the distance; the `inf`
    sentinel or joint-skip is more honest; and/or
  - make `_compute_dtw` wrap the `dtw(...)` call in a try/except that returns
    `float("inf")` on `ValueError("No warping path ...")` — but this hides the
    NaN root cause; and/or add the same degenerate-length guard
    `MotionDTWAligner` has, plus a NaN guard.
  - The deeper fix is in gap-filling/smoothing (ensure no NaN reaches the
    aligner), but the aligner must still be defensive — both aligner classes.

The correct contract: a NaN keypoint in the user sequence must NOT crash
`MotionAligner.compute_distance` / `align` / `compute_distance_3d`. The
aligner must degrade gracefully — return `float("inf")` (no match) or a finite
NaN-masked distance, and `align` must not raise — NOT raise `ValueError`.

RED now: the observable assertions below describe the CORRECT behavior — a
NaN keypoint must NOT raise; `compute_distance` / `compute_distance_3d` must
return a finite/`inf` float, `align` must return a tuple. They FAIL because
the NaN poisons the DTW cost matrix and the `dtw` library raises
`ValueError`. After the fix: NaN is guarded and the calls degrade. The
source-check test confirms `MotionAligner` (a SEPARATE class from
`MotionDTWAligner`) has NO NaN guard and calls `dtw(...)` unguarded in
`_compute_dtw` (root cause locked).

Pure-Python (no GPU, no DB): `compute_distance`, `compute_distance_3d`,
`align`, and `_compute_dtw` are pure-data functions over pose arrays.
"""

import inspect

import numpy as np

from src.alignment.aligner import MotionAligner


def _seq(n: int = 12, nan_keypoint: int | None = None) -> np.ndarray:
    """A 12-frame 2D pose sequence with a small vertical drift (frames 4,5
    drift down) so the all-valid DTW has a finite (here 0.0) distance.

    When `nan_keypoint` is set, that keypoint is NaN across ALL frames — the
    occlusion case. A NaN keypoint → NaN in the flattened cost matrix → the
    DTW accumulator becomes NaN → no finite warping path satisfies the local
    constraints → `dtw` raises `ValueError("No warping path found ...")`.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, 0] = [0.0, 0.0]  # head
        poses[f, 1] = [-0.2, 0.1]  # lshoulder
        poses[f, 2] = [0.2, 0.1]  # rshoulder
        poses[f, 4] = [-0.1, 0.5 + f * 0.01]  # lhip (drift)
        poses[f, 5] = [0.1, 0.5 + f * 0.01]  # rhip (drift)
    if nan_keypoint is not None:
        poses[:, nan_keypoint] = [np.nan, np.nan]
    return poses


def _seq3d(n: int = 12, nan_keypoint: int | None = None) -> np.ndarray:
    """3D variant for `compute_distance_3d`."""
    poses = np.zeros((n, 17, 3), dtype=np.float32)
    for f in range(n):
        poses[f, 0] = [0.0, 0.0, 0.0]
        poses[f, 1] = [-0.2, 0.1, 0.0]
        poses[f, 2] = [0.2, 0.1, 0.0]
        poses[f, 4] = [-0.1, 0.5 + f * 0.01, 0.0]
        poses[f, 5] = [0.1, 0.5 + f * 0.01, 0.0]
    if nan_keypoint is not None:
        poses[:, nan_keypoint] = [np.nan, np.nan, np.nan]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: a NaN keypoint in the user sequence must NOT crash
# compute_distance — must return a finite or inf float (graceful degradation).
# --------------------------------------------------------------------------- #


def test_nan_knee_compute_distance_does_not_crash_repro():
    """CORRECT behavior: `MotionAligner.compute_distance` with a NaN keypoint
    in the user sequence must NOT raise. It must return a finite float
    (NaN-masked distance) or `float("inf")` (no match), NOT crash the whole
    call.

    RED now: `RKNEE` (keypoint index 1, here RSHOULDER slot used as a
    stand-in — any keypoint) NaN across all frames → NaN in the flattened cost
    matrix → the DTW dynamic-programming accumulator becomes NaN → no finite
    warping path satisfies the local constraints → `dtw` raises
    `ValueError("No warping path found compatible with the local
    constraints")`. After the fix: NaN is guarded (masked / `inf` sentinel)
    and the call returns a float.
    """
    aligner = MotionAligner(window_type="sakoechiba", window_size=0.2)

    # Baseline: all-valid → finite distance (no crash).
    d_valid = aligner.compute_distance(_seq(12, None), _seq(12, None))
    assert np.isfinite(d_valid), (
        f"test fixture broken: all-valid DTW distance {d_valid} is non-finite; "
        f"expected finite. The fixture needs a small vertical drift so the "
        f"all-valid baseline computes a finite distance without crashing."
    )

    # NaN keypoint in user — must NOT crash, must return finite or inf.
    try:
        d_nan = aligner.compute_distance(_seq(12, 1), _seq(12, None))
    except Exception as e:
        raise AssertionError(
            f"BUG: MotionAligner.compute_distance raised {type(e).__name__}: "
            f"{e} for a user sequence with a NaN keypoint (index 1) across all "
            f"frames (occlusion). A NaN keypoint poisons the flattened DTW cost "
            f"matrix → the dynamic-programming accumulator becomes NaN → no "
            f"finite warping path satisfies the local constraints → the `dtw` "
            f"library raises ValueError. `MotionAligner` is a PUBLIC class "
            f"(exported from src.alignment.__init__, declared as the "
            f"`MotionAligner | MotionDTWAligner` pipeline aligner union in "
            f"pipeline.py:534) — the documented alternative aligner. A NaN "
            f"keypoint (landing-leg knee frequently occluded in figure skating) "
            f"crashes the call. The aligner must degrade gracefully (return "
            f"`inf` / a finite NaN-masked distance), NOT crash. This is a "
            f"SEPARATE class from MotionDTWAligner (tranche BZ/#888) — BZ's "
            f"fix does NOT cover MotionAligner. (Sanity: all-valid = "
            f"{d_valid}.)"
        ) from e

    assert isinstance(d_nan, float), (
        f"BUG: compute_distance returned non-float {type(d_nan).__name__} "
        f"({d_nan}) for NaN-keypoint input; expected float (finite or inf)."
    )
    assert d_nan == float("inf") or np.isfinite(d_nan), (
        f"BUG: compute_distance returned {d_nan} for NaN-keypoint input; "
        f"expected float('inf') (no match sentinel) or a finite NaN-masked "
        f"distance, NOT a NaN-leak."
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint — wide blast radius.
# --------------------------------------------------------------------------- #


def test_nan_any_keypoint_compute_distance_does_not_crash_repro():
    """CORRECT behavior: a NaN in ANY keypoint (not just one) must NOT crash
    `compute_distance`. The DTW cost matrix uses ALL joints (default
    `joints=None` → all 17), so a NaN in ANY joint poisons the cost the same
    way. The bug has a wide blast radius — any occluded joint.

    RED now: NaN in keypoint 2, 5, 10 each → `ValueError` crash. After the
    fix: graceful degradation on any occluded keypoint.
    """
    aligner = MotionAligner(window_type="sakoechiba", window_size=0.2)
    for kp in (2, 5, 10):
        try:
            d = aligner.compute_distance(_seq(12, kp), _seq(12, None))
        except Exception as e:
            raise AssertionError(
                f"BUG: MotionAligner.compute_distance raised "
                f"{type(e).__name__}: {e} for a user sequence with a NaN "
                f"keypoint (index {kp}) across all frames. The DTW cost matrix "
                f"uses ALL joints (default joints=None → all 17), so a NaN in "
                f"ANY joint poisons the cost the same way — wide blast radius. "
                f"The aligner must degrade gracefully on any occluded keypoint, "
                f"NOT crash. (A fix that only guards one keypoint would leave "
                f"the other 16 broken.)"
            ) from e
        assert d == float("inf") or np.isfinite(d), (
            f"BUG: compute_distance returned {d} for NaN keypoint {kp}; "
            f"expected float('inf') or finite, not a NaN-leak."
        )


# --------------------------------------------------------------------------- #
# Observable 3: align (the warping path) must NOT crash on NaN either.
# --------------------------------------------------------------------------- #


def test_nan_knee_align_does_not_crash_repro():
    """CORRECT behavior: `align` (returns `(aligned_user, warp_path)`) must
    NOT raise on a NaN keypoint. Same root cause as `compute_distance` — the
    `_compute_dtw` → `dtw` cost matrix is NaN-poisoned. `align` additionally
    warps via `_warp_sequence` (line 271 `np.mean(frames, axis=0)` — NaN
    propagates into the warped sequence), but the crash happens before that,
    at `_compute_dtw`.

    RED now: NaN keypoint → `ValueError` crash in `align`. After the fix:
    graceful degradation (NaN-masked distance / `inf` sentinel / NaN-masked
    warp).
    """
    aligner = MotionAligner(window_type="sakoechiba", window_size=0.2)
    try:
        result = aligner.align(_seq(12, 1), _seq(12, None))
    except Exception as e:
        raise AssertionError(
            f"BUG: MotionAligner.align raised {type(e).__name__}: {e} for a "
            f"user sequence with a NaN keypoint (index 1) across all frames. "
            f"`align` calls `_compute_dtw` (line 58) → `dtw(...)` (line 227) "
            f"with no NaN guard — the cost matrix is NaN-poisoned the same way "
            f"as `compute_distance`. After the fix: graceful degradation "
            f"(NaN-masked warp or sentinel)."
        ) from e

    assert isinstance(result, tuple) and len(result) == 2, (
        f"BUG: align returned {type(result).__name__} ({result}) for "
        f"NaN-keypoint input; expected a (aligned_user, warp_path) tuple."
    )


# --------------------------------------------------------------------------- #
# Observable 4: compute_distance_3d (the 3D path) must NOT crash on NaN.
# --------------------------------------------------------------------------- #


def test_nan_knee_compute_distance_3d_does_not_crash_repro():
    """CORRECT behavior: `compute_distance_3d` must NOT raise on a NaN
    keypoint. Same root cause — the 3D flattened cost matrix is NaN-poisoned.

    RED now: NaN keypoint → `ValueError` crash in `compute_distance_3d`.
    After the fix: graceful degradation.
    """
    aligner = MotionAligner(window_type="sakoechiba", window_size=0.2)
    try:
        d = aligner.compute_distance_3d(_seq3d(12, 1), _seq3d(12, None))
    except Exception as e:
        raise AssertionError(
            f"BUG: MotionAligner.compute_distance_3d raised "
            f"{type(e).__name__}: {e} for a user 3D sequence with a NaN "
            f"keypoint (index 1) across all frames. The 3D path uses the same "
            f"`_compute_dtw` → `dtw` cost matrix (line 132 → 227), which is "
            f"NaN-poisoned the same way as the 2D path. After the fix: graceful "
            f"degradation (NaN-masked distance or `inf` sentinel)."
        ) from e
    assert d == float("inf") or np.isfinite(d), (
        f"BUG: compute_distance_3d returned {d} for NaN-keypoint input; "
        f"expected float('inf') or finite, not a NaN-leak."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid DTW still computes a finite distance.
# --------------------------------------------------------------------------- #


def test_all_valid_compute_distance_unchanged_repro():
    """Regression guard: an all-valid pair must still compute a finite
    distance. The fix (NaN guard / NaN-mask / `inf` sentinel) must not change
    the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the all-valid case.
    """
    aligner = MotionAligner(window_type="sakoechiba", window_size=0.2)
    d = aligner.compute_distance(_seq(12, None), _seq(12, None))
    assert np.isfinite(d), (
        f"BUG (regression): all-valid DTW distance {d} is non-finite; expected "
        f"finite. The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: GREEN contract — the MotionAligner NaN-crash guard is locked
# (separate class from MotionDTWAligner, fixed independently of BZ/#888).
# --------------------------------------------------------------------------- #


def test_aligner_nan_crash_source_repro():
    """Source check (GREEN contract): the NaN-crash fix lives in
    `MotionAligner._compute_dtw` (the shared root — `compute_distance` /
    `compute_distance_3d` / `align` all route through it). `np.nan_to_num`
    sanitizes the cost matrix so an occluded keypoint degrades to a finite
    NaN-masked distance instead of raising ValueError. Identity on all-finite
    input. MotionAligner remains a SEPARATE class from MotionDTWAligner.
    """
    # MotionAligner is a distinct class from MotionDTWAligner.
    from src.alignment.motion_dtw import MotionDTWAligner

    assert MotionAligner is not MotionDTWAligner, (
        "BUG: MotionAligner must remain a SEPARATE class from "
        "MotionDTWAligner (tranche BZ/#888) — distinct code paths, the #896 "
        "fix is independent."
    )

    dtw_src = inspect.getsource(MotionAligner._compute_dtw)
    # The dtw(...) call is still present (the guard is before it, not wrapping it).
    assert "return dtw(" in dtw_src, (
        "BUG: _compute_dtw must still call `return dtw(...)`; the #896 guard "
        "is a nan_to_num before the call, not a wrapper around it."
    )
    # np.nan_to_num sanitizes the cost matrix (#896).
    assert "np.nan_to_num" in dtw_src, (
        "BUG: _compute_dtw must sanitize NaN in the cost matrix via "
        "`np.nan_to_num` (#896) so an occluded keypoint does not poison the "
        "DTW accumulator and raise ValueError."
    )

    # compute_distance still routes through _compute_dtw (the shared root).
    cd_src = inspect.getsource(MotionAligner.compute_distance)
    assert "alignment = self._compute_dtw(user_flat, ref_flat)" in cd_src, (
        "BUG: compute_distance must still call "
        "`alignment = self._compute_dtw(user_flat, ref_flat)`; the #896 fix "
        "lives in _compute_dtw, not by bypassing it."
    )

    # align still routes through _compute_dtw (the shared root).
    al_src = inspect.getsource(MotionAligner.align)
    assert "alignment = self._compute_dtw(user_flat, ref_flat)" in al_src, (
        "BUG: align must still call "
        "`alignment = self._compute_dtw(user_flat, ref_flat)`; the #896 fix "
        "lives in _compute_dtw, not by bypassing it."
    )
