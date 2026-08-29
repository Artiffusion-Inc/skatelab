"""RED repro — `_segment_with_tas` / `_segment_with_tas_v2` NaN propagation
(ml/src/analysis/element_segmenter.py:193, :251).

Bug: `float(np.mean([s.confidence for s in element_segs]))` silently
returns NaN if any element_seg confidence is NaN. The `if element_segs else
0.0` guard only catches empty lists — non-empty lists with NaN confidences
still pass through. When BiGRU coarse output is NaN, or RF fine output
NaN, or upstream MI/MH/HI family NaN-propagates, the mean returns NaN
and `SegmentationResult.confidence = NaN` — user sees
"segmentation confidence: nan" with no diagnostic.

Source: ml/src/analysis/element_segmenter.py:193 (tas_ml) and :251 (tas_ml_v2).

Consumer chain (per issue #1316):
  SegmentationResult.confidence = NaN → user sees
  "segmentation confidence: nan" → silent unreliable segmentation
  (the element detection may be wrong, the biomechanics report is based
  on wrong segments).

Sibling fix exists at :670-680 (`_compute_overall_confidence`), which
filters via `math.isfinite` — the same pattern is missing at :193 and :251.

Methodology (per audit reglement):
  3 observables  (one-NaN, all-NaN, mixed-NaN for each of the two sites)
  1 regression   (all-finite → expected mean, NaN-free)
  1 source check (unguarded pattern locked at the two sites)
"""

from __future__ import annotations

import inspect
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter
from src.types import ElementSegment, SegmentationResult
from src.utils.video import VideoMeta

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _video_meta() -> VideoMeta:
    """Standard video metadata for tests."""
    return VideoMeta(
        path=Path("test.mp4"),
        width=640,
        height=480,
        fps=30.0,
        num_frames=90,
    )


def _seg(confidence: float, idx: int = 0) -> ElementSegment:
    """Helper: build an ElementSegment with given confidence."""
    return ElementSegment(
        element_type="waltz_jump",
        start=idx * 30,
        end=idx * 30 + 29,
        confidence=confidence,
    )


# =========================================================================== #
# Site 1: _segment_with_tas (line 193)
# =========================================================================== #


def test_segment_with_tas_one_nan_does_not_silently_propagate_repro():
    """RED contract: a single NaN segment confidence in `_segment_with_tas`
    must NOT silently propagate to `SegmentationResult.confidence`.

    Pre-fix: `np.mean([0.9, NaN, 0.8])` = NaN → `float(NaN)` = NaN is
    written to `SegmentationResult.confidence`.
    """
    seg = ElementSegmenter()
    poses = np.random.rand(30, 17, 2).astype(np.float32)

    mock_tas = MagicMock()
    mock_tas.segment.return_value = [
        {"element_type": "flip", "start": 0, "end": 10, "confidence": 0.9},
        {"element_type": "waltz_jump", "start": 11, "end": 20, "confidence": float("nan")},
        {"element_type": "toe_loop", "start": 21, "end": 30, "confidence": 0.8},
    ]

    result = seg._segment_with_tas(mock_tas, poses, Path("test.mp4"), _video_meta())
    assert isinstance(result, SegmentationResult)
    assert not (isinstance(result.confidence, float) and math.isnan(result.confidence)), (
        f"BUG: _segment_with_tas returned NaN confidence from a NaN-bearing "
        f"TAS output. Got {result.confidence!r}."
    )


def test_segment_with_tas_all_nan_does_not_silently_propagate_repro():
    """RED contract: ALL-NaN confidences in TAS output must NOT return NaN.

    Pre-fix: `np.mean([NaN, NaN, NaN])` = NaN. Post-fix should treat
    no-finite-signal as 0.0 (or a typed error), not silent NaN.
    """
    seg = ElementSegmenter()
    poses = np.random.rand(30, 17, 2).astype(np.float32)

    mock_tas = MagicMock()
    mock_tas.segment.return_value = [
        {"element_type": "flip", "start": 0, "end": 10, "confidence": float("nan")},
        {"element_type": "waltz_jump", "start": 11, "end": 20, "confidence": float("nan")},
        {"element_type": "toe_loop", "start": 21, "end": 30, "confidence": float("nan")},
    ]

    result = seg._segment_with_tas(mock_tas, poses, Path("test.mp4"), _video_meta())
    assert not (isinstance(result.confidence, float) and math.isnan(result.confidence)), (
        f"BUG: _segment_with_tas returned NaN confidence for all-NaN TAS output. "
        f"Got {result.confidence!r}."
    )


