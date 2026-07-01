"""RED repro — divide-by-fps crashes/corruption when video fps is 0.0 (#505).

cv2 returns fps=0.0 for broken-header / remuxed / unusual-codec videos
(ml/src/utils/video.py:54, unguarded `float(cap.get(CAP_PROP_FPS))`). Three
sibling analysis files divide by `fps` with NO guard — #499/#501 fixed
types.py fps=0; these sibling files were missed.

1. element_segmenter.py:453 — `round(num_frames / fps, 3)` where num_frames is
   a pure Python int → `int / 0.0` raises ZeroDivisionError (HARD CRASH, kills
   process_video_task). Reached via ElementSegmenter.segment() which threads
   video_meta.fps to _extract_segment_features.

2. phase_detector.py:222 / :443 — `airtime = (landing_idx - takeoff_idx) / fps`
   where the numerator is a numpy int64 → numpy `/ 0.0` yields `inf` + a
   RuntimeWarning (NOT ZeroDivisionError). The downstream plausibility check
   `airtime < 0.3` is `False` for inf, so an impossible infinite-airtime
   segment is ACCEPTED instead of rejected — the validation gate is bypassed
   and a garbage PhaseDetectionResult with non-zero confidence is returned.

3. spin_classifier.py:90 — `duration_s = (spin_frames[-1] - spin_frames[0])
   / fps` numpy int64 / 0.0 → inf; `is_spin = duration_s >= 1.0` → True for
   inf, so a degenerate spin (any two spinning frames under fps=0) is reported
   with an infinite duration.

Bug class: divide-by-zero / inconsistent-guard-across-siblings (#499/#501-class).

These tests MUST fail (RED) against the current code. Repros, not fixes.
"""

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter
from src.analysis.phase_detector import PhaseDetector
from src.analysis.spin_classifier import detect_spin

# ---------------------------------------------------------------------------
# Bug 1: element_segmenter _extract_segment_features ZeroDivisionError on fps=0
# ---------------------------------------------------------------------------


def test_extract_segment_features_fps_zero_no_crash():
    """A segment under fps=0 must not crash with ZeroDivisionError."""
    seg = ElementSegmenter()
    # 2-frame valid segment (enough for _compute_motion_energy's np.pad).
    poses = np.random.RandomState(0).randn(2, 17, 2).astype(np.float32) * 0.1 + 0.5

    raised = False
    exc: BaseException | None = None
    try:
        seg._extract_segment_features(poses, fps=0.0)
    except ZeroDivisionError as e:  # noqa: B017 — bug-hunt repro
        raised = True
        exc = e

    assert not raised, (
        f"BUG 1: _extract_segment_features crashes on fps=0: "
        f"{type(exc).__name__}: {exc}. element_segmenter.py:453 "
        f"round(num_frames / fps, 3) with pure-int num_frames and fps=0.0 raises "
        f"ZeroDivisionError, killing process_video_task. #499/#501-class sibling "
        f"(types.py fps=0 was guarded, these analysis files were not)."
    )


# ---------------------------------------------------------------------------
# Bug 2: phase_detector airtime=inf on fps=0 bypasses plausibility gate
# ---------------------------------------------------------------------------


def test_detect_jump_phases_fps_zero_no_infinite_airtime():
    """Under fps=0 the airtime plausibility gate must reject an impossible
    segment. phase_detector.py:222/:443 `(landing_idx-takeoff_idx)/fps` is
    numpy int64 / 0.0 → inf, and `inf < 0.3` is False, so the gate accepts an
    impossible infinite-airtime segment (returns a non-degenerate result with
    takeoff != landing and non-zero confidence). After the fix (fps<=0 →
    airtime=0.0, which fails the < 0.3 gate → fallback), the result is the
    degenerate fallback (confidence 0 / default phases).
    """
    detector = PhaseDetector()
    # Enough frames for the parabolic path (>=12) with a clear CoM arc.
    rng = np.random.RandomState(0)
    poses = np.zeros((40, 17, 2), np.float32)
    # Construct a CoM arc: hip y dips in the middle (a jump).
    t = np.arange(40)
    arc = -0.3 * ((t - 20) / 10.0) ** 2 + 0.5
    poses[:, 0, 1] = arc  # hip center y
    poses[:, :, 0] = 0.5
    poses += rng.randn(40, 17, 2).astype(np.float32) * 0.01

    result = detector.detect_phases(poses, fps=0.0, element_type="waltz_jump")

    # RED now (bug): the inf airtime bypasses the < 0.3 plausibility gate, so a
    # non-degenerate result (takeoff != landing, confidence > 0) is ACCEPTED.
    # GREEN after fix: fps<=0 → airtime=0.0 → gate rejects → degenerate fallback.
    assert result.confidence == 0.0 or result.phases.takeoff == result.phases.landing, (
        f"BUG 2: phase_detector accepted an impossible segment under fps=0 "
        f"(takeoff={result.phases.takeoff}, landing={result.phases.landing}, "
        f"confidence={result.confidence}). phase_detector.py:222/:443 "
        f"`(landing-takeoff)/fps` is numpy int64 / 0.0 → inf, and the "
        f"`airtime < 0.3` plausibility gate is False for inf, so an impossible "
        f"infinite-airtime segment is ACCEPTED instead of rejected. "
        f"#499/#501-class sibling."
    )


# ---------------------------------------------------------------------------
# Bug 3: spin_classifier duration_s=inf on fps=0 → false spin accepted
# ---------------------------------------------------------------------------


def test_detect_spin_fps_zero_no_infinite_duration():
    """Under fps=0 a detected spin must not report an infinite duration.
    spin_classifier.py:90 `(spin_frames[-1]-spin_frames[0])/fps` numpy int64 /
    0.0 → inf; `duration_s >= 1.0` → True, so any two spinning frames under
    fps=0 is reported as a spin with infinite duration.
    """
    # Two frames above the spin threshold → is_spinning True at frames 5 and 10.
    angular_velocity = np.zeros(15, np.float32)
    angular_velocity[5] = 300.0
    angular_velocity[10] = 300.0
    hip_y = np.linspace(0.4, 0.5, 15).astype(np.float32)

    is_spin, duration_s, _hip_range = detect_spin(angular_velocity, hip_y, fps=0.0)

    assert not (is_spin and not np.isfinite(duration_s)), (
        f"BUG 3: detect_spin reports a spin with infinite duration under fps=0: "
        f"is_spin={is_spin}, duration_s={duration_s}. spin_classifier.py:90 "
        f"`(spin_frames[-1]-spin_frames[0])/fps` is numpy int64 / 0.0 → inf, and "
        f"`duration_s >= 1.0` is True for inf, so a degenerate spin is accepted. "
        f"#499/#501-class sibling."
    )
