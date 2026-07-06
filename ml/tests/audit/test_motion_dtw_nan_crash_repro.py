"""RED repro — `MotionDTWAligner.compute_distance` (and
`align_with_keyframes`) CRASH with `ValueError: No warping path found
compatible with the local constraints` when a single keypoint is NaN across
frames in the user sequence — a pipeline crash on occluded/missing data, not
graceful degradation.

Root cause (ml/src/alignment/motion_dtw.py):
  `compute_distance` (442) → `align_with_keyframes` (107) → for each phase,
  `_align_phase` (303) → `_compute_dtw` (338) → `dtw(...)`. The cost matrix
  is built from `user_flat`/`ref_flat` (flattened poses). A NaN keypoint in
  the user sequence → NaN in the cost matrix → the DTW accumulator becomes
  NaN → no finite warping path satisfies the local constraints → the `dtw`
  library raises `ValueError("No warping path found compatible with the local
  constraints")`.

  `compute_distance` has a guard for `len(user) < 2 or len(reference) < 2`
  (line 470, returns `inf`) but NO guard for NaN in the data. A NaN keypoint
  (common — one occluded joint, see BM-BX CoM tranches) crashes the whole
  call instead of degrading to `inf` (no match) or a finite NaN-masked
  distance.

`pipeline.py:336` calls `aligner.compute_distance(...)` (2D path) /
`compute_distance_3d` (3D path, line 331) UNWRAPPED in try/except (the Stage 6
block, lines 318-340, has no exception guard). A NaN keypoint in
`normalized[phases.start : phases.end]` → `compute_distance` raises → the
entire `process_video` arq job crashes. This is a HARD pipeline crash on
occluded-data input, not a graceful degradation.

Consequences (prod impact):
  1. A single NaN keypoint in the user's flight frames (landing-leg knee
     frequently occluded in figure skating) crashes the whole video-analysis
     arq job — no report, no metrics, no GOE. The user uploads a video and
     gets a server error instead of a degraded-but-useful analysis.
  2. The crash is in the DTW cost-matrix accumulation — NaN propagates through
     the dynamic-programming recurrence, making every path NaN, so the "no
     warping path found" error is raised. The error message gives NO hint that
     the cause is NaN data (it says "local constraints" — misleading).
  3. The bug composes with the CoM tranches: a NaN keypoint → NaN in
     `normalized` (if gap-filling/smoothing fails to fill it) → DTW crash
     here. The aligner should be a NaN-safety net (skip NaN joints, or
     return `inf`), not a crash point.
  4. Existing tests miss it: `test_motion_dtw*` / `test_aligner*` feed
     all-valid keypoints. No test feeds a NaN keypoint through
     `compute_distance` and asserts it degrades (returns `inf` / a sentinel)
     instead of crashing.

The fix (NOT applied — repro only):
  - guard `compute_distance` / `align_with_keyframes`: if `np.isnan(user).any()`
    (or `not np.isfinite`), mask NaN joints (skip them from the cost) or
    return `float("inf")` (no match — the same sentinel as the <2-frame guard);
    and/or
  - NaN-mask the cost matrix: `user_flat = np.nan_to_num(user_flat, nan=0.0)` —
    but this silently treats NaN as 0, which biases the distance; the `inf`
    sentinel or joint-skip is more honest; and/or
  - wrap the `dtw(...)` call in `_compute_dtw` with a try/except that returns
    `float("inf")` on `ValueError("No warping path ...")` — but this hides the
    NaN root cause (a finite-masked distance is better than a blanket `inf`).
  - The deeper fix is in gap-filling/smoothing (ensure no NaN reaches the
    aligner), but the aligner must still be defensive.

The correct contract: a NaN keypoint in the user sequence must NOT crash
`compute_distance` (or `align_with_keyframes`). The aligner must degrade
gracefully — return `float("inf")` (no match, same as the <2-frame guard) or
a finite NaN-masked distance — NOT raise `ValueError`.

RED now: the observable assertions below describe the CORRECT behavior — a
NaN keypoint must NOT raise; `compute_distance` must return a finite/`inf`
float. They FAIL because the NaN poisons the DTW cost matrix and the `dtw`
library raises `ValueError`. After the fix: NaN is guarded and the call
returns `inf` (or a finite masked distance). The source-check test confirms
the `if len(user) < 2 or len(reference) < 2: return float("inf")` guard
exists (degenerate-length guard) but NO NaN guard follows it, and the
unguarded `result = self.align_with_keyframes(...)` call is present (root
cause locked).

Pure-Python (no GPU, no DB): `compute_distance` and `align_with_keyframes`
are pure-data functions over pose arrays.
"""

