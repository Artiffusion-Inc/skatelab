"""RED repro — ElementPhase.airtime_sec crashes (ZeroDivisionError) on fps=0.
No guard. 4th intra-file sibling in types.py missed by #499.

BUG #2 (MEDIUM — divide-by-zero / inconsistent-guard-across-siblings
        intra-types.py, #499 sibling):
    ml/src/types.py:489  ElementPhase.airtime_sec:
        `return (self.landing - self.takeoff) / fps`   (NO guard)
    ml/src/types.py:450  VideoMeta.duration_sec:
        `return self.num_frames / self.fps if self.fps > 0 else 0.0`  (HAS guard)
    ml/src/types.py:770 / :796  SegmentationResult.get_timeline /
        export_segments_json:  guarded via #499.

    #499 covered the SegmentationResult siblings (:770/:796) but MISSED
    :489 (airtime_sec) — a 4th sibling in the SAME file. fps=0 is an
    anticipated edge (corrupt / unreadable video, cv2.CAP_PROP_FPS=0 —
    VideoMeta.duration_sec guards exactly this case).

    Prod flow: pipeline.py:315 → metrics.py:191 _analyze_jump →
    compute_airtime → phases.airtime_sec(fps) → ZeroDivisionError.

    Existing test_types.py:190 tests airtime_sec with fps=30/60 only — no
    fps=0 case.

This test asserts airtime_sec(fps=0.0) does NOT raise (expected 0.0, mirroring
VideoMeta.duration_sec). Currently raises ZeroDivisionError → RED.
"""

import pytest

from src.types import ElementPhase


def test_elementphase_airtime_sec_fps_zero_no_crash():
    """ElementPhase.airtime_sec must not raise ZeroDivisionError on fps=0.
    types.py:489 `(self.landing - self.takeoff) / fps` has no guard, but
    VideoMeta.duration_sec (:450) HAS `if self.fps > 0 else 0.0`. Same-file
    sibling (#499 covered :770/:796, missed :489). fps=0 = corrupt video
    (cv2.CAP_PROP_FPS=0) → crashes the jump-metrics path
    (pipeline → _analyze_jump → compute_airtime → airtime_sec).
    """
    phase = ElementPhase(
        name="waltz_jump",
        start=5,
        takeoff=10,
        peak=15,
        landing=20,
        end=25,
    )

    raised = False
    exc: BaseException | None = None
    try:
        phase.airtime_sec(fps=0.0)
    except ZeroDivisionError as e:
        raised = True
        exc = e

    assert not raised, (
        f"BUG: ElementPhase.airtime_sec crashes on fps=0: {exc}. "
        f"types.py:489 `(self.landing - self.takeoff) / fps` has no guard. "
        f"VideoMeta.duration_sec (:450) guards `if self.fps > 0 else 0.0`; "
        f"#499 guarded SegmentationResult (:770/:796) but MISSED :489 — 4th "
        f"sibling intra-types.py. fps=0 anticipated (corrupt video, "
        f"cv2.CAP_PROP_FPS=0) → ZeroDivisionError on the jump-metrics path "
        f"(pipeline.py:315 → metrics.py:191 _analyze_jump → compute_airtime "
        f"→ airtime_sec). Expected 0.0, mirroring duration_sec."
    )
