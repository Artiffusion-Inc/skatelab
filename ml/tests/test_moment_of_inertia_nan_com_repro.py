"""RED repro — `PhysicsEngine.calculate_moment_of_inertia` (PUBLIC) silently
NaN-poisons per-frame inertia via NaN keypoints feeding the radius `r`.

    com_trajectory = self.calculate_center_of_mass(poses_3d)   # NaN-guarded (#884)
    return self._calculate_moment_of_inertia_with_com(poses_3d, com_trajectory, axis)

`_calculate_moment_of_inertia_with_com` (physics_engine.py) builds per-frame
inertia `I = sum(m_i * r_i^2)` where `r_i = ||pos_i - com||` (axis-projected).
The CoM is NaN-guarded (#884 masks NaN-keypoint contributions to 0), BUT the
keypoint `pos_i` itself (e.g. `head`, `torso_pos = (spine + thorax)/2`) is
fed RAW into:

    offset = pos - com_trajectory       # NaN keypoint → NaN offset
    r = np.linalg.norm(offset, axis=1)  # NaN offset → NaN r
    inertia[:] += mass * r**2           # NaN + finite = NaN (in-place poison)

`inertia[:] += mass * r**2` is an in-place add: NaN + finite = NaN, and no
subsequent segment contribution can recover that frame. So ONE occluded
joint on a frame NaN-poisons the per-frame inertia for that frame (and only
that frame, since each frame's r is independent). The NaN then flows into
`calculate_angular_momentum` (`L = inertia * angular_velocity`) and any
caller that averages inertia → `avg_inertia = nan` in report JSON.

Sibling family: #919 `_with_com` (covered by `test_avg_inertia_nan_joint_leak`),
#884 `calculate_center_of_mass` (NaN-masked), #994 `calculate_com_trajectory_3d`
(geometry.py `_w` mask). This repro covers the PUBLIC
`calculate_moment_of_inertia` path's own NaN-keypoint leak in
`add_segment_inertia` — a single occluded joint must NOT NaN-poison that
frame's inertia.

The fix (NOT applied — repro only): mirror the `_w` pattern from #884/#994
in `add_segment_inertia` — mask each segment's `mass * r**2` contribution to
0 on frames where `r` is non-finite (`np.where(np.isfinite(r), mass * r**2,
0.0)`). All-valid case is byte-identical. No renormalization — same contract
as the CoM path.

Pure-Python (no GPU, no DB): `calculate_moment_of_inertia` and
`_calculate_moment_of_inertia_with_com` are pure-data functions over a poses
array.
"""

import inspect

import numpy as np

from src.analysis.physics_engine import PhysicsEngine
from src.types import H36Key


def _standing_pose_3d(nan_keypoint: str | None = None, n: int = 8) -> np.ndarray:
    """An `n`-frame 3D pose sequence in a neutral standing pose. All keypoints
    at biomechanically-plausible positions (meters). When `nan_keypoint` is
    set, that keypoint is NaN on frame 3 only — the occlusion case for
    `add_segment_inertia`."""
    poses = np.zeros((n, 17, 3), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.HEAD] = [0.0, 1.5, 0.0]
        poses[f, H36Key.SPINE] = [0.0, 1.0, 0.0]
        poses[f, H36Key.THORAX] = [0.0, 1.2, 0.0]
        poses[f, H36Key.LSHOULDER] = [-0.2, 1.3, 0.0]
        poses[f, H36Key.LELBOW] = [-0.3, 1.1, 0.0]
        poses[f, H36Key.LWRIST] = [-0.35, 0.9, 0.0]
        poses[f, H36Key.RSHOULDER] = [0.2, 1.3, 0.0]
        poses[f, H36Key.RELBOW] = [0.3, 1.1, 0.0]
        poses[f, H36Key.RWRIST] = [0.35, 0.9, 0.0]
        poses[f, H36Key.LHIP] = [-0.1, 0.9, 0.0]
        poses[f, H36Key.LKNEE] = [-0.1, 0.5, 0.0]
        poses[f, H36Key.LFOOT] = [-0.1, 0.0, 0.0]
        poses[f, H36Key.RHIP] = [0.1, 0.9, 0.0]
        poses[f, H36Key.RKNEE] = [0.1, 0.5, 0.0]
        poses[f, H36Key.RFOOT] = [0.1, 0.0, 0.0]
    if nan_keypoint:
        kp = {
            "rknee": H36Key.RKNEE,
            "rwrist": H36Key.RWRIST,
            "lfoot": H36Key.LFOOT,
            "head": H36Key.HEAD,
        }[nan_keypoint]
        poses[3, kp] = [np.nan, np.nan, np.nan]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: a NaN keypoint on one frame must NOT NaN-poison that frame's
