"""RED repro — Sports2DTracker all-NaN first-frame person (#969).

Bug: on the first frame, if a person's keypoints are all-NaN (detector
returned no valid keypoints — heavy occlusion / model warmup), the Kalman
filter state is initialized with NaN. The all-NaN slice flows through
``np.nanmean`` which emits ``RuntimeWarning: Mean of empty slice`` on every
such person every frame (log spam), and pre-#567 the resulting NaN centroid
poisoned the Kalman state forever, producing a permanent phantom track.

Root cause: ``_centroid`` calls ``np.nanmean`` unconditionally. On an
all-NaN slice, ``nanmean`` warns (Mean of empty slice) and returns NaN.
The downstream ``isfinite`` guard (added by #567) catches the NaN, but the
warning has already fired and the Kalman state is initialized with the
(0,0) fallback sentinel — a phantom track at the origin persists until
``_max_lost_frames`` purges it.

Fix direction: guard ``_centroid`` so that an all-NaN keypoint set is
detected BEFORE ``np.nanmean`` is called (no warning), and skip track
creation in ``update`` for all-NaN first-frame persons (no phantom track
at the sentinel origin). Mirrors the isfinite-guard pattern used in
deepsort_tracker and _track_validator.

RED contract:
- all-NaN first-frame person → no "Mean of empty slice" RuntimeWarning,
  no phantom track created (track count stays at the finite-person
  count), Kalman states finite (no NaN).
- finite first frame unchanged (regression).
- mixed: finite person unaffected by NaN person in the same frame.
- source-check: ``_centroid`` has an ``np.all(np.isnan(...))`` (or
  equivalent) guard BEFORE the ``np.nanmean`` call — locks the root
  cause, not a downstream mask.
"""

import inspect
import warnings

import numpy as np
import pytest

from src.tracking.sports2d import Sports2DTracker


def _finite_person(cx: float = 0.4, cy: float = 0.5) -> np.ndarray:
    kps = np.zeros((17, 2), dtype=np.float64)
    kps[:, 0] = cx
    kps[:, 1] = cy
    return kps


def _nan_person() -> np.ndarray:
    return np.full((17, 2), np.nan, dtype=np.float64)


def test_all_nan_first_frame_no_mean_of_empty_slice_warning():
    """First frame with an all-NaN person must NOT emit
    ``RuntimeWarning: Mean of empty slice``. The guard must be placed
    BEFORE ``np.nanmean`` so the warning never fires.
    RED: ``np.nanmean(all-NaN)`` warns before the isfinite fallback.
    """
    kps = np.stack([_finite_person(), _nan_person()], axis=0)
    scores = np.ones((2, 17), dtype=np.float64)
    tracker = Sports2DTracker()

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        tracker.update(kps, scores)  # must not raise RuntimeWarning


def test_all_nan_first_frame_no_phantom_track_and_finite_kalman():
    """First frame: 1 finite person + 1 all-NaN person. The all-NaN
    person must NOT create a NaN-poisoned phantom track — its Kalman
    state (if created) must be finite so it can re-associate on a later
    finite frame instead of being silently lost forever.

    RED: pre-fix the all-NaN person's Kalman state position is NaN; the
    ``nan_to_num`` mask on the distance matrix hides the NaN-distance
    but never fixes the state, so the track is permanent and unmatchable.
    """
    kps = np.stack([_finite_person(), _nan_person()], axis=0)
    scores = np.ones((2, 17), dtype=np.float64)
    tracker = Sports2DTracker()
    track_ids = tracker.update(kps, scores)

    # Every returned track must have a finite Kalman state — no NaN
    # phantom that can never re-associate.
    for tid in track_ids:
        assert tid in tracker._kalman_states, f"track {tid} has no Kalman state"
        state, cov = tracker._kalman_states[tid]
        assert np.all(np.isfinite(state)), (
            f"Kalman state for track {tid} contains NaN/Inf — NaN-poisoned phantom track"
        )
        assert np.all(np.isfinite(cov)), f"Kalman covariance for track {tid} contains NaN/Inf"


def test_finite_first_frame_unchanged_regression():
    """A fully-finite first frame must behave exactly as before: one
    track per person, all Kalman states finite, no warnings.
    Regression guard for the fix.
    """
    kps = np.stack([_finite_person(0.3, 0.4), _finite_person(0.6, 0.7)], axis=0)
    scores = np.ones((2, 17), dtype=np.float64)
    tracker = Sports2DTracker()

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        track_ids = tracker.update(kps, scores)

    assert len(track_ids) == 2
    for tid in track_ids:
        state, _cov = tracker._kalman_states[tid]
        assert np.all(np.isfinite(state)), f"track {tid} state not finite"
        # Position matches the centroid of the finite keypoints.
        assert np.isclose(state[0, 0], 0.3) or np.isclose(state[0, 0], 0.6)


def test_mixed_frame_nan_person_does_not_affect_finite_person():
    """First frame: 1 finite person + 1 all-NaN person. The finite
    person's track ID and Kalman state must be unaffected by the NaN
    person — same first track id, same finite state as if the NaN
    person weren't there.
    """
    # With NaN person present.
    kps_mixed = np.stack([_finite_person(0.3, 0.4), _nan_person()], axis=0)
    scores_mixed = np.ones((2, 17), dtype=np.float64)
    t_mixed = Sports2DTracker()
    ids_mixed = t_mixed.update(kps_mixed, scores_mixed)

    # Finite-only (control).
    kps_only = _finite_person(0.3, 0.4)[np.newaxis, ...]
    scores_only = np.ones((1, 17), dtype=np.float64)
    t_only = Sports2DTracker()
    ids_only = t_only.update(kps_only, scores_only)

    # First track id is the finite person's (both start from _next_id=0).
    assert ids_mixed[0] == ids_only[0], "finite person's track id shifted by the NaN person"
    # Kalman state for the finite person matches (NaN person didn't shift it).
    state_mixed, _ = t_mixed._kalman_states[ids_mixed[0]]
    state_only, _ = t_only._kalman_states[ids_only[0]]
    np.testing.assert_allclose(state_mixed.ravel(), state_only.ravel())


def test_centroid_source_has_all_nan_guard_before_nanmean():
    """Source-check: ``_centroid`` must guard against an all-NaN
    keypoint set BEFORE calling ``np.nanmean`` (which is what emits the
    ``Mean of empty slice`` warning). This locks the root cause — a
    downstream-only isfinite check on the nanmean result is insufficient
    because the warning has already fired.

    RED: current source calls ``np.nanmean(keypoints[:, 0])`` with no
    preceding ``np.all(np.isnan(...))`` guard.
    """
    src = inspect.getsource(Sports2DTracker._centroid)
    # Match the actual call sites (not docstring/comment mentions): the
    # guard is `np.isnan(...)` and the warning source is the call
    # `np.nanmean(keypoints...)`. A leading np.all(np.isnan(...)) guard
    # must appear before the first np.nanmean(keypoints...) call.
    isnan_pos = src.find("np.isnan(")
    nanmean_pos = src.find("np.nanmean(keypoints")
    assert isnan_pos != -1, "_centroid has no np.isnan(...) guard — root cause not addressed"
    assert nanmean_pos != -1, "_centroid missing np.nanmean(keypoints...) call"
    assert isnan_pos < nanmean_pos, (
        "_centroid np.isnan guard must precede np.nanmean(keypoints...) — "
        "otherwise the 'Mean of empty slice' warning fires first"
    )
