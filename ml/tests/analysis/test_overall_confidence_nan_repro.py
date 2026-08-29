"""RED repro — `_compute_overall_confidence` NaN propagation
(ml/src/analysis/element_segmenter.py:637-650).

Bug: `float(np.mean([s.confidence for s in segments]))` silently
returns NaN if any segment confidence is NaN. The numpy mean of a
list containing NaN is NaN — there is no isfinite guard at the
function's trust boundary.

Source: ml/src/analysis/element_segmenter.py:649-650.

Consumer chain (per issue #1265):
  Silent NaN → per-element score NaN → session analysis broken →
  user sees no element confidence for corrupt pose.

Sibling bug noted in #1265: LG (worker.py:468) uses the same
np.mean-NaN-propagate pattern — out of scope for this fix.

Methodology (per audit reglement):
  3 observables  (one-NaN segment, all-NaN, mixed-NaN)
  1 regression   (all-finite values → expected mean, NaN-free)
  1 source check (root cause locked via inspect.getsource)
"""

from __future__ import annotations

import inspect
import math

from src.analysis.element_segmenter import ElementSegmenter
from src.types import ElementSegment


def _seg(confidence: float, idx: int = 0) -> ElementSegment:
    """Helper: build an ElementSegment with given confidence."""
    return ElementSegment(
        element_type="waltz_jump",
        start=idx * 30,
        end=idx * 30 + 29,
        confidence=confidence,
    )


# =========================================================================== #
# Observable 1: a single NaN segment silently poisons overall confidence.
# =========================================================================== #


def test_overall_confidence_one_nan_segment_does_not_silently_propagate_repro():
    """RED contract: a single NaN segment confidence must NOT silently
    propagate to the overall confidence (return NaN).

    Pre-fix: `np.mean([0.8, NaN, 0.6])` = NaN → `float(NaN)` = NaN
    is returned, contaminating every downstream score.
    """
    seg = ElementSegmenter()
    segments = [_seg(0.8, 0), _seg(float("nan"), 1), _seg(0.6, 2)]
    result = seg._compute_overall_confidence(segments)
    assert not (isinstance(result, float) and math.isnan(result)), (
        f"BUG: _compute_overall_confidence returned NaN from a NaN-bearing "
        f"input list — silent NaN propagation. Got {result!r}."
    )


# =========================================================================== #
# Observable 2: every-NaN input must not yield NaN.
# =========================================================================== #


def test_overall_confidence_all_nan_segments_does_not_silently_propagate_repro():
    """RED contract: ALL-NaN input must NOT return NaN.

    Pre-fix: `np.mean([NaN, NaN, NaN])` = NaN. Post-fix should
    treat the list as no finite signal — return 0.0 (or a typed
    error), not silent NaN.
    """
    seg = ElementSegmenter()
    segments = [_seg(float("nan"), 0), _seg(float("nan"), 1), _seg(float("nan"), 2)]
    result = seg._compute_overall_confidence(segments)
    assert not (isinstance(result, float) and math.isnan(result)), (
        f"BUG: _compute_overall_confidence returned NaN for all-NaN input — "
        f"silent NaN propagation. Got {result!r}."
    )


# =========================================================================== #
# Observable 3: a mix of NaN and finite values must ignore NaN entries.
# =========================================================================== #


def test_overall_confidence_mixed_nan_finite_ignores_nan_repro():
    """RED contract: with mixed NaN/finite input, the NaN entries
    must be ignored, not poison the mean. With [0.5, NaN, 0.9]
    the post-fix result should equal 0.7 (mean of 0.5 and 0.9),
    NOT NaN.
    """
    seg = ElementSegmenter()
    segments = [_seg(0.5, 0), _seg(float("nan"), 1), _seg(0.9, 2)]
    result = seg._compute_overall_confidence(segments)
    assert not (isinstance(result, float) and math.isnan(result)), (
        f"BUG: _compute_overall_confidence returned NaN for mixed input — "
        f"silent NaN propagation. Got {result!r}."
    )
    assert math.isclose(result, 0.7, abs_tol=1e-9), (
        f"BUG: expected NaN entries to be ignored → mean of [0.5, 0.9] = 0.7, got {result!r}."
    )


# =========================================================================== #
# Regression: all-finite input must produce the arithmetic mean unchanged.
# =========================================================================== #


def test_overall_confidence_all_finite_unchanged_regression_repro():
    """Regression: with all-finite input, behavior must be the
    arithmetic mean of the confidences. The fix (NaN guard) must
    not change the typical happy path.
    """
    seg = ElementSegmenter()
    segments = [_seg(0.2, 0), _seg(0.4, 1), _seg(0.6, 2), _seg(0.8, 3)]
    result = seg._compute_overall_confidence(segments)
    assert math.isclose(result, 0.5, abs_tol=1e-9), (
        f"BUG (regression): expected mean of [0.2, 0.4, 0.6, 0.8] = 0.5, got {result!r}."
    )


# =========================================================================== #
# Source check: the isfinite/NaN guard IS present in the function body
# (the fix is locked in).
# =========================================================================== #


def test_overall_confidence_isfinite_guard_locked_in_source_repro():
    """Source check: the NaN guard IS present in
    `_compute_overall_confidence`. If a future refactor reintroduces
    the raw `np.mean([s.confidence for s in segments])` pattern, this
    test FAILS, signaling the silent-NaN regression is back.

    Acceptable guards (any one of):
      - `math.isfinite(...)` filter
      - `np.nanmean(...)`
      - explicit `if isnan: skip` loop
    """
    src = inspect.getsource(ElementSegmenter._compute_overall_confidence)
    has_guard = "isfinite" in src or "isnan" in src or "nanmean" in src
    # Also reject the bare unguarded list-comprehension mean pattern.
    has_unguarded_bug = "np.mean([s.confidence for s in segments])" in src and not has_guard
    assert has_guard and not has_unguarded_bug, (
        "BUG: _compute_overall_confidence has no isfinite/isnan/nanmean guard. "
        "The silent NaN propagation regression is back.\n"
        f"Source:\n{src}"
    )