# per-frame inertia.
# --------------------------------------------------------------------------- #


def test_nan_knee_moment_of_inertia_per_frame_finite_repro():
    """CORRECT behavior: PUBLIC `calculate_moment_of_inertia` with ONE NaN
    RKNEE on frame 3 must return a per-frame inertia array that is FINITE on
    frame 3 — the NaN-keypoint's contribution to that frame is masked to 0
    (its mass is simply absent for that frame, same contract as the CoM
    `_w` mask). The other frames must equal the all-valid inertia.

    RED now: RKNEE NaN on frame 3 → in `_calculate_moment_of_inertia_with_com`
    `add_segment_inertia`, the leg segments use `r_thigh=(r_hip+r_knee)/2`
    and `r_shin=(r_knee+r_foot)/2`; `r_knee` NaN → these midpoints NaN →
    `offset = pos - com` NaN → `r = ||offset||` NaN →
    `inertia[:] += mass * r**2` poisons inertia[3] in-place (NaN + finite =
    NaN). After the fix: the NaN-keypoint contribution is masked to 0 on
    frame 3, inertia[3] is finite (close to all-valid — only the leg mass
    is absent).
    """
    engine = PhysicsEngine()

    poses_valid = _standing_pose_3d(None)
    poses_nan = _standing_pose_3d("rknee")

    inertia_valid = engine.calculate_moment_of_inertia(poses_valid, axis="vertical")
    inertia_nan = engine.calculate_moment_of_inertia(poses_nan, axis="vertical")

    # Frame 3 must be FINITE — no NaN-leak from the occluded knee.
    assert np.isfinite(inertia_nan[3]), (
        f"BUG: calculate_moment_of_inertia returned inertia[3]="
        f"{inertia_nan[3]} (nan) for a pose with a NaN RKNEE on frame 3. "
        f"`add_segment_inertia` does `offset = pos - com; r = ||offset||; "
        f"inertia[:] += mass * r**2` with no NaN guard, so a NaN keypoint "
        f"poisons r → NaN + finite = NaN in-place. NaN then flows into "
        f"calculate_angular_momentum and avg_inertia in report JSON. "
        f"(Sanity: all-valid inertia[3] = {inertia_valid[3]:.4f}.)"
    )

    # Frames without the occlusion must be byte-identical to the all-valid
    # inertia (the guard is a no-op on finite frames).
    other = [i for i in range(len(inertia_valid)) if i != 3]
    np.testing.assert_array_equal(
        inertia_nan[other],
        inertia_valid[other],
        err_msg=(
            "BUG: NaN guard changed inertia on frames WITHOUT the occlusion. "
            "The guard must be a no-op on all-finite frames "
            "(np.where(isfinite, term, 0.0) == term when finite)."
        ),
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint, not just the knee.
# --------------------------------------------------------------------------- #


def test_nan_wrist_moment_of_inertia_per_frame_finite_repro():
    """CORRECT behavior: a NaN RWRIST on frame 3 must also yield a FINITE
    inertia[3]. The arm segments use `r_forearm = (r_elbow + r_wrist)/2` and
    `r_wrist` directly as `r_hand`, so a NaN wrist poisons r the same way.
    Wide blast radius — ANY keypoint.

    RED now: RWRIST NaN → r_forearm/hand NaN → inertia[3] = NaN. After the
    fix: graceful degradation on any occluded keypoint.
    """
    engine = PhysicsEngine()
    inertia_nan = engine.calculate_moment_of_inertia(_standing_pose_3d("rwrist"), axis="vertical")
    assert np.isfinite(inertia_nan[3]), (
        f"BUG: calculate_moment_of_inertia returned inertia[3]={inertia_nan[3]} "
        f"(nan) for a pose with a NaN RWRIST on frame 3. The arm segments "
        f"(r_forearm = (RELBOW + RWRIST)/2, r_hand = RWRIST) feed `r` raw, so "
        f"a NaN wrist poisons inertia[3] the same way as a NaN knee. The bug "
        f"has a wide blast radius — ANY keypoint, not just the legs."
    )


# --------------------------------------------------------------------------- #
# Observable 3: symmetry — occluding LKNEE vs RKNEE gives equal inertia[3].
# --------------------------------------------------------------------------- #


def test_nan_knee_moment_of_inertia_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE on frame 3 must give equal
    inertia[3] — both poison the same mass set (one thigh + one shin + one
    foot) by symmetry of the segment-mass table.

    RED now: both NaN (symmetric today, both leak). After the fix: both
    finite and equal — locks the symmetry contract so a one-sided fix fails.
    """
    engine = PhysicsEngine()
    poses_r = _standing_pose_3d("rknee")
    poses_l = _standing_pose_3d(None)
    poses_l[3, H36Key.LKNEE] = [np.nan, np.nan, np.nan]

    inertia_r = engine.calculate_moment_of_inertia(poses_r, axis="vertical")
    inertia_l = engine.calculate_moment_of_inertia(poses_l, axis="vertical")

    assert np.isfinite(inertia_r[3]) and np.isfinite(inertia_l[3]), (
        f"BUG (symmetry): occluding LKNEE/RKNEE gives non-finite inertia[3] "
        f"({inertia_l[3]} vs {inertia_r[3]}). Both must be finite before the "
        f"symmetry contract can be checked."
    )
    assert abs(inertia_r[3] - inertia_l[3]) < 1e-5, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different inertia[3] "
        f"({inertia_l[3]:.6f} vs {inertia_r[3]:.6f}). The segment-mass table is "
        f"left/right symmetric, so the masked contribution must be equal."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid input unchanged.
# --------------------------------------------------------------------------- #


def test_all_valid_moment_of_inertia_unchanged_repro():
    """Regression guard: an all-valid pose must return a FINITE, NON-NEGATIVE
    per-frame inertia. The fix (NaN-mask in `add_segment_inertia`) must not
    change the no-NaN case.

    PASSES today; locks the contract so the NaN-aware fix cannot regress the
    all-valid case.
    """
    engine = PhysicsEngine()
    inertia = engine.calculate_moment_of_inertia(_standing_pose_3d(None), axis="vertical")
    assert np.all(np.isfinite(inertia)), (
        f"BUG (regression): all-valid pose returned non-finite inertia {inertia}."
    )
    assert np.all(inertia >= 0.0), (
        f"BUG (regression): all-valid pose returned negative inertia {inertia} "
        f"(I = sum m*r^2 >= 0)."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — add_segment_inertia masks NaN r.
# --------------------------------------------------------------------------- #


def test_calculate_moment_of_inertia_nan_guard_source_repro():
    """GREEN contract source check: the NaN-keypoint leak in
    `_calculate_moment_of_inertia_with_com`'s `add_segment_inertia` is fixed
    — each segment's `mass * r**2` contribution is masked to 0 on frames
    where `r` is non-finite (mirrors the #884/#994 `_w` pattern). The guard
    is in the shared `_with_com` helper, so both the PUBLIC
    `calculate_moment_of_inertia` and `analyze` paths are covered.
    """
    src = inspect.getsource(PhysicsEngine._calculate_moment_of_inertia_with_com)
    assert "np.isfinite" in src, (
        "BUG: _calculate_moment_of_inertia_with_com must guard NaN in "
        "`add_segment_inertia` (np.isfinite on r) so a NaN keypoint cannot "
        "poison per-frame inertia (#980)."
    )
