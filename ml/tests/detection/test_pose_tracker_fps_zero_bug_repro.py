"""RED repro: pose_tracker PoseTracker(fps=0) crashes in __init__.

Bug (HIGH): ml/src/detection/pose_tracker.py:85 does
    self.dt = 1.0 / fps
without a guard. A caller passing fps=0 (e.g. from a corrupted video
where FPS detection failed, or an explicit bad config) crashes the
constructor with ZeroDivisionError. Worse than the silent NaN-poisoned
F matrix the agent's initial report suggested — the tracker fails to
even initialize, so downstream code can't recover gracefully.

This test verifies the contract: a tracker created with fps <= 0 must
NOT crash; it should either raise a clear ValueError (preferred) or
fall back to a safe default.
"""

import pytest


def test_pose_tracker_init_with_zero_fps_does_not_crash():
    """fps=0 must not crash PoseTracker construction."""
    from src.detection.pose_tracker import PoseTracker

    # Pre-fix: 1.0 / 0 → ZeroDivisionError. Post-fix: clear ValueError
    # with a message about fps being invalid.
    with pytest.raises(ValueError, match=r"fps.*positive|invalid.*fps|fps.*zero"):
        PoseTracker(fps=0.0)


def test_pose_tracker_init_with_negative_fps_does_not_crash():
    """fps=-1 must not crash (also divide by zero or sign error)."""
    from src.detection.pose_tracker import PoseTracker

    with pytest.raises(ValueError, match=r"fps.*positive|invalid.*fps|fps.*zero"):
        PoseTracker(fps=-1.0)


def test_pose_tracker_init_with_valid_fps_succeeds():
    """fps=30 (default) works fine — regression guard for the guard."""
    from src.detection.pose_tracker import PoseTracker

    tracker = PoseTracker(fps=30.0)
    assert tracker.dt == pytest.approx(1.0 / 30.0)
