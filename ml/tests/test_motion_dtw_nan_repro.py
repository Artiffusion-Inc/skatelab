"""RED repro — `MotionDTWAligner._warp_with_path` and
`MotionAligner._warp_sequence` crash with `ValueError: cannot convert float
NaN to integer` (and `IndexError` from `int(NaN).astype(int)`) when the DTW
warp path contains NaN entries (tranche HD / #1097).

Root cause:
  motion_dtw.py:430 — `warped[ref_idx] = sequence[int(user_indices[0])]`
    → int(NaN) raises `ValueError: cannot convert float NaN to integer`.
  motion_dtw.py:433 — `frames = sequence[user_indices.astype(int)]`
    → NaN truncates to a huge negative int → `IndexError`.
  aligner.py:293 — `warped[i] = sequence[int(user_indices[0])]`
    → same int(NaN) crash.
  aligner.py:296 — `frames = sequence[user_indices.astype(int)]`
    → same IndexError on NaN.

The warp functions consume the DTW path produced by `dtw(...)`. A NaN entry
in the path (from NaN in the cost matrix — see #1090 + tranche BZ upstream)
crashes the warp at the int cast. The path is filtered/used per-element, so
the bug is in the SHARED warp layer (one guard in each function fixes every
caller routing through it).

The fix (NOT applied — repro only):
  - Filter NaN before the int cast: `valid = user_indices[np.isfinite(user_indices)]`
  - If all indices are NaN → fall back to nearest-neighbor (mirrors the
    `len(user_indices) == 0` branch — same contract).

This test locks the contract: a NaN entry in the warp path must NOT raise.
The function must degrade gracefully — produce a finite warped sequence
(matching the no-NaN regression case). The source-check test confirms the
`np.isfinite` guard is present in the warp function bodies (the #1097
NaN-warp guard).

Pure-Python (no GPU, no DB): `_warp_with_path` and `_warp_sequence` are
pure-data functions over pose arrays.
"""

import inspect

import numpy as np

from src.alignment.aligner import MotionAligner
from src.alignment.motion_dtw import MotionDTWAligner


def _seq(n: int = 6) -> np.ndarray:
    """A small 2D pose sequence — 6 frames, 17 keypoints, all finite."""
    rng = np.random.default_rng(0)
    return rng.random((n, 17, 2), dtype=np.float32)


# --------------------------------------------------------------------------- #
# Observable 1: _warp_with_path must NOT crash on a NaN warp_path entry.
# --------------------------------------------------------------------------- #


def test_warp_with_path_nan_entry_does_not_crash_repro():
    """CORRECT behavior: a single NaN in `warp_path[:, 0]` (the user-index
    column) must NOT raise `ValueError: cannot convert float NaN to integer`
    at `int(user_indices[0])`. Must return a finite warped sequence.

    RED now: NaN entry in warp_path[:, 0] → `int(NaN)` → `ValueError` at
    line 430 (`sequence[int(user_indices[0])]`). After the fix: NaN indices
    are filtered via `np.isfinite`; if all are NaN for a ref frame, the
    function falls back to nearest-neighbor (mirrors the
    `len(user_indices) == 0` branch). The fix is in `_warp_with_path` (the
    SHARED warp function — one guard fixes every caller routing through it).
    """
    aligner = MotionDTWAligner(window_type="sakoechiba", window_size=0.2)
    seq = _seq(6)
    # warp_path shape (N, 2): col 0 = user index, col 1 = ref index.
    # Inject NaN at user-index 0 of the first row → that ref frame (0)
    # sees user_indices containing NaN.
    warp_path = np.array(
        [
            [np.nan, 0],  # NaN user index → int(NaN) crash
            [1.0, 1.0],
            [2.0, 2.0],
            [3.0, 3.0],
            [4.0, 4.0],
            [5.0, 5.0],
        ],
        dtype=np.float64,
    )

    try:
        warped = aligner._warp_with_path(seq, warp_path, target_length=6)  # type: ignore[reportPrivateUsage]
    except (ValueError, IndexError) as e:
        raise AssertionError(
            f"BUG: MotionDTWAligner._warp_with_path raised {type(e).__name__}: "
            f"{e} for a warp_path with a NaN user-index entry. "
            f"`int(NaN) = ValueError` (line 430) and `user_indices.astype(int)` "
            f"of NaN truncates to a huge negative int → IndexError (line 433). "
            f"The #1097 fix: filter NaN via `np.isfinite` BEFORE the int cast — "
            f"`valid = user_indices[np.isfinite(user_indices)]`. If all are NaN "
            f"for a ref frame, fall back to nearest-neighbor (mirrors the "
            f"`len(user_indices) == 0` branch). This guard in the SHARED warp "
            f"function fixes every caller routing through it (1 fix, not N)."
        ) from e

    # If it did not crash, the output must be a finite array of the right shape.
    assert warped.shape == (6, 17, 2), (
        f"BUG: _warp_with_path returned shape {warped.shape}; expected (6, 17, 2)."
    )
    assert np.all(np.isfinite(warped)), (
        "BUG: _warp_with_path returned non-finite values for NaN-warp-path input; "
        "expected all-finite (NaN-masked warped sequence). NaN-leak breaks "
        "downstream JSON / GOE."
    )


