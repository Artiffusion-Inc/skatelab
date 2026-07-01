"""RED repro — two short-input crashes in the analysis/alignment layer.

Bug A (#476-class, production-reachable):
    PhaseDetector.detect_phases -> detect_jump_phases -> _detect_jump_phases_parabolic
    -> calculate_com_trajectory(poses) -> com_y -> np.gradient(com_y) * fps
    (phase_detector.py:151). np.gradient on a 1-element array raises:
        ValueError: Shape of array too small to calculate a numerical gradient,
        at least (edge_order + 1) elements are required.

    Reachability: ml/src/pipeline.py:274 / :306 call detect_phases(smoothed, ...)
    with NO len(poses) < 2 guard. A 1-frame valid video (single valid detection)
    reaches phase detection and crashes the whole process_video_task. Sibling of
    #476 (ElementSegmenter np.pad empty-axis crash) — same pipeline, no short-input
    guard before a gradient/diff op.

Bug B (#478-sibling, sentinel inconsistency):
    MotionDTWAligner.compute_distance guards len(user) < 2 or len(reference) < 2
    -> inf (#478), but compute_distance_3d guards ONLY len == 0 (motion_dtw.py:
    511). A single-frame 3D reference slips through and returns a FINITE DTW
    distance instead of the inf "no meaningful reference" sentinel — the same
    silent non-sentinel the 2D path was fixed to emit in #478. A degenerate
    single-frame 3D reference is treated as a real comparison.

These tests MUST fail (RED) against the current code. Repros, not fixes.
"""

import numpy as np

from src.alignment.motion_dtw import MotionDTWAligner
from src.analysis.phase_detector import PhaseDetector

# ---------------------------------------------------------------------------
# Bug A: PhaseDetector crashes on a 1-frame valid video (np.gradient on 1 elem)
# ---------------------------------------------------------------------------


def test_detect_jump_phases_one_frame_no_crash():
    """A 1-frame valid pose must NOT crash phase detection. Pipeline has no
    short-input guard before detect_phases, so a single-frame video reaches
    np.gradient(com_y) and raises ValueError.
    """
    detector = PhaseDetector()
    # 1-frame valid pose (normalized, 17 H3.6M joints, 2D).
    poses = np.random.RandomState(0).randn(1, 17, 2).astype(np.float32) * 0.1 + 0.5

    raised = False
    exc: BaseException | None = None
    try:
        detector.detect_phases(poses, fps=30.0, element_type="waltz_jump")
    except (ValueError, IndexError) as e:  # noqa: B017 — bug-hunt repro
        raised = True
        exc = e

    assert not raised, (
        f"BUG A: PhaseDetector.detect_phases crashes on a 1-frame video: "
        f"{type(exc).__name__}: {exc}. np.gradient(com_y) (phase_detector.py:151) "
        f"requires >=2 elements. Pipeline (pipeline.py:274/:306) calls detect_phases "
        f"with no len(poses)<2 guard, so a single-frame valid video crashes "
        f"process_video_task. Sibling of #476 (ElementSegmenter empty-axis crash) — "
        f"same missing short-input guard before a gradient op."
    )


# ---------------------------------------------------------------------------
# Bug B: compute_distance_3d single-frame reference must return inf (#478 parity)
# ---------------------------------------------------------------------------


def test_compute_distance_3d_single_frame_reference_is_not_finite():
    """A single-frame 3D reference must return inf (the degenerate/missing
    sentinel), matching the 2D compute_distance guard (#478). The 3D path
    guards only len==0, so a single-frame reference returns a FINITE distance
    — indistinguishable from a real comparison.
    """
    aligner = MotionDTWAligner()
    user = np.random.RandomState(0).randn(30, 17, 3).astype(np.float32) * 0.1
    reference = np.random.RandomState(1).randn(1, 17, 3).astype(np.float32) * 0.1

    distance = aligner.compute_distance_3d(user, reference)

    assert not np.isfinite(distance), (
        f"BUG B: compute_distance_3d single-frame reference returned a FINITE "
        f"distance={distance} instead of inf. The 2D path (compute_distance) "
        f"guards len<2 -> inf (#478), but compute_distance_3d guards only "
        f"len==0 (motion_dtw.py:511). A degenerate single-frame 3D reference is "
        f"treated as a real comparison — the same silent non-sentinel #478 fixed "
        f"for 2D. Fix: extend the 3D guard to len<2 -> inf for parity."
    )
