"""RED repro — DTW single-frame reference silently returns 0.0 (perfect match).

Bug: MotionDTWAligner.compute_distance (motion_dtw.py:442) guards against
EMPTY input (`len(user)==0 or len(reference)==0` → inf, #452 fix), but a
SINGLE-FRAME reference slips through:

  :465  if len(user) == 0 or len(reference) == 0: return inf   # only empty
  :472  ref_phases = ElementPhase(end=len(reference) - 1)      # end = 0

Then align_with_keyframes splits into a "full" phase with ref_segment =
reference[0:0] (empty), so `len(ref_segment) == 0` → phase skipped
(motion_dtw.py:144). phase_alignments stays empty, and

  :170  total_distance = sum([]) / max(len([]), 1) = 0.0 / 1 = 0.0

A degenerate single-frame reference returns 0.0 — indistinguishable from a
real perfect match. This is the SAME #432/#434/#452 silent-0.0 bug-class:
a perfect-match distance corrupts the overall_score / GOE composite and
makes a degenerate/missing reference look like a flawless performance.

Reachability: a reference element reduced to one valid pose frame (aggressive
filtering, very short reference clip, or a reference built from a single
keyframe) reaches compute_distance and returns 0.0 instead of signalling
"no meaningful reference".

This test MUST fail (RED) against the current code. Repro, not a fix.
"""

import numpy as np

from src.alignment.motion_dtw import MotionDTWAligner


def test_compute_distance_single_frame_reference_is_not_perfect_match():
    """A single-frame reference must NOT return 0.0 against a real user
    sequence — that is indistinguishable from a genuine perfect match.
    """
    aligner = MotionDTWAligner()
    # Real user sequence: 30 frames of motion.
    user = np.random.RandomState(0).randn(30, 17, 2).astype(np.float32) * 0.1
    # Degenerate reference: a single frame.
    reference = np.random.RandomState(1).randn(1, 17, 2).astype(np.float32) * 0.1

    distance = aligner.compute_distance(user, reference)

    # CONTRACT: a single-frame reference must NOT silently return 0.0 (perfect
    # match). The fix extends #452's empty→inf sentinel to <2 frames, so inf is
    # the expected "no meaningful reference" signal (not a finite distance). The
    # only thing we must reject is 0.0 — the silent-perfect-match corruption.
    assert distance != 0.0, (
        f"BUG: single-frame reference returned distance={distance} — a "
        f"degenerate/missing reference is silently treated as a PERFECT match "
        f"(0.0), indistinguishable from a genuine perfect alignment. #452 "
        f"guarded the empty case (→inf) but missed single-frame: "
        f"ref_phases.end=0 → empty ref_segment → phase skipped → "
        f"sum([])/max(0,1)=0.0. This corrupts overall_score/GOE (#432/#434 "
        f"class): a one-frame reference makes any user sequence look flawless."
    )