# --------------------------------------------------------------------------- #
# Observable 2: _warp_with_path must NOT crash on NaN propagating through
# `user_indices.astype(int)` (the multi-mapping branch, line 433).
# --------------------------------------------------------------------------- #


def test_warp_with_path_nan_multimap_does_not_crash_repro():
    """CORRECT behavior: NaN in `warp_path[:, 0]` for a ref frame with
    MULTIPLE user mappings (the `else` branch, line 433) must NOT raise
    `IndexError` from `user_indices.astype(int)` (NaN truncates to a huge
    negative int). Must return a finite warped sequence.

    RED now: `frames = sequence[user_indices.astype(int)]` with NaN in
    user_indices → NaN truncates → huge negative index → `IndexError`.
    After the fix: `np.isfinite` mask before `astype(int)`; if all are NaN
    for a ref frame, fall back to nearest-neighbor.
    """
    aligner = MotionDTWAligner(window_type="sakoechiba", window_size=0.2)
    seq = _seq(6)
    # Two rows map to ref_idx=0 — multi-mapping branch (line 432-434).
    # First row has NaN user-index → user_indices contains NaN.
    warp_path = np.array(
        [
            [np.nan, 0],
            [0.0, 0],  # multi-mapping at ref 0
            [1.0, 1.0],
            [2.0, 2.0],
            [3.0, 3.0],
            [4.0, 4.0],
            [5.0, 5.0],
        ],
        dtype=np.float64,
    )

    try:
        warped = aligner._warp_with_path(seq, warp_path, target_length=6)  # type: ignore[reportPrivateUsage]
    except (ValueError, IndexError) as e:
        raise AssertionError(
            f"BUG: MotionDTWAligner._warp_with_path raised {type(e).__name__}: "
            f"{e} for a multi-mapping ref frame with a NaN user-index. "
            f"`user_indices.astype(int)` with NaN truncates to a huge negative "
            f"int (line 433) → `sequence[<huge-negative>]` → `IndexError`. "
            f"The #1097 fix: `valid = user_indices[np.isfinite(user_indices)]` "
            f"BEFORE the int cast."
        ) from e

    assert warped.shape == (6, 17, 2)
    assert np.all(np.isfinite(warped)), (
        "BUG: _warp_with_path returned non-finite values; expected all-finite."
    )


# --------------------------------------------------------------------------- #
# Observable 3: _warp_sequence (aligner.py) must NOT crash on NaN entry.
# --------------------------------------------------------------------------- #


