"""RED repro: motion_dtw.align_with_keyframes returns 0.0 for empty phases.

Bug (HIGH): ml/src/alignment/motion_dtw.py:170
    total_distance = sum(p.distance for p in phase_alignments) / max(len(phase_alignments), 1)

When all phases are empty or single-frame (skipped by `_align_phase`),
`len(phase_alignments) == 0`. The `max(..., 1)` guard prevents
ZeroDivisionError, but the sum is 0, divided by 1, yields `0.0` — a
silent "perfect match" score for completely degenerate input.

The sibling `compute_distance` (line 470) and `compute_distance_3d`
(line 515) have the #478 fix that returns `inf` for empty inputs.
`align_with_keyframes` was not patched.

This test verifies the contract: align_with_keyframes on empty
phases returns `inf` (not 0.0) so downstream scoring treats it as
"no match" rather than "perfect match".
"""

import numpy as np


def test_align_with_keyframes_empty_phases_returns_inf():
    """All phases empty → returns inf (no match), not 0.0 (perfect match)."""
    from src.alignment.motion_dtw import MotionDTWAligner
    from src.types import ElementPhase

    aligner = MotionDTWAligner()

    # User has a single frame, reference has a single frame — both empty
    # after phase extraction.
    user = np.zeros((1, 17, 2), dtype=np.float32)
    reference = np.zeros((1, 17, 2), dtype=np.float32)

    # Phases that produce 0 frames in both segments.
    user_phases = ElementPhase(name="test", start=0, takeoff=0, peak=0, landing=0, end=0)
    ref_phases = ElementPhase(name="test", start=0, takeoff=0, peak=0, landing=0, end=0)

    # Pre-fix: returns 0.0 (perfect match). Post-fix: returns inf.
    result = aligner.align_with_keyframes(user, user_phases, reference, ref_phases)
    assert result.total_distance == float("inf"), (
        f"Empty phases should return inf, got {result.total_distance}. "
        f"0.0 is a silent 'perfect match' that inflates the score for "
        f"degenerate input."
    )
