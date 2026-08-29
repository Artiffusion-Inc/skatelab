"""RED repro — Sports2D lost-track re-association: np.nansum on all-NaN
person yields 0.0 → steals lost track id at perfect distance.

Bug: Sports2DTracker.update lost-track re-association block
(sports2d.py:244-249):

  :244  disp_exp   = lost_kps[:, np.newaxis, :, :]      # (n_lost, 1, 17, 2)
  :245  unassoc_exp = unassoc_kps[np.newaxis, :, :, :]  # (1, n_unassoc, 17, 2)
  :246  d = unassoc_exp - disp_exp
  :247  dists = np.sqrt(np.nansum(d**2, axis=3))        # <-- BUG
  :248  lost_matrix = np.nanmean(dists, axis=2)
  :249  lost_matrix = np.nan_to_num(lost_matrix, nan=1e10, posinf=1e10)

`np.nansum` on an all-NaN slice returns 0.0 (NOT NaN — it treats an
all-NaN slice as an empty sum, summing zero finite values). So for a
person whose 17 keypoints are all NaN (MogaNet inference failure on a
heavily-occluded crop), `d**2` is all-NaN, `np.nansum` returns 0.0,
`sqrt(0.0)=0.0`, `np.nanmean(0.0-array)=0.0`, and `np.nan_to_num(0.0)`
leaves 0.0 (0 is not NaN). The all-NaN person matches the lost track at
distance 0.0 — a perfect match — and steals that track's id.

The MAIN association matrix (sports2d.py:170) has a `nan_to_num(...,
nan=1e10)` guard on a centroid-distance matrix that is NaN when
centroids are NaN — so an all-NaN person is pushed to distance 1e10 in
the main pass and left unassociated. But the LOST-track re-association
matrix (the second cost matrix in the same file) uses `np.nansum`, which
yields 0.0 BEFORE `nan_to_num` runs (0 is not NaN → nan_to_num leaves
it). So the two cost matrices in the same file apply INCONSISTENT
NaN-handling: main matrix → all-NaN = far (1e10); lost matrix → all-NaN
= perfect (0.0). The all-NaN person, rejected by the main matrix as
untrustworthy, is then handed a lost track id by the lost matrix at
distance 0.0.

Scenario:
  frame1: 2 normal people A (x=0.3) + B (x=0.7)  → ids [0, 1]
  frame2: only B                                  → A becomes lost (id 0)
  frame3: B + all-NaN person at x=0.05 (far from
          A's last real position x=0.3)           → all-NaN person steals
          A's lost id 0 at distance 0.0

Expected: all-NaN person gets a NEW id (2) or is skipped — it must NOT
steal A's lost id 0. A's last real position was x=0.3; the all-NaN
person is at x=0.05 (0.25 away in normalized coords). Distance 0.0 is
obviously wrong — it is the np.nansum empty-slice artifact.

Prod-impact (HIGH): the ML pipeline feeds h36m poses to
Sports2DTracker.update (tracking_backend="sports2d" fallback when
DeepSORT is unavailable). All-NaN keypoints are reachable — MogaNet-B
returns NaN confidence on a heavily-occluded / failed crop, and the
h36m conversion + gap-filling can propagate NaN keypoints into a track
slot. The all-NaN person silently steals a nearby lost track id → a
silent ID switch → the wrong person's skeleton flows into downstream
biomechanics metrics, DTW alignment, and Russian-text recommendations.
No crash, no warning — the id switch is invisible.

Existing test `test_nan_keypoints_no_crash` (tracking/test_sports2d.py)
uses a 1-of-17 NaN partial (RFOOT=NaN) — `np.nansum` sums the other 16
finite joints → a real distance → no steal. The all-17-NaN case is
untested. This test fills that gap.

Fix direction (do NOT apply here): guard all-NaN rows/cols BEFORE
`np.nansum`, e.g.
  all_nan_lost  = np.isnan(lost_kps).all(axis=(2,3))         # (n_lost,)
  all_nan_unassoc = np.isnan(unassoc_kps).all(axis=(2,3))    # (n_unassoc,)
  dists = np.sqrt(np.nansum(d**2, axis=3))
  lost_matrix = np.nanmean(dists, axis=2)
  # mask all-NaN to inf so they never match at 0.0
  lost_matrix[np.ix_(all_nan_lost, all_nan_unassoc)] = np.inf
or replace `np.nansum` with a NaN-propagating reduction matching the
main matrix guard. One guard in the lost-matrix makes its NaN-handling
consistent with the main matrix.

This test MUST fail (RED) against the current code. Repro, not a fix.
"""

import warnings

import numpy as np

from src.tracking.sports2d import Sports2DTracker
from src.types import H36Key


