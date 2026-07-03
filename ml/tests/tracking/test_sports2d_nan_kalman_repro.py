"""RED repro — sports2d NaN centroid poisons Kalman state.

Bug: when keypoints[i] is all-NaN (low-confidence pose for a person on the
first detected frame), np.nanmean returns NaN. The NaN centroid is stored
in the Kalman state at line 153. Subsequent _kalman_predict returns NaN,
the distance matrix becomes NaN, and the track can never be re-associated
with a real detection.

Fix direction: at the centroid computation (line 85-89) or the state init
(line 152-153), detect NaN and either skip this person or use a default.

RED contract: when the first-frame keypoints for a person are all-NaN, the
resulting Kalman state must NOT contain NaN. Otherwise the track is lost
forever and downstream phase detection operates on partial data.
"""

import numpy as np
import pytest

from src.tracking.sports2d import Sports2DTracker


def test_first_frame_all_nan_does_not_poison_kalman_state():
    """First frame: 2 persons, person 0 has valid keypoints, person 1 is all-NaN.
    Person 1's Kalman state must NOT be NaN-poisoned — a fix initializes it
    with a sensible default (e.g. 0.0) or skips the person entirely.
    RED: state for person 1 is NaN, track is lost forever.
    """
    # Two persons, 17 keypoints each.
    # Person 0: valid keypoints (mid-frame).
    person0 = np.zeros((17, 2), dtype=np.float64)
    person0[:, 0] = 0.4
    person0[:, 1] = 0.5
    # Person 1: ALL NaN (low-confidence / occluded / model warmup).
    person1 = np.full((17, 2), np.nan, dtype=np.float64)
    keypoints = np.stack([person0, person1], axis=0)
    scores = np.ones((2, 17), dtype=np.float64)

    tracker = Sports2DTracker()
    track_ids = tracker.update(keypoints, scores)

    # After update, internal Kalman states for both tracks must be finite.
    for tid in track_ids:
        state, cov = tracker._kalman_states[tid]
        assert np.all(np.isfinite(state)), (
            f"Kalman state for track {tid} contains NaN/Inf — first-frame "
            f"all-NaN keypoints poisoned the state. The track is now lost "
            f"forever (np.nanmean → NaN → stored → never recovered). "
            f"State:\n{state}"
        )
        assert np.all(np.isfinite(cov)), f"Kalman covariance for track {tid} contains NaN/Inf."


def test_subsequent_frame_valid_does_not_resurrect_nan_state():
    """After an all-NaN first frame, a valid second frame for the same
    person should produce a finite Kalman state — the track is no longer
    lost. RED: state stays NaN from frame 1, distance matrix is NaN,
    linear_sum_assignment fails to re-associate.
    """
    # Frame 1: person 0 valid, person 1 all-NaN.
    person0_f1 = np.full((17, 2), 0.4, dtype=np.float64)
    person1_f1 = np.full((17, 2), np.nan, dtype=np.float64)
    keypoints_f1 = np.stack([person0_f1, person1_f1], axis=0)
    scores_f1 = np.ones((2, 17), dtype=np.float64)

    tracker = Sports2DTracker()
    track_ids_f1 = tracker.update(keypoints_f1, scores_f1)
    person1_tid = track_ids_f1[1]

    # Frame 2: person 0 valid, person 1 NOW VALID.
    person0_f2 = np.full((17, 2), 0.5, dtype=np.float64)
    person1_f2 = np.full((17, 2), 0.6, dtype=np.float64)
    keypoints_f2 = np.stack([person0_f2, person1_f2], axis=0)
    scores_f2 = np.ones((2, 17), dtype=np.float64)

    track_ids_f2 = tracker.update(keypoints_f2, scores_f2)

    # The same person (track_id from frame 1) should be re-associated, OR
    # if the fix dropped the NaN-person in frame 1, person 1 in frame 2
    # should get a fresh non-NaN state. Either way, NO NaN in the state.
    for tid in tracker._kalman_states:
        state, _cov = tracker._kalman_states[tid]
        assert np.all(np.isfinite(state)), (
            f"Kalman state for track {tid} still NaN-poisoned in frame 2 — "
            f"the all-NaN state from frame 1 was never recovered."
        )
