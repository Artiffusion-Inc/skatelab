"""GREEN contract — `ElementSegmenter._detect_stillness` and
`ElementSegmenter.segment` (ml/src/analysis/element_segmenter.py)
must NOT crash with an uncaught `ValueError: cannot convert float
NaN to integer` when fed NaN fps / NaN config.

Root cause (now fixed by #1109):
    `int(self._min_still_duration * fps)` and
    `int(self._min_segment_duration * video_meta.fps)` are now
    guarded by `math.isfinite(...) and ... > 0` typed errors
    mirroring the PR #1063 pattern. The uncaught `int(NaN)` crash
    is replaced with a named ValueError naming the bad parameter,
    so the worker surfaces a clear failure instead of an opaque
    math exception.

Siblings:
- PR #1063 (tranche #505 fps guard for `_extract_segment_features`
  silent-zero-coerce): same root cause family (no `math.isfinite`
  guard), different bug class (silent 0 vs crash), different
  function. Not affected by this fix.
- PR #1094 (tranche #1031 _extract_segments label-NaN int crash):
  different file (tas/segmentation), same family. Not affected.

Methodology (per audit reglement):
  3 observables  (NaN fps to _detect_stillness, NaN fps to segment,
                 NaN via _min_still_duration config)
  1 regression   (valid fps → sane stillness mask)
  1 source check (root cause locked via inspect.getsource)
"""

from __future__ import annotations

import inspect

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter

# =========================================================================== #
# Observable 1: NaN fps to `_detect_stillness` — typed error, not int(NaN).
# =========================================================================== #


def test_element_segmenter_detect_stillness_nan_fps_silent_crash_repro():
    """GREEN contract: NaN fps must raise a typed, named ValueError
    at the trust boundary — not a raw `int(NaN)` ValueError from
    the math.

    Mirrors PR #1063 / #1043 fps guard pattern in
    `_extract_segment_features`.
    """
    seg = ElementSegmenter()
    motion_energy = np.zeros(10, dtype=np.float32)
    try:
        seg._detect_stillness(motion_energy, fps=float("nan"))
    except ValueError as ex:
        # No raw int(NaN) leak.
        assert "cannot convert float NaN to integer" not in str(ex), (
            f"BUG: raw int(NaN) leak — got ValueError: {ex}"
        )
        # Typed error naming the bad parameter.
        assert "fps" in str(ex), f"BUG: expected typed fps error, got ValueError: {ex}"
        return  # GREEN: typed error raised
    raise AssertionError(
        "BUG: _detect_stillness with NaN fps did not raise. The math.isfinite guard is missing."
    )


# =========================================================================== #
# Observable 2: NaN `video_meta.fps` to `segment` — typed error.
# =========================================================================== #


def test_element_segmenter_segment_nan_fps_silent_crash_repro():
    """GREEN contract: NaN `video_meta.fps` must raise a typed,
    named ValueError at the trust boundary — not a raw `int(NaN)`
    ValueError from the math.
    """
    from pathlib import Path

    from src.types import VideoMeta

    seg = ElementSegmenter()
    poses = np.random.RandomState(42).rand(30, 17, 2).astype(np.float32)
    meta = VideoMeta(
        path=Path("dummy.mp4"),
        width=1920,
        height=1080,
        fps=float("nan"),
        num_frames=30,
    )
    try:
        seg.segment(poses, Path("dummy.mp4"), meta)
    except ValueError as ex:
        assert "cannot convert float NaN to integer" not in str(ex), (
            f"BUG: raw int(NaN) leak — got ValueError: {ex}"
        )
        assert "fps" in str(ex), f"BUG: expected typed fps error, got ValueError: {ex}"
        return  # GREEN: typed error raised
    raise AssertionError(
        "BUG: segment with NaN video_meta.fps did not raise. The math.isfinite guard is missing."
    )


# =========================================================================== #
# Observable 3: NaN `_min_still_duration` config — typed error.
# =========================================================================== #


def test_element_segmenter_detect_stillness_nan_min_still_crash_repro():
    """GREEN contract: NaN `_min_still_duration` config must raise a
    typed, named ValueError at the trust boundary — not a raw
    `int(NaN)` ValueError from the math.
    """
    seg = ElementSegmenter(min_still_duration=float("nan"))
    motion_energy = np.zeros(10, dtype=np.float32)
    try:
        seg._detect_stillness(motion_energy, fps=30.0)
    except ValueError as ex:
        assert "cannot convert float NaN to integer" not in str(ex), (
            f"BUG: raw int(NaN) leak — got ValueError: {ex}"
        )
        assert "min_still_duration" in str(ex), (
            f"BUG: expected typed min_still_duration error, got ValueError: {ex}"
        )
        return  # GREEN: typed error raised
    raise AssertionError(
        "BUG: _detect_stillness with NaN min_still_duration did not raise. "
        "The math.isfinite guard is missing."
    )


# =========================================================================== #
# Regression guard: valid fps + valid _min_still_duration must produce
# a sane stillness mask. The fix (NaN guard) must not change the
# typical case.
# =========================================================================== #


def test_element_segmenter_detect_stillness_valid_unchanged_repro():
    """Regression guard: valid fps + valid _min_still_duration
    must produce a sane stillness mask. The fix (NaN guard) must
    not change the typical case.
    """
    seg = ElementSegmenter()
    motion_energy = np.zeros(10, dtype=np.float32)
    # Should not raise.
    result = seg._detect_stillness(motion_energy, fps=30.0)
    assert result.shape == (10,), (
        f"BUG (regression): _detect_stillness returned shape {result.shape}, expected (10,)."
    )
    assert result.dtype == np.bool_, (
        f"BUG (regression): _detect_stillness returned dtype {result.dtype}, expected bool_."
    )


# =========================================================================== #
# Source check: the `math.isfinite` guard IS present at both conversion
# sites (the fix is locked in).
# =========================================================================== #


def test_element_segmenter_unguarded_nan_int_source_repro():
    """Source check: the `math.isfinite` guard IS present at both
    conversion sites (the fix is locked in). The unguarded
    `int(self._min_still_duration * fps)` and
    `int(self._min_segment_duration * video_meta.fps)` casts have
    been moved behind a typed-error guard.

    GREEN now: the guard is present (PASS). If the guard is ever
    removed, this test FAILS, signaling the int(NaN) crash
    regression is back.
    """
    src_detect = inspect.getsource(ElementSegmenter._detect_stillness)
    assert "isfinite(fps)" in src_detect, (
        "BUG: `math.isfinite(fps)` guard missing in _detect_stillness — "
        "the int(NaN) crash regression is back."
    )

    src_segment = inspect.getsource(ElementSegmenter.segment)
    assert "isfinite(video_meta.fps)" in src_segment, (
        "BUG: `math.isfinite(video_meta.fps)` guard missing in segment — "
        "the int(NaN) crash regression is back."
    )
