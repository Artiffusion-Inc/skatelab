"""GREEN contract (#952): PoseTracker(fps=0) must NOT crash — fall back to
frame-based dt=1.0 like its Sports2D sibling.

Bug (#610 raised ValueError on fps<=0, which killed the worker job at the
FIRST pipeline stage for corrupt videos where cv2.CAP_PROP_FPS=0). Fix
(#952): a corrupt video with fps=0 degrades gracefully — dt=1.0 (one sample
per step, frame-index time), Kalman matrices finite. Mirror the Sports2D
sibling (ml/src/tracking/sports2d.py:53 `dt=1`, frame-based, no /fps).
"""

import numpy as np
import pytest


def test_pose_tracker_init_with_zero_fps_does_not_crash():
    """fps=0 must not crash — falls back to frame-based dt=1.0."""
    from src.detection.pose_tracker import PoseTracker

    tracker = PoseTracker(fps=0.0)
    assert tracker is not None
    assert tracker.dt == 1.0
    assert np.isfinite(tracker.dt)


def test_pose_tracker_init_with_negative_fps_does_not_crash():
    """fps<0 falls back to frame-based dt=1.0 (no sign-error crash)."""
    from src.detection.pose_tracker import PoseTracker

    tracker = PoseTracker(fps=-1.0)
    assert tracker.dt == 1.0
    assert np.isfinite(tracker.dt)


def test_pose_tracker_fps_zero_kalman_matrices_finite():
    """fps=0 → Kalman matrices (F/H/Q/R/P0) all finite — no inf/NaN."""
    from src.detection.pose_tracker import PoseTracker

    tracker = PoseTracker(fps=0.0)
    for mat in (tracker.F, tracker.H, tracker.Q, tracker.R, tracker.P0):
        assert np.all(np.isfinite(mat)), "Kalman matrix has inf/NaN entries at fps=0"


def test_pose_tracker_init_with_valid_fps_succeeds():
    """fps=30 (default) unchanged — dt=1/30 (regression guard)."""
    from src.detection.pose_tracker import PoseTracker

    tracker = PoseTracker(fps=30.0)
    assert tracker.dt == pytest.approx(1.0 / 30.0)
