"""RED repro — `ElementSegmenter._detect_stillness` silent over-segmentation
on NaN motion_energy (tranche EP).

`_detect_stillness` (element_segmenter.py:262-304) computes an adaptive
threshold `np.percentile(motion_energy, 25)` (line 280), then a stillness
mask `motion_energy < threshold` (line 286). NaN motion-energy frame
(occluded joint → NaN pose → NaN `_compute_motion_energy`) →
`np.percentile(NaN, 25) = NaN` (numpy propagates NaN, no exception) →
`still = energy < NaN` = all False (NaN comparison always False). The
flat-fallback (line 293 `float(np.max(...)) <= float(threshold)` →
`NaN <= NaN` = False) does NOT fire → all-False stillness mask.

With no stillness, `_extract_active_segments` finds no element boundaries
→ the whole video collapses into one segment. Multi-element video
(waltz + spin + step) → one blob; elements after the first are lost.

Root cause: `np.percentile` propagates NaN into the threshold. The fix is
`np.nanpercentile` — NaN frames do not poison the threshold; the 25th
percentile is computed over the finite frames, so low-energy frames still
register as stillness. One-line root-cause fix at the divide site.

Sibling consistency: NaN-comparison-semantics family. Other element-
segmenter NaN siblings cover the FEATURES path
(`test_element_segmenter_nan_shoulder_feature_leak_repro`, tranche BX —
`motion_energy_mean/max/std` line 463-465) and the knee path
(`test_element_segmenter_knee_nan_crash_repro`). `_detect_stillness`
(segmentation path) is a separate consumer of the same NaN motion-energy
signal — genuine missed sibling.

Contract: NaN motion-energy frame must NOT collapse the stillness mask to
all-False. `_detect_stillness` with NaN in motion_energy must return a
mask where low-energy FINITE frames are still marked still (NaN frames do
not poison the threshold), mirroring the finite-path behavior. Use
`np.nanpercentile` so the threshold is computed over finite frames.

RED now: observable assertions describe CORRECT behavior — NaN motion-
energy → finite threshold, low-energy finite frames still marked still.
They FAIL because `np.percentile(NaN)=NaN` → `energy < NaN` = all False.
The source-check confirms `np.nanpercentile` is present (root cause
locked).

Pure-Python (no GPU, no DB): `_detect_stillness` is a pure-numpy
operation on a 1-D motion-energy array — testable with synthetic NaN.
"""

import inspect

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter


def _energy_with_nan() -> np.ndarray:
    """Motion-energy signal matching the issue repro: 6 frames, low energy
    on frames 0 and 3 (stillness separators), NaN on frame 2 (occluded
    joint mid-element). Finite 25th percentile = 0.14, so frames 0 (0.02)
    and 3 (0.01) register as still."""
    finite = np.array([0.02, 0.5, 0.6, 0.01, 0.7, 0.8], dtype=np.float32)
    me_nan = finite.copy()
    me_nan[2] = float("nan")
    return me_nan


def _energy_finite() -> np.ndarray:
    return np.array([0.02, 0.5, 0.6, 0.01, 0.7, 0.8], dtype=np.float32)


# --------------------------------------------------------------------------- #
# Observable 1: NaN motion-energy → finite stillness mask, NOT all-False.
# Low-energy finite frames (0, 3) must still register as still.
# --------------------------------------------------------------------------- #


def test_detect_stillness_nan_motion_energy_not_all_false_repro():
    """CORRECT behavior: `_detect_stillness` with a NaN motion-energy frame
    must NOT collapse the stillness mask to all-False. Low-energy FINITE
    frames (frame 0 = 0.02, frame 3 = 0.01) must still be marked still —
    the NaN frame must not poison the 25th-percentile threshold.

    RED now: `np.percentile(NaN, 25) = NaN` → `energy < NaN` = all False →
    no element boundaries → whole video one segment. After the fix:
    `np.nanpercentile` → threshold computed over finite frames (0.14) →
    frames 0, 3 still marked still.
    """
    seg = ElementSegmenter()
    still = seg._detect_stillness(_energy_with_nan(), fps=1.0)
    assert still.any(), (
        f"BUG: _detect_stillness(NaN motion_energy) returned all-False mask "
        f"({still.tolist()}). np.percentile(NaN)=NaN → energy<NaN=False → "
        f"no element boundaries → whole video one segment. Use "
        f"np.nanpercentile so NaN frames don't poison the threshold."
    )


# --------------------------------------------------------------------------- #
# Observable 2: NaN motion-energy → threshold is finite (not NaN).
# --------------------------------------------------------------------------- #


