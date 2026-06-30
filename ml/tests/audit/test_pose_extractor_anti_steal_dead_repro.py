"""RED repro: _fill_target_pose pass-by-value reassignment kills the anti-steal guard.

Bug — `PoseExtractor._fill_target_pose`
  (ml/src/pose_estimation/pose_extractor.py:589-652) takes the caller's loop
  state — `last_target_pose`, `last_target_ratios`, `target_lost_frame` — as
  POSITIONAL parameters and REASSIGNS them LOCALLY:

      :613  last_target_pose = h36m_poses[p].copy()
      :614  last_target_ratios = compute_2d_skeletal_ratios(h36m_poses[p])
      :615  target_lost_frame = None
      :625  target_lost_frame = frame_idx
      :648-652  last_target_pose = best_new_pose.copy()
                last_target_ratios = compute_2d_skeletal_ratios(best_new_pose)
                target_lost_frame = None

  Python passes object references BY VALUE. Reassignment of the LOCAL name
  (binding it to a new object) does NOT propagate back to the caller's
  variable. The method returns None (signature `-> None`, no return
  statement). So:

      caller's last_target_pose  -> stays None forever
      caller's last_target_ratios -> stays None forever
      caller's target_lost_frame  -> stays None forever

Consequence — the anti-steal guard is DEAD CODE in BOTH production paths:
  - line :607  `if last_target_pose is not None and validator.is_stolen(...)`
    short-circuits to False EVERY frame (caller's last_target_pose is always
    None) -> `validator.is_stolen` is never called -> a skeleton-steal
    (wrong person suddenly locked on) is never detected.
  - lines :623-652  the migration/recovery branch is gated on
    `last_target_pose is not None` -> also unreachable -> occlusion recovery
    never fires.

  So `all_poses[frame_idx] = h36m_poses[p]` (line :612) writes the (stolen)
  wrong-person pose VERBATIM into the output. This is the exact failure mode
  the CLAUDE.md "Tracking Debugging Workflow" exists to diagnose — and it goes
  UNDETECTED in both `_extract_per_frame` (:282-284 init, :342-352 call) and
  `_extract_batch` (:416-418 init, :544-554 call).

Why existing tests pass while the bug is live:
  ml/tests/pose_estimation/test_pose_extractor.py uses constant identical
  detections every frame (FakePersonDetector same bbox, FakeMogaNet same
  keypoints). The dead anti-steal path is never exercised — there is no
  frame where `last_target_pose` would have been non-None and `is_stolen`
  would have been called — so the tests pass while the guard is dead.

Compounds #451 (the anti-steal NaN-keypoint bug): even after #451 is fixed,
  the whole anti-steal system stays dead because of this pass-by-value bug —
  `last_target_pose` is never non-None, so `is_stolen` is never reached.

These tests are intentionally RED against current code. They assert the
CORRECT contract (caller-visible state mutation OR returned state); current
code violates it. Do NOT weaken the assertions.
"""

import numpy as np
import pytest

from src.pose_estimation._track_state import TrackState
from src.pose_estimation._track_validator import TrackValidator
from src.pose_estimation.pose_extractor import PoseExtractor
from src.tracking.skeletal_identity import compute_2d_skeletal_ratios
from src.types import H36Key

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _normal_pose(cx: float = 0.50, cy: float = 0.50) -> np.ndarray:
    """A non-degenerate H3.6M pose centered at (cx, cy).

    All ratio-relevant joints are given distinct coords so the skeletal-ratio
    vector is non-trivial. Confidence = 0.9.
    """
    pose = np.zeros((17, 3), np.float32)
    pose[:, 2] = 0.9
    pose[H36Key.HIP_CENTER] = [cx, cy + 0.05, 0.9]
    pose[H36Key.NECK] = [cx, cy - 0.15, 0.9]
    pose[H36Key.LSHOULDER] = [cx - 0.10, cy - 0.20, 0.9]
    pose[H36Key.RSHOULDER] = [cx + 0.10, cy - 0.20, 0.9]
    pose[H36Key.LHIP] = [cx - 0.05, cy + 0.10, 0.9]
    pose[H36Key.RHIP] = [cx + 0.05, cy + 0.10, 0.9]
    pose[H36Key.LKNEE] = [cx - 0.04, cy + 0.30, 0.9]
    pose[H36Key.RKNEE] = [cx + 0.04, cy + 0.30, 0.9]
    return pose.astype(np.float32)


def _stolen_pose(cx: float = 0.50, cy: float = 0.50) -> np.ndarray:
    """A DIFFERENT person's pose: same track id but a huge centroid jump +
    skeletal-ratio change (a clear steal by both AND-gate halves).

    Centroid moves ~0.5 in each axis (jump ~0.7 >> 0.15 threshold) and limb
    proportions differ (femur/tibia scaled) so ratio_change >> 0.25.
    """
    pose = _normal_pose(cx + 0.5, cy + 0.5)  # big centroid jump
    # Distort limb proportions so the skeletal-ratio half also triggers.
    pose[H36Key.LKNEE] = [cx + 0.5 - 0.20, cy + 0.5 + 0.50, 0.9]
    pose[H36Key.RKNEE] = [cx + 0.5 + 0.20, cy + 0.5 + 0.50, 0.9]
    return pose.astype(np.float32)