def test_segment_with_tas_mixed_nan_finite_ignores_nan_repro():
    """RED contract: with mixed NaN/finite TAS confidences, the NaN entries
    must be ignored, not poison the mean. With [0.5, NaN, 0.9] the post-fix
    result should equal 0.7 (mean of 0.5 and 0.9), NOT NaN.
    """
    seg = ElementSegmenter()
    poses = np.random.rand(30, 17, 2).astype(np.float32)

    mock_tas = MagicMock()
    mock_tas.segment.return_value = [
        {"element_type": "flip", "start": 0, "end": 10, "confidence": 0.5},
        {"element_type": "waltz_jump", "start": 11, "end": 20, "confidence": float("nan")},
        {"element_type": "toe_loop", "start": 21, "end": 30, "confidence": 0.9},
    ]

    result = seg._segment_with_tas(mock_tas, poses, Path("test.mp4"), _video_meta())
    assert not (isinstance(result.confidence, float) and math.isnan(result.confidence)), (
        f"BUG: _segment_with_tas returned NaN confidence for mixed TAS output. "
        f"Got {result.confidence!r}."
    )
    assert math.isclose(result.confidence, 0.7, abs_tol=1e-9), (
        f"BUG: expected NaN entries to be ignored → mean of [0.5, 0.9] = 0.7, "
        f"got {result.confidence!r}."
    )


# =========================================================================== #
# Site 2: _segment_with_tas_v2 (line 251)
# =========================================================================== #


def test_segment_with_tas_v2_one_nan_does_not_silently_propagate_repro():
    """RED contract: a single NaN segment confidence in `_segment_with_tas_v2`
    must NOT silently propagate to `SegmentationResult.confidence`.

    Same NaN-propagate pattern as site 1, in the v2 BiGRU+Skeleton1DCNN path.
    """
    seg = ElementSegmenter()
    poses = np.random.rand(60, 17, 2).astype(np.float32)

    mock_tas = MagicMock()
    mock_tas.segment.return_value = [
        {"element_type": "Jump", "start": 0, "end": 20, "confidence": 0.85},
        {"element_type": "Spin", "start": 21, "end": 40, "confidence": float("nan")},
        {"element_type": "Step", "start": 41, "end": 60, "confidence": 0.7},
    ]

    with patch.object(seg, "_get_tas_segmenter", return_value=mock_tas):
        result = seg._segment_with_tas_v2(poses, fps=30.0, video_meta=_video_meta())
    assert isinstance(result, SegmentationResult)
    assert not (isinstance(result.confidence, float) and math.isnan(result.confidence)), (
        f"BUG: _segment_with_tas_v2 returned NaN confidence from a NaN-bearing "
        f"TAS output. Got {result.confidence!r}."
    )


def test_segment_with_tas_v2_all_nan_does_not_silently_propagate_repro():
    """RED contract: ALL-NaN confidences in v2 TAS output must NOT return NaN."""
    seg = ElementSegmenter()
    poses = np.random.rand(60, 17, 2).astype(np.float32)

    mock_tas = MagicMock()
    mock_tas.segment.return_value = [
        {"element_type": "Jump", "start": 0, "end": 20, "confidence": float("nan")},
        {"element_type": "Spin", "start": 21, "end": 40, "confidence": float("nan")},
        {"element_type": "Step", "start": 41, "end": 60, "confidence": float("nan")},
    ]

    with patch.object(seg, "_get_tas_segmenter", return_value=mock_tas):
        result = seg._segment_with_tas_v2(poses, fps=30.0, video_meta=_video_meta())
    assert not (isinstance(result.confidence, float) and math.isnan(result.confidence)), (
        f"BUG: _segment_with_tas_v2 returned NaN confidence for all-NaN TAS output. "
        f"Got {result.confidence!r}."
    )


def test_segment_with_tas_v2_mixed_nan_finite_ignores_nan_repro():
    """RED contract: with mixed NaN/finite v2 TAS confidences, the NaN entries
    must be ignored. With [0.4, NaN, 0.6] the post-fix result should equal
    0.5 (mean of 0.4 and 0.6), NOT NaN.
    """
    seg = ElementSegmenter()
    poses = np.random.rand(60, 17, 2).astype(np.float32)

    mock_tas = MagicMock()
    mock_tas.segment.return_value = [
        {"element_type": "Jump", "start": 0, "end": 20, "confidence": 0.4},
        {"element_type": "Spin", "start": 21, "end": 40, "confidence": float("nan")},
        {"element_type": "Step", "start": 41, "end": 60, "confidence": 0.6},
    ]

    with patch.object(seg, "_get_tas_segmenter", return_value=mock_tas):
        result = seg._segment_with_tas_v2(poses, fps=30.0, video_meta=_video_meta())
    assert not (isinstance(result.confidence, float) and math.isnan(result.confidence)), (
        f"BUG: _segment_with_tas_v2 returned NaN confidence for mixed TAS output. "
        f"Got {result.confidence!r}."
    )
    assert math.isclose(result.confidence, 0.5, abs_tol=1e-9), (
        f"BUG: expected NaN entries to be ignored → mean of [0.4, 0.6] = 0.5, "
        f"got {result.confidence!r}."
    )