import inspect

import numpy as np

from src.alignment.motion_dtw import MotionDTWAligner


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


# --------------------------------------------------------------------------- #
# Observable 1: a NaN keypoint in the user sequence must NOT crash
# compute_distance — must return a finite or inf float (graceful degradation).
# --------------------------------------------------------------------------- #


def test_nan_knee_compute_distance_does_not_crash_repro():
    """CORRECT behavior: `compute_distance` with a NaN keypoint in the user
    sequence must NOT raise. It must return a finite float (NaN-masked
    distance) or `float("inf")` (no match — the same sentinel as the
    <2-frame degenerate guard, line 470), NOT crash the whole call.

    RED now: `RKNEE` (keypoint index 2, here RSHOULDER slot used as a stand-in
    — any keypoint) NaN across all frames → NaN in the flattened cost matrix
    → the DTW dynamic-programming accumulator becomes NaN → no finite warping
    path satisfies the local constraints → `dtw` raises `ValueError("No
    warping path found compatible with the local constraints")`. After the
    fix: NaN is guarded (masked / `inf` sentinel) and the call returns a float.
    """
    aligner = MotionDTWAligner(window_type="sakoechiba", window_size=0.2)

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
            f"BUG: MotionDTWAligner.compute_distance raised {type(e).__name__}: "
            f"{e} for a user sequence with a NaN keypoint (index 1) across all "
            f"frames (occlusion). A NaN keypoint poisons the flattened DTW cost "
            f"matrix → the dynamic-programming accumulator becomes NaN → no "
            f"finite warping path satisfies the local constraints → the `dtw` "
            f"library raises ValueError. `pipeline.py:336` calls "
            f"`compute_distance(...)` UNWRAPPED in try/except — a NaN keypoint "
            f"crashes the whole `process_video` arq job (no report, no metrics, "
            f"no GOE). The aligner must degrade gracefully (return `inf` / a "
            f"finite NaN-masked distance), NOT crash. (Sanity: all-valid = "
            f"{d_valid}.)"
        ) from e

    # If it did not crash, the result must be a finite or inf float (not NaN).
    assert isinstance(d_nan, float), (
        f"BUG: compute_distance returned non-float {type(d_nan).__name__} "
        f"({d_nan}) for NaN-keypoint input; expected float (finite or inf)."
    )
    assert d_nan == float("inf") or np.isfinite(d_nan), (
        f"BUG: compute_distance returned {d_nan} for NaN-keypoint input; "
        f"expected float('inf') (no match sentinel) or a finite NaN-masked "
        f"distance, NOT a NaN-leak (which breaks downstream JSON / GOE)."
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint, not just one — a
# NaN in any joint crashes the call.
# --------------------------------------------------------------------------- #


def test_nan_any_keypoint_compute_distance_does_not_crash_repro():
    """CORRECT behavior: a NaN in ANY keypoint (not just one) must NOT crash
    `compute_distance`. The DTW cost matrix uses ALL joints (default
    `joints=None` → all 17), so a NaN in ANY joint poisons the cost the same
    way. The bug has a wide blast radius — any occluded joint.

    RED now: NaN in keypoint 2, 5, 10 each → `ValueError` crash. After the
    fix: graceful degradation on any occluded keypoint.
    """
    aligner = MotionDTWAligner(window_type="sakoechiba", window_size=0.2)
    for kp in (2, 5, 10):
        try:
            d = aligner.compute_distance(_seq(12, kp), _seq(12, None))
        except Exception as e:
            raise AssertionError(
                f"BUG: MotionDTWAligner.compute_distance raised "
                f"{type(e).__name__}: {e} for a user sequence with a NaN "
                f"keypoint (index {kp}) across all frames. The DTW cost matrix "
                f"uses ALL joints (default joints=None → all 17), so a NaN in ANY "
                f"joint poisons the cost the same way — wide blast radius. The "
                f"aligner must degrade gracefully on any occluded keypoint, NOT "
                f"crash. (A fix that only guards one keypoint would leave the "
                f"other 16 broken.)"
            ) from e
        assert d == float("inf") or np.isfinite(d), (
            f"BUG: compute_distance returned {d} for NaN keypoint {kp}; expected "
            f"float('inf') or finite, not a NaN-leak."
        )


# --------------------------------------------------------------------------- #
# Observable 3: align_with_keyframes (the phase-aware path) must NOT crash
# on NaN either — same root cause.
# --------------------------------------------------------------------------- #


def test_nan_knee_align_with_keyframes_does_not_crash_repro():
    """CORRECT behavior: `align_with_keyframes` (the phase-aware alignment
    path, used internally by `compute_distance` and directly by callers) must
    NOT raise on a NaN keypoint. Same root cause as `compute_distance` — the
    per-phase `_align_phase` → `_compute_dtw` → `dtw` cost matrix is NaN-poisoned.

    RED now: NaN keypoint → `ValueError` crash in `align_with_keyframes`.
    After the fix: graceful degradation.
    """
    from src.types import ElementPhase

    aligner = MotionDTWAligner(window_type="sakoechiba", window_size=0.2)
    up = ElementPhase(name="j", start=0, takeoff=2, peak=6, landing=10, end=11)
    rp = ElementPhase(name="j", start=0, takeoff=2, peak=6, landing=10, end=11)

    try:
        result = aligner.align_with_keyframes(_seq(12, 1), up, _seq(12, None), rp)
    except Exception as e:
        raise AssertionError(
            f"BUG: MotionDTWAligner.align_with_keyframes raised "
            f"{type(e).__name__}: {e} for a user sequence with a NaN keypoint "
            f"(index 1) across all frames. The phase-aware path uses the same "
            f"`_align_phase` → `_compute_dtw` → `dtw` cost matrix, which is "
            f"NaN-poisoned the same way as `compute_distance`. After the fix: "
            f"graceful degradation (NaN-masked distance or `inf` sentinel)."
        ) from e


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
    aligner = MotionDTWAligner(window_type="sakoechiba", window_size=0.2)
    d = aligner.compute_distance(_seq(12, None), _seq(12, None))
    assert np.isfinite(d), (
        f"BUG (regression): all-valid DTW distance {d} is non-finite; expected "
        f"finite. The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — degenerate-length guard exists, but NO
# NaN guard follows it; unguarded align_with_keyframes call.
# --------------------------------------------------------------------------- #


def test_motion_dtw_nan_crash_source_repro():
    """Source check: the NaN-crash fix lives in `_compute_dtw` (the shared
    root — both the 2D phase path via `_align_phase` and the 3D
    `compute_distance_3d` path route through it). A `nan_to_num` guard there
    sanitizes the cost matrix so an occluded keypoint degrades to a finite
    NaN-masked distance instead of raising `ValueError`. Identity on
    all-finite input — the all-valid case is unchanged.

    GREEN contract: `_compute_dtw` source contains `np.nan_to_num` (the
    NaN-guard), and `compute_distance` still has the degenerate-length
    `inf` sentinel + the phase-aware `align_with_keyframes` call.
    """
    dtw_src = inspect.getsource(MotionDTWAligner._compute_dtw)
    assert "np.nan_to_num" in dtw_src, (
        "BUG: _compute_dtw must sanitize NaN in the cost matrix via "
        "`np.nan_to_num` (the #888 NaN-crash guard). A NaN keypoint must not "
        "poison the DTW accumulator and raise ValueError — the guard degrades "
        "to a finite NaN-masked distance."
    )
    cd_src = inspect.getsource(MotionDTWAligner.compute_distance)
    # The degenerate-length guard still exists (returns inf) — the NaN guard
    # is an addition, not a replacement of the existing inf sentinel.
    assert (
        "if len(user) < 2 or len(reference) < 2:" in cd_src and 'return float("inf")' in cd_src
    ), (
        "BUG: compute_distance must still guard `len(user) < 2 or "
        "len(reference) < 2: return float('inf')` (degenerate-length sentinel); "
        "the #888 NaN guard is an addition, not a replacement."
    )
    # The phase-aware alignment call is still present (the fix did not bypass it).
    assert (
        "result = self.align_with_keyframes(user, user_phases, reference, ref_phases, joints)"
        in cd_src
    ), (
        "BUG: compute_distance must still call "
        "`result = self.align_with_keyframes(user, user_phases, reference, "
        "ref_phases, joints)`; the #888 fix lives in _compute_dtw, not by "
        "bypassing the phase-aware path."
    )