@pytest.fixture()
def extractor() -> PoseExtractor:
    """Construct a PoseExtractor WITHOUT loading the ONNX model.

    `PoseExtractor.__init__` builds PersonDetector and MogaNetBatch, which
    load ONNX weights and need CUDA. The bug is in `_fill_target_pose` — a
    pure-Python method that touches only `all_poses`, `track_state`, and the
    passed-in `validator`/loop-state. We bypass `__init__` via
    `__new__` and set only the attributes `_fill_target_pose` reads.
    """
    ext = PoseExtractor.__new__(PoseExtractor)
    # _fill_target_pose reads none of the heavy model attrs — it only uses
    # `self` to qualify the method. The validator and track_state are passed
    # in as args. So no model setup is needed.
    return ext


@pytest.fixture()
def track_state() -> TrackState:
    """A TrackState with target_track_id already pinned to 0.

    `_fill_target_pose` only reads `track_state.target_track_id` and calls
    `track_state.retroactive_fill` (the migration branch, unreachable while
    the bug is live). The tracker instances are NOT used by `_fill_target_pose`
    directly. Construct with the custom backend (Sports2DTracker) to match
    the production default; we never call update_tracking here.
    """
    ts = TrackState(fps=30.0, tracking_backend="custom", tracking_mode="auto")
    ts.target_track_id = 0
    return ts


# ---------------------------------------------------------------------------
# Bug — pass-by-value reassignment: caller's last_target_pose stays None
# ---------------------------------------------------------------------------


def test_fill_target_pose_mutates_caller_last_target_pose(extractor, track_state):
    """RED: after a valid frame-0 fill, the CALLER's `last_target_pose` must be
    non-None (so the next frame's `is_stolen` guard can run).

    Mirrors the `_extract_per_frame` / `_extract_batch` call site:
        last_target_pose = None
        ...
        self._fill_target_pose(all_poses, frame_idx, h36m_poses, track_ids,
                                track_state, validator,
                                last_target_pose, last_target_ratios,
                                target_lost_frame)
        # caller then uses last_target_pose on the NEXT iteration's guard

    Current code: `_fill_target_pose` reassigns the LOCAL `last_target_pose`
    (line :613) but returns None, so the caller's variable stays None. The
    next frame's guard `if last_target_pose is not None and
    validator.is_stolen(...)` (line :607) short-circuits to False every
    frame -> anti-steal is DEAD.

    Correct contract: either (a) the method mutates caller-visible state
    (impossible for a rebind in pure Python — ints/None are immutable, and
    the ndarray is reassigned not mutated in place), OR (b) the method
    RETURNS the updated state and the caller reassigns. It does neither.
    """
    num_frames = 2
    all_poses = np.full((num_frames, 17, 3), np.nan, dtype=np.float32)
    validator = TrackValidator()

    pose0 = _normal_pose()
    h36m_poses = pose0[None, ...]  # (1, 17, 3) — one person detected
    track_ids = [0]

    # Caller's loop state — EXACTLY as initialized in _extract_per_frame:282-284
    # and _extract_batch:416-418.
    last_target_pose: np.ndarray | None = None
    last_target_ratios: np.ndarray | None = None
    target_lost_frame: int | None = None

    extractor._fill_target_pose(
        all_poses,
        0,  # frame_idx
        h36m_poses,
        track_ids,
        track_state,
        validator,
        last_target_pose,
        last_target_ratios,
        target_lost_frame,
    )

    assert last_target_pose is not None, (
        "BUG: _fill_target_pose reassigns the LOCAL `last_target_pose` (line 613) "
        "but returns None — Python pass-by-value means the caller's variable "
        "stays None. On the next frame, the guard `if last_target_pose is not "
        "None and validator.is_stolen(...)` (line 607) short-circuits to False, "
        "so the TrackValidator anti-steal check (#451 / _track_validator.py) is "
        "DEAD CODE in both _extract_per_frame and _extract_batch. The fix must "
        "either return (last_target_pose, last_target_ratios, target_lost_frame) "
        "and have both callers reassign, OR move this state into a mutable "
        "object passed by reference."
    )