def test_warp_sequence_nan_entry_does_not_crash_repro():
    """CORRECT behavior: a NaN in `index1` (the user-index column) for
    `MotionAligner._warp_sequence` must NOT raise `ValueError: cannot
    convert float NaN to integer` at `int(user_indices[0])` (line 293).
    Must return a finite warped sequence.

    RED now: NaN in `index1` → `int(NaN)` → `ValueError` at line 293. After
    the fix: `np.isfinite` mask before the int cast.
    """
    aligner = MotionAligner()
    seq = _seq(6)
    index1 = np.array([np.nan, 0.0, 1.0, 2.0, 3.0, 4.0], dtype=np.float64)
    index2 = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)

    try:
        warped = aligner._warp_sequence(seq, index1, index2)  # type: ignore[reportPrivateUsage]
    except (ValueError, IndexError) as e:
        raise AssertionError(
            f"BUG: MotionAligner._warp_sequence raised {type(e).__name__}: "
            f"{e} for `index1` with a NaN entry. `int(NaN) = ValueError` at "
            f"line 293 (`sequence[int(user_indices[0])]`) and "
            f"`user_indices.astype(int)` of NaN → IndexError at line 296. "
            f"The #1097 fix: `valid = user_indices[np.isfinite(user_indices)]` "
            f"BEFORE the int cast in `_warp_sequence`."
        ) from e

    assert np.all(np.isfinite(warped)), (
        "BUG: _warp_sequence returned non-finite values for NaN-index1 input; "
        "expected all-finite (NaN-masked warped sequence)."
    )


# --------------------------------------------------------------------------- #
# Regression: valid finite warp_path / index1 must still produce a finite
# warped sequence (the fix must not change the no-NaN case).
# --------------------------------------------------------------------------- #


def test_warp_with_path_all_finite_regression():
    """Regression guard: an all-finite warp_path must still produce a finite
    warped sequence. The fix (`np.isfinite` mask) must be a no-op on all-finite
    input — it filters nothing, the existing branch runs unchanged.
    """
    aligner = MotionDTWAligner(window_type="sakoechiba", window_size=0.2)
    seq = _seq(6)
    warp_path = np.array([[i, i] for i in range(6)], dtype=np.float64)
    warped = aligner._warp_with_path(seq, warp_path, target_length=6)  # type: ignore[reportPrivateUsage]
    assert warped.shape == (6, 17, 2)
    assert np.all(np.isfinite(warped)), (
        "REGRESSION: all-finite warp_path produced non-finite warped sequence; "
        "the #1097 fix must be a no-op on the no-NaN case."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — the #1097 NaN-warp guard lives in the
# shared warp function bodies. Confirms `np.isfinite` is applied to
# `user_indices` BEFORE the int cast.
# --------------------------------------------------------------------------- #


def test_motion_dtw_nan_warp_source_repro():
    """Source check: the #1097 fix lives in `_warp_with_path` (the shared
    warp function in motion_dtw.py) and `_warp_sequence` (the shared warp
    function in aligner.py). Both must apply `np.isfinite` to `user_indices`
    BEFORE the int cast. A guard only at the call site (caller-side) is the
    wrong layer — every caller would have to be patched; the guard in the
    shared function fixes all callers at once.

    GREEN contract:
      - `_warp_with_path` source contains `np.isfinite` (the NaN-warp guard).
      - `_warp_sequence` source contains `np.isfinite` (the NaN-warp guard).
    """
    warp_dtw_src = inspect.getsource(MotionDTWAligner._warp_with_path)  # type: ignore[reportPrivateUsage]
    assert "np.isfinite" in warp_dtw_src, (
        "BUG: MotionDTWAligner._warp_with_path must apply `np.isfinite` to "
        "`user_indices` BEFORE the int cast (the #1097 NaN-warp guard). "
        "`int(NaN)` raises ValueError; the guard filters NaN out (or falls "
        "back to nearest-neighbor if all are NaN). The guard lives in the "
        "shared warp function — one fix, not N."
    )

    warp_aligner_src = inspect.getsource(MotionAligner._warp_sequence)  # type: ignore[reportPrivateUsage]
    assert "np.isfinite" in warp_aligner_src, (
        "BUG: MotionAligner._warp_sequence must apply `np.isfinite` to "
        "`user_indices` BEFORE the int cast (the #1097 NaN-warp guard). "
        "`int(NaN)` raises ValueError; the guard filters NaN out. The guard "
        "lives in the shared warp function — one fix, not N."
    )
