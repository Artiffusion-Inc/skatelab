"""RED repro — inclusive-end span vs count off-by-one (#515, #516).

Two sibling sites compute a frame SPAN (last - first) instead of a COUNT
(last - first + 1) where the end index is INCLUSIVE. An exact-boundary case
(30 frames at 30 fps = exactly 1.0 s) is rejected/undercounted by one frame.

1. spin_classifier.py:90  `duration_s = (spin_frames[-1] - spin_frames[0]) / fps`
   A spin occupying exactly 30 consecutive frames (indices 0..29) at 30 fps
   is a true 1.0 s spin, but span = 29 - 0 = 29 → 29/30 = 0.9667 s < 1.0 →
   `is_spin = False` (line 93). The exact-1.0 s threshold spin is missed.
   Correct: `(spin_frames[-1] - spin_frames[0] + 1) / fps`.

2. types.py:740  `ElementSegment.duration_frames` returns `self.end - self.start`
   The `end` field is an INCLUSIVE last-frame index (tas/inference.py:129
   returns `end-1`; element_segmenter.py:224 stores it verbatim;
   element_segmenter.py:207 slices `poses[start : end+1]` knowing it is
   inclusive). A 30-frame segment [0, 29] has duration_frames = 29 - 0 = 29,
   not 30. Correct: `self.end - self.start + 1`.

Bug class: inclusive-end span vs count off-by-one.

These tests MUST fail (RED) against the current code. Repros, not fixes.
"""

import numpy as np

from src.analysis.spin_classifier import detect_spin
from src.types import ElementSegment

# ---------------------------------------------------------------------------
# Bug 1: detect_spin span vs count — exact 1.0 s spin rejected
# ---------------------------------------------------------------------------


def test_detect_spin_exact_one_second_is_detected():
    """A spin occupying exactly 30 consecutive frames at 30 fps is exactly
    1.0 s and must be detected as a spin (is_spin True). RED now: span=29 →
    0.9667 s < 1.0 → is_spin False.
    """
    fps = 30.0
    n_frames = 30  # exactly 1.0 s at 30 fps
    vel = np.full(n_frames, 350.0, dtype=np.float32)  # every frame > 200 deg/s
    hip_y = np.full(n_frames, 0.5, dtype=np.float32)

    is_spin, duration_s, _hip_range, _mask = detect_spin(vel, hip_y, fps=fps)

    assert bool(is_spin) is True, (
        f"BUG #515: detect_spin rejected an exact 1.0 s spin — is_spin={is_spin}, "
        f"duration_s={duration_s}. spin_classifier.py:90 uses span "
        f"(spin_frames[-1]-spin_frames[0])/fps = (29-0)/30 = 0.9667 < 1.0, so "
        f"line 93 `duration_s >= 1.0` is False. 30 consecutive frames at 30 fps "
        f"is a TRUE 1.0 s spin; the count is 30 (last-first+1), not the span 29. "
        f"Fix: (spin_frames[-1]-spin_frames[0]+1)/fps."
    )


# ---------------------------------------------------------------------------
# Bug 2: ElementSegment.duration_frames span vs count — undercounts by 1
# ---------------------------------------------------------------------------


def test_element_segment_duration_frames_counts_inclusive_end():
    """A segment [start=0, end=29] (inclusive end) spans 30 frames; its
    duration_frames must be 30, not 29. RED now: end-start = 29.
    """
    seg = ElementSegment(
        element_type="waltz_jump",
        start=0,
        end=29,  # inclusive last-frame index → 30 frames [0, 29]
        confidence=0.9,
    )

    assert seg.duration_frames == 30, (
        f"BUG #516: ElementSegment.duration_frames = {seg.duration_frames} "
        f"for [start=0, end=29] (inclusive end, 30 frames), expected 30. "
        f"types.py:740 returns self.end - self.start (span 29), but `end` is an "
        f"INCLUSIVE last-frame index (tas/inference.py:129 returns end-1; "
        f"element_segmenter.py:207 slices poses[start:end+1] knowing inclusive). "
        f"Fix: self.end - self.start + 1."
    )