def test_fill_target_pose_returns_updated_state(extractor, track_state):
    """RED: alternative contract — if the method will NOT mutate caller state
    (pure Python rebind), it MUST return the updated state so callers can
    reassign.

    Current signature is `-> None` and there is no return statement, so the
    caller has no way to recover the updated `last_target_pose` /
    `last_target_ratios` / `target_lost_frame`.

    Asserts the method returns a non-None value (a tuple or object carrying
    the updated state). RED now: it returns None.
    """
    num_frames = 1
    all_poses = np.full((num_frames, 17, 3), np.nan, dtype=np.float32)
    validator = TrackValidator()
    pose0 = _normal_pose()
    h36m_poses = pose0[None, ...]
    track_ids = [0]

    result = extractor._fill_target_pose(
        all_poses,
        0,
        h36m_poses,
        track_ids,
        track_state,
        validator,
        None,
        None,
        None,
    )

    assert result is not None, (
        "BUG: _fill_target_pose returns None (signature `-> None`, no return "
        "statement). Since it cannot mutate the caller's rebound locals "
        "(pass-by-value), the ONLY way to propagate the updated tracking state "
        "is to RETURN it. It returns None, so the caller's last_target_pose / "
        "last_target_ratios / target_lost_frame are stuck at their initial "
        "values forever — the anti-steal guard (line 607) and the migration/"
        "recovery branch (lines 623-652) are both unreachable."
    )


# ---------------------------------------------------------------------------
# Consequence — a stolen pose is written VERBATIM (guard never fires)
# ---------------------------------------------------------------------------


def test_stolen_pose_is_written_verbatim_when_guard_is_dead(extractor, track_state):
    """RED: end-to-end consequence of the dead guard.

    Simulates two frames of the extraction loop:
      frame 0: normal target pose, track 0.
      frame 1: a STEAL — track 0 now carries a wildly different person (big
               centroid jump + skeletal ratio change). `is_stolen` would
               return True IF `last_target_pose` were set. But because of the
               pass-by-value bug, `last_target_pose` is still None at frame 1,
               so the guard `if last_target_pose is not None and
               validator.is_stolen(...)` short-circuits to False, and the
               stolen pose is written verbatim into all_poses[1].

    Correct behavior: all_poses[1] should be NaN (the steal detected and the
    frame blanked, line :620) — OR at minimum the guard must have been
    REACHED (last_target_pose non-None). RED now: all_poses[1] is the stolen
    pose verbatim (the guard was never reached).
    """
    num_frames = 2
    all_poses = np.full((num_frames, 17, 3), np.nan, dtype=np.float32)
    validator = TrackValidator()

    pose0 = _normal_pose()
    pose1 = _stolen_pose()  # clearly a different person under track 0

    # Sanity: pose1 IS a steal by both AND-gate halves — confirm independently
    # so a future change to is_stolen cannot make this test pass for the
    # wrong reason.
    ratios0 = compute_2d_skeletal_ratios(pose0)
    assert validator.is_stolen(pose1, pose0, ratios0) is True, (
        "test fixture broken: pose1 is not a clear steal by the validator. "
        "The repro requires is_stolen(pose1, pose0, ratios0) == True."
    )

    # ---- frame 0: normal fill ----
    last_target_pose: np.ndarray | None = None
    last_target_ratios: np.ndarray | None = None
    target_lost_frame: int | None = None

    extractor._fill_target_pose(
        all_poses,
        0,
        pose0[None, ...],
        [0],
        track_state,
        validator,
        last_target_pose,
        last_target_ratios,
        target_lost_frame,
    )
    # Caller's last_target_pose is STILL None (the bug) — the guard at frame 1
    # will short-circuit.
    assert last_target_pose is None, (
        "test setup invariant: caller's last_target_pose stays None after "
        "_fill_target_pose (the bug). If this fails, the bug is fixed and "
        "this test should be removed."
    )

    # ---- frame 1: a steal under the SAME track id ----
    extractor._fill_target_pose(
        all_poses,
        1,
        pose1[None, ...],
        [0],
        track_state,
        validator,
        last_target_pose,
        last_target_ratios,
        target_lost_frame,
    )

    # The CORRECT behavior: all_poses[1] is NaN (steal detected, frame blanked
    # at line :620). The BUGGY behavior: all_poses[1] is pose1 verbatim (the
    # guard short-circuited because last_target_pose was None, so line :612
    # wrote the stolen pose directly).
    frame1_xy = all_poses[1, :, :2]
    stolen_xy = pose1[:, :2]
    written_verbatim = np.allclose(frame1_xy, stolen_xy, equal_nan=True)

    assert not written_verbatim, (
        "BUG: stolen pose written VERBATIM into all_poses[1]. The anti-steal "
        "guard (line 607: `if last_target_pose is not None and "
        "validator.is_stolen(...)`) short-circuited to False because the "
        "caller's last_target_pose is still None (pass-by-value reassignment "
        "in _fill_target_pose did not propagate back). is_stolen was never "
        "called, so the clear steal (is_stolen(pose1, pose0, ratios0)==True, "
        "verified above) was missed, and the wrong-person pose was written "
        "verbatim. This is the exact skeleton-steal failure mode the "
        "CLAUDE.md Tracking Debugging Workflow exists to diagnose — and it "
        "goes UNDETECTED in both production extraction paths."
    )
