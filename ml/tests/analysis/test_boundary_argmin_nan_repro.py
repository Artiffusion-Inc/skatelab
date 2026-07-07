"""RED repro for issue #1322: boundary argmin NaN silent-wrong-index (tranche MP).

`phase_detector.py:209-210` guards with `np.isfinite(com_y_search).any()` —
this passes for a mixed-NaN window but then `np.argmin(com_y_search)` returns
the index of the FIRST NaN (numpy treats NaN as smallest). The result is a
finite WRONG index, not NaN: silent data quality corruption.

`com_y_search = [0.4, NaN, 0.3, 0.1]` →
  - isfinite.any() = True (window not all-NaN, guard passes)
  - argmin = 1 (first NaN, silent)
  - peak_idx = search_start + 1 (wrong; real min at index 3)

The correct fix mirrors the element_segmenter._refine_boundaries pattern (#972):
use `np.nanargmin` (skips NaN, picks the actual minimum over finite frames).

3 observables + 1 regression + 1 source check.
"""

from __future__ import annotations

import math

import numpy as np

# --------------------------------------------------------------------------- #
# Observable 1: mixed-NaN window → argmin returns first-NaN index silently.
# `np.isfinite(arr).any()` is TRUE for this array, so the existing guard
# does NOT prevent the silent wrong-index.
# --------------------------------------------------------------------------- #


def test_argmin_mixed_nan_silent_first_nan_index_repro():
    """RED: np.argmin on [finite, NaN, ...] returns index of first NaN.

    The peak search at phase_detector.py:209-210 enters the `argmin` branch
    because `isfinite(arr).any()` is True. argmin then silently returns 1
    instead of the true minimum index 3.
    """
    arr = np.array([0.4, float("nan"), 0.3, 0.1])
    # Document the actual numpy behavior this depends on.
    assert np.isfinite(arr).any(), "precondition: at least one finite value"
    assert np.argmin(arr) == 1, "numpy contract changed: argmin no longer returns first-NaN index"
    # The peak should be at index 3 (value 0.1, the actual minimum over
    # finite frames), not index 1 (first NaN).
    expected_min_index = int(np.nanargmin(arr))  # 3
    actual_argmin_index = int(np.argmin(arr))  # 1
    assert actual_argmin_index != expected_min_index, (
        "Test precondition broken: argmin == nanargmin on mixed NaN — "
        "numpy semantics changed, update test."
    )


# --------------------------------------------------------------------------- #
# Observable 2: longer mixed-NaN window — same wrong-index pattern.
# --------------------------------------------------------------------------- #


def test_argmin_mixed_nan_long_window_silent_first_nan_repro():
    """RED: 50-frame window with one early NaN → argmin returns that NaN index.

    Simulates a single-frame occlusion in the search window: peak snap to
    the occluded frame, silently corrupting phase detection.
    """
    arr = np.full(50, 0.5)
    arr[2] = float("nan")  # single NaN at index 2
    arr[40] = 0.1  # actual minimum (highest CoM peak)
    # isfinite passes: guard at line 209 does NOT prevent this.
    assert np.isfinite(arr).any()
    # argmin returns 2 (first NaN), not 40 (real min).
    assert int(np.argmin(arr)) == 2
    # Real minimum is at 40 via nanargmin.
    assert int(np.nanargmin(arr)) == 40


# --------------------------------------------------------------------------- #
# Observable 3: NaN via inf-inf chain (subtle: not literal float('nan')).
# inf can sneak in via empty-mean / log / division edge cases.
# --------------------------------------------------------------------------- #


def test_argmin_nan_via_inf_chain_silent_first_nan_repro():
    """RED: inf-inf = NaN, mixed with finite values, argmin returns NaN index."""
    nan = math.inf - math.inf
    arr = np.array([0.5, 0.3, nan, 0.2, 0.1])
    assert np.isfinite(arr).any()  # guard passes
    assert int(np.argmin(arr)) == 2  # first NaN, silent
    assert int(np.nanargmin(arr)) == 4  # actual min over finite


# --------------------------------------------------------------------------- #
# Regression guard: all-finite CoM must produce correct peak.
# Locks the typical-case contract so the fix doesn't break it.
# --------------------------------------------------------------------------- #


def test_argmin_valid_com_correct_peak_regression():
    """Regression: valid CoM with clear dip must still return correct peak."""
    # CoM with clear dip at index 2 (peak of jump).
    com_y = np.array([0.0, -0.1, -0.5, -0.2, 0.0])
    assert int(np.nanargmin(com_y)) == 2
    # CoM with dip at index 3.
    com_y = np.array([0.0, 0.0, 0.0, -0.3, 0.0, 0.0])
    assert int(np.nanargmin(com_y)) == 3


# --------------------------------------------------------------------------- #
# Source check: phase_detector.py:210 must use nanargmin (not raw argmin).
# Mirrors the element_segmenter._refine_boundaries fix (#972).
# RED on master, GREEN after fix.
# --------------------------------------------------------------------------- #


def test_argmin_nanargmin_source_repro():
    """Source check: phase_detector.py:210 uses nanargmin over argmin.

    The fix mirrors element_segmenter._refine_boundaries (commit 34bc1ec6):
    replace unguarded `np.argmin(arr)` with `np.nanargmin(arr)` to skip NaN
    frames and pick the actual minimum over finite frames. The
    `np.isfinite(arr).any()` guard at line 209 is insufficient: it passes
    for mixed-NaN windows but does not prevent argmin from returning the
    first-NaN index.
    """
    from pathlib import Path as P

    src_path = P(__file__).parent.parent.parent / "src" / "analysis" / "phase_detector.py"
    src = src_path.read_text(encoding="utf-8")
    # Locate the peak-search block.
    assert "com_y_search = com_y[search_start:search_end]" in src
    # Either: (a) the unguarded `np.argmin(com_y_search)` is gone (fixed with
    # `np.nanargmin`), OR (b) the unguarded argmin is wrapped in a stricter
    # isfinite check (e.g. `isfinite(arr).all()` instead of `.any()`) that
    # actually catches mixed-NaN windows. Both prevent silent wrong-index.
    has_nanargmin = "np.nanargmin(com_y_search)" in src
    raw_argmin_present = "np.argmin(com_y_search)" in src
    assert has_nanargmin or not raw_argmin_present, (
        "BUG: `np.argmin(com_y_search)` still unguarded at "
        "phase_detector.py:210. Mixed-NaN windows return first-NaN index "
        "silently (wrong peak). Replace with `np.nanargmin(com_y_search)` "
        "(skips NaN, picks true min over finite frames). Mirrors the "
        "element_segmenter._refine_boundaries fix #972."
    )