def _make_person_pose(cx: float, cy: float, scale: float = 0.1) -> np.ndarray:
    """Build a simple standing-person pose centered at (cx, cy). (17, 2)."""
    pose = np.zeros((17, 2), dtype=np.float32)
    s = scale / 0.1
    pose[H36Key.HIP_CENTER] = [cx, cy]
    pose[H36Key.RHIP] = [cx - 0.04 * s, cy]
    pose[H36Key.LHIP] = [cx + 0.04 * s, cy]
    pose[H36Key.RKNEE] = [cx - 0.04 * s, cy + 0.20 * s]
    pose[H36Key.LKNEE] = [cx + 0.04 * s, cy + 0.20 * s]
    pose[H36Key.RFOOT] = [cx - 0.04 * s, cy + 0.40 * s]
    pose[H36Key.LFOOT] = [cx + 0.04 * s, cy + 0.40 * s]
    pose[H36Key.SPINE] = [cx, cy - 0.15 * s]
    pose[H36Key.THORAX] = [cx, cy - 0.25 * s]
    pose[H36Key.NECK] = [cx, cy - 0.30 * s]
    pose[H36Key.HEAD] = [cx, cy - 0.35 * s]
    pose[H36Key.LSHOULDER] = [cx + 0.08 * s, cy - 0.25 * s]
    pose[H36Key.RSHOULDER] = [cx - 0.08 * s, cy - 0.25 * s]
    pose[H36Key.LELBOW] = [cx + 0.12 * s, cy - 0.15 * s]
    pose[H36Key.RELBOW] = [cx - 0.12 * s, cy - 0.15 * s]
    pose[H36Key.LWRIST] = [cx + 0.14 * s, cy - 0.05 * s]
    pose[H36Key.RWRIST] = [cx - 0.14 * s, cy - 0.05 * s]
    return pose


def _scores(n: int, base: float = 0.9) -> np.ndarray:
    return np.full((n, 17), base, dtype=np.float32)


def test_all_nan_person_does_not_steal_lost_track_id():
    """An all-NaN person must not steal a lost track's id at distance 0.0.

    The all-NaN person is far from A's last real position, so a 0.0
    match is the np.nansum empty-slice artifact, not a real association.
    """
    # np.nanmean on all-NaN raises a RuntimeWarning; we want the BUG
    # behaviour (returns NaN/0) to surface, not the warning to error the
    # test. We assert on the id-assignment contract, not on warnings.
    tracker = Sports2DTracker(max_dist=None, max_disappeared=30, fps=30.0)

    person_a = _make_person_pose(0.3, 0.5)  # A at x=0.3
    person_b = _make_person_pose(0.7, 0.5)  # B at x=0.7

    # frame 1: two normal people → ids [0, 1]
    ids1 = tracker.update(np.array([person_a, person_b]), _scores(2))
    assert ids1 == [0, 1]

    # frame 2: only B present → A (id 0) becomes "lost" (within max_disappeared)
    ids2 = tracker.update(np.array([person_b]), _scores(1))
    assert ids2 == [1]
    # A's lost keypoints are stored at its last real position x=0.3
    assert 0 in tracker._lost_keypoints, "A should be registered as lost"

    # frame 3: B + an ALL-NaN person at x=0.05 (FAR from A's last x=0.3).
    # The all-NaN person represents a MogaNet failure on an occluded crop:
    # all 17 keypoints (xy AND score) are NaN.
    all_nan_person = np.full((17, 2), np.nan, dtype=np.float32)
    # scores shape must be (P, 17); build a (1,17)+B's scores → (2,17)
    frame3_kps = np.array([person_b, all_nan_person])
    frame3_scores = np.array([_scores(1, 0.9)[0], np.full(17, np.nan, dtype=np.float32)])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        ids3 = tracker.update(frame3_kps, frame3_scores)

    # ids3[0] is B (should keep id 1); ids3[1] is the all-NaN person.
    assert ids3[0] == 1, f"B should keep id 1, got ids3={ids3}"

    # CONTRACT: the all-NaN person must NOT steal A's lost id 0.
    # It should get a NEW id (2) — or be skipped — but never inherit id 0
    # via the np.nansum empty-slice=0.0 perfect-distance artifact.
    all_nan_id = ids3[1]
    assert all_nan_id != 0, (
        "BUG: all-NaN person stole lost track id 0 (A's last real position "
        "x=0.3) via np.nansum empty-slice=0.0 → sqrt(0)=0 → distance 0.0 "
        "perfect match in the lost-track re-association matrix. The main "
        "association matrix guards nan_to_num(nan=1e10) but the lost matrix "
        "uses np.nansum which yields 0.0 BEFORE nan_to_num (0 is not NaN → "
        "nan_to_num leaves it). Inconsistent NaN-handling between the two "
        f"cost matrices → silent ID switch → wrong-person skeleton. ids3={ids3}"
    )