# =========================================================================== #
# Regression: all-finite input must produce the arithmetic mean unchanged.
# =========================================================================== #


def test_segment_with_tas_all_finite_unchanged_regression_repro():
    """Regression: with all-finite TAS confidences, the result must be the
    arithmetic mean. The fix (NaN guard) must not change the happy path.
    """
    seg = ElementSegmenter()
    poses = np.random.rand(30, 17, 2).astype(np.float32)

    mock_tas = MagicMock()
    mock_tas.segment.return_value = [
        {"element_type": "flip", "start": 0, "end": 10, "confidence": 0.2},
        {"element_type": "waltz_jump", "start": 11, "end": 20, "confidence": 0.4},
        {"element_type": "toe_loop", "start": 21, "end": 30, "confidence": 0.6},
        {"element_type": "three_turn", "start": 31, "end": 45, "confidence": 0.8},
    ]

    result = seg._segment_with_tas(mock_tas, poses, Path("test.mp4"), _video_meta())
    assert math.isclose(result.confidence, 0.5, abs_tol=1e-9), (
        f"BUG (regression): expected mean of [0.2, 0.4, 0.6, 0.8] = 0.5, got {result.confidence!r}."
    )


def test_segment_with_tas_v2_all_finite_unchanged_regression_repro():
    """Regression: with all-finite v2 TAS confidences, the result must be
    the arithmetic mean. The fix (NaN guard) must not change the happy path.
    """
    seg = ElementSegmenter()
    poses = np.random.rand(60, 17, 2).astype(np.float32)

    mock_tas = MagicMock()
    mock_tas.segment.return_value = [
        {"element_type": "Jump", "start": 0, "end": 20, "confidence": 0.3},
        {"element_type": "Spin", "start": 21, "end": 40, "confidence": 0.5},
        {"element_type": "Step", "start": 41, "end": 60, "confidence": 0.7},
    ]

    with patch.object(seg, "_get_tas_segmenter", return_value=mock_tas):
        result = seg._segment_with_tas_v2(poses, fps=30.0, video_meta=_video_meta())
    assert math.isclose(result.confidence, 0.5, abs_tol=1e-9), (
        f"BUG (regression): expected mean of [0.3, 0.5, 0.7] = 0.5, got {result.confidence!r}."
    )


# =========================================================================== #
# Source check: the unguarded `np.mean([s.confidence for s in element_segs])`
# pattern is gone at the two sites. If a future refactor reintroduces it,
# this test FAILS, signaling the silent-NaN regression is back.
# =========================================================================== #


def test_segment_with_tas_unguarded_np_mean_removed_repro():
    """Source check: `_segment_with_tas` must NOT contain a bare
    `np.mean([s.confidence for s in element_segs])` (unguarded).

    Acceptable guards (any one of):
      - `math.isfinite(...)` filter
      - `np.nanmean(...)`
      - explicit `if isnan: skip` loop
    """
    src = inspect.getsource(ElementSegmenter._segment_with_tas)
    has_guard = "isfinite" in src or "isnan" in src or "nanmean" in src
    has_unguarded_bug = "np.mean([s.confidence for s in element_segs])" in src and not has_guard
    assert not has_unguarded_bug, (
        "BUG: _segment_with_tas still has unguarded "
        "`np.mean([s.confidence for s in element_segs])` — silent NaN propagate.\n"
        f"Source:\n{src}"
    )


def test_segment_with_tas_v2_unguarded_np_mean_removed_repro():
    """Source check: `_segment_with_tas_v2` must NOT contain a bare
    `np.mean([s.confidence for s in segments])` (unguarded).
    """
    src = inspect.getsource(ElementSegmenter._segment_with_tas_v2)
    has_guard = "isfinite" in src or "isnan" in src or "nanmean" in src
    has_unguarded_bug = "np.mean([s.confidence for s in segments])" in src and not has_guard
    assert not has_unguarded_bug, (
        "BUG: _segment_with_tas_v2 still has unguarded "
        "`np.mean([s.confidence for s in segments])` — silent NaN propagate.\n"
        f"Source:\n{src}"
    )