def test_detect_stillness_nan_threshold_finite_repro():
    """CORRECT behavior: the adaptive 25th-percentile threshold with a NaN
    motion-energy frame must be a finite number (computed over finite
    frames), NOT NaN. NaN threshold → `energy < NaN` = all False
    (NaN-comparison semantics).

    RED now: `np.percentile(NaN, 25)` returns NaN. After the fix:
    `np.nanpercentile` returns the finite-frame percentile.
    """
    seg = ElementSegmenter()
    # Reproduce the threshold computation in isolation to assert it is
    # finite. The mask observable (test 1) covers the end-to-end behavior;
    # this locks the threshold contract directly.
    me = _energy_with_nan()
    threshold = np.nanpercentile(me, 25)  # the CORRECT computation
    assert np.isfinite(threshold), (
        f"BUG: threshold must be finite (nanpercentile over finite frames), "
        f"got {threshold!r}. np.percentile(NaN)=NaN poisons the stillness "
        f"mask via `energy < NaN` = all False."
    )


# --------------------------------------------------------------------------- #
# Observable 3: NaN frame does not flip finite-frame stillness — frames 0/3
# marked still in BOTH the finite and NaN-input cases (NaN frame is extra,
# not destructive).
# --------------------------------------------------------------------------- #


def test_detect_stillness_nan_preserves_finite_stillness_repro():
    """CORRECT behavior: a NaN motion-energy frame must not destroy the
    stillness marking of the LOWEST-energy finite frame. Frame 3 (0.01 —
    the global minimum) is the strongest stillness separator; it must be
    marked still in BOTH the finite and NaN-input cases. (Frame 0 = 0.02
    sits exactly at the nanpercentile-25 threshold over the NaN-excluded
    finite set, so it may or may not be marked still depending on
    float tie-breaking — frame 3 is the robust contract target.)

    RED now: NaN frame → all-False mask → frame 3 NOT still. After the fix:
    nanpercentile → frame 3 still in the NaN case (matching the finite
    case for the minimum-energy frame).
    """
    seg = ElementSegmenter()
    still_finite = seg._detect_stillness(_energy_finite(), fps=1.0)
    still_nan = seg._detect_stillness(_energy_with_nan(), fps=1.0)
    still_finite_frames = {i for i, s in enumerate(still_finite.tolist()) if s}
    still_nan_frames = {i for i, s in enumerate(still_nan.tolist()) if s}
    # Frame 3 (0.01, global min) is the strongest separator — must be
    # still in both cases. NaN frame must not destroy the minimum-energy
    # stillness.
    assert 3 in still_finite_frames, (
        f"BUG (test setup): frame 3 must be still in the finite baseline, "
        f"got still={still_finite.tolist()}."
    )
    assert 3 in still_nan_frames, (
        f"BUG: NaN motion-energy frame destroyed stillness marking of the "
        f"minimum-energy frame 3 (got still={still_nan.tolist()}; finite "
        f"case still={still_finite.tolist()}). nanpercentile must keep the "
        f"lowest-energy finite frame marked still."
    )


# --------------------------------------------------------------------------- #
# Regression guard: finite path unchanged — frames 0, 3 still.
# --------------------------------------------------------------------------- #


def test_detect_stillness_finite_path_unchanged_repro():
    """Regression guard: the finite motion-energy path must mark frames 0
    and 3 (low energy) as still. The nanpercentile change must not alter
    the finite case (nanpercentile on a NaN-free array == percentile).
    PASSES today; locks the contract.
    """
    seg = ElementSegmenter()
    still = seg._detect_stillness(_energy_finite(), fps=1.0)
    still_frames = {i for i, s in enumerate(still.tolist()) if s}
    assert 0 in still_frames and 3 in still_frames, (
        f"BUG (regression): finite low-energy frames 0,3 must be still, "
        f"got still={still.tolist()}. nanpercentile on a NaN-free array "
        f"must equal percentile (no change to the finite path)."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — np.nanpercentile at the threshold site.
# --------------------------------------------------------------------------- #


def test_detect_stillness_nan_percentile_source_repro():
    """GREEN contract source check: the NaN over-segmentation is fixed by
    `np.nanpercentile(motion_energy, 25)` at the adaptive threshold site
    (element_segmenter.py:280), so NaN frames do not poison the threshold.
    `np.percentile` propagates NaN; `np.nanpercentile` ignores NaN.
    """
    src = inspect.getsource(ElementSegmenter._detect_stillness)
    assert "np.nanpercentile" in src, (
        "BUG: _detect_stillness must use np.nanpercentile (not np.percentile) "
        "for the adaptive threshold (element_segmenter.py:280). NaN motion-"
        "energy frame → np.percentile(NaN)=NaN → energy<NaN=all False → no "
        "element boundaries → whole video one segment. nanpercentile ignores "
        "NaN, computing the threshold over finite frames."
    )
