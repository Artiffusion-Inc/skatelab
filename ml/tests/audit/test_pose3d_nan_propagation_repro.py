"""RED repro — Pose3DNormalizer NaN-foot poisons frame + coco_to_h36m HEAD NaN-eye bypass.

Two confirmed bugs (scout-verified, RED against current code):

BUG A — Pose3DNormalizer one NaN foot poisons entire frame via min():
    ml/src/pose_3d/normalizer_3d.py:70-75
        lowest_foot = min(left_foot_y, right_foot_y)   # Python min() — NaN
        body_height = head_y - lowest_foot             # NaN propagates
        scale = 1.0 if body_height < 0.1 else self._target_height / body_height
            # NaN < 0.1 is False → scale = NaN (degenerate-guard misses NaN)
        normalized[frame_idx] = centered * scale       # entire frame × NaN = all-NaN
    One NaN foot/head y-coordinate → body_height=NaN → scale=NaN → ALL 17 joints
    of that frame become NaN (even valid joints). calculate_body_heights
    (normalizer_3d.py:167-172) uses np.minimum — same root cause (NaN if either).

BUG B — coco_to_h36m HEAD eye-midpoint no NaN-coord guard:
    ml/src/pose_estimation/h36m.py:196-204 (single) + :282-287 (batch)
        if eye_conf_ok:  # checks CONFIDENCE channel only (>=0.3)
            head_pos = (left_eye[:2] + right_eye[:2]) / 2  # NaN coords (high conf) → NaN
    A detector glitch returning NaN xy coords WITH confidence >= 0.3 bypasses
    the confidence gate and poisons HEAD. Hip/shoulder midpoints use
    _finite_midpoint (finiteness guard) — HEAD eye-midpoint was NOT given that
    guard. Same bug-class as #451.

The bugs STACK: NaN eye (B) → NaN HEAD → NaN body_height (A) → NaN scale →
    all-NaN frame.

Tests stay RED until production code is fixed. Do NOT fix production code.
"""

import numpy as np

from src.pose_3d.normalizer_3d import Pose3DNormalizer
from src.pose_estimation.h36m import coco_to_h36m, coco_to_h36m_batch
from src.types import H36Key

# ---------------------------------------------------------------------------
# BUG A — Pose3DNormalizer: one NaN foot poisons entire 17-joint frame
# ---------------------------------------------------------------------------


def test_bug_a_one_nan_foot_poisons_entire_frame():
    """RED: LFOOT.y=NaN makes LSHOULDER (a valid joint) NaN via min(NaN) → NaN scale.

    Root cause: normalizer_3d.py:70 `lowest_foot = min(left_foot_y, right_foot_y)`.
    Python's built-in `min(a, b)` propagates NaN in an arg-order-dependent way:
    `min` compares `a < b`; when that comparison involves NaN it returns False,
    so `min` falls through to returning `b`. Thus `min(np.nan, 0.0)` returns
    `nan` (NaN<0.0 is False → return second arg... actually returns first when
    second is not less), while `min(0.0, np.nan)` returns `0.0`. Either way the
    guard is unreliable: for `min(left_foot_y, right_foot_y)` with
    left_foot_y=NaN the result is NaN. body_height = head_y - NaN = NaN. The
    degenerate-guard `scale = 1.0 if body_height < 0.1 else ...` does NOT catch
    NaN because `NaN < 0.1` is False, so scale becomes `target_height / NaN =
    NaN`. `centered * NaN` = all 17 joints of the frame become NaN — even the
    perfectly valid LSHOULDER.

    Note: the bug is arg-order-dependent (a separate defect — relying on
    Python `min` for numeric NaN-safety is wrong regardless of which arg is
    NaN; the fix must use `np.nanmin`/`np.fmin`). We exercise the LFOOT=NaN
    orientation which deterministically REDs; RFOOT=NaN happens to slip past
    `min` for this arg order but is equally a latent instance of the bug
    (swap the foot that occludes and the frame dies).
    """
    pose = np.zeros((1, 17, 3), dtype=np.float32)
    pose[0, H36Key.HEAD, 1] = 1.7
    pose[0, H36Key.LFOOT, 1] = np.nan  # left foot missing (deterministic RED)
    pose[0, H36Key.RFOOT, 1] = 0.0
    pose[0, H36Key.LSHOULDER] = [0.1, 1.5, 0.0]  # a valid joint

    out = Pose3DNormalizer().normalize(pose)

    assert np.isfinite(out[0, H36Key.LSHOULDER]).all(), (
        "BUG A: one missing foot (LFOOT.y=NaN) poisons all 17 joints — "
        "min(NaN,0.0)=NaN → body_height=NaN → scale=NaN (NaN<0.1 is False, "
        "guard misses NaN) → centered*NaN = all-NaN frame. A single dropped "
        f"keypoint zeroes the entire frame's 3D pose. "
        f"LSHOULDER={out[0, H36Key.LSHOULDER]}"
    )


def test_bug_a_one_nan_head_poisons_entire_frame():
    """RED: HEAD.y=NaN makes LSHOULDER (a valid joint) NaN via NaN body_height.

    The same `min()`/`<0.1`-guard defect also fires when HEAD is the NaN joint
    (head_y=NaN → body_height=NaN regardless of feet). Confirms the guard
    failure is not foot-specific.
    """
    pose = np.zeros((1, 17, 3), dtype=np.float32)
    pose[0, H36Key.HEAD, 1] = np.nan  # head missing
    pose[0, H36Key.LFOOT, 1] = 0.0
    pose[0, H36Key.RFOOT, 1] = 0.0
    pose[0, H36Key.LSHOULDER] = [0.1, 1.5, 0.0]

    out = Pose3DNormalizer().normalize(pose)

    assert np.isfinite(out[0, H36Key.LSHOULDER]).all(), (
        "BUG A: NaN head (HEAD.y=NaN) poisons all 17 joints — body_height=NaN "
        "→ scale=NaN (NaN<0.1 is False, guard misses NaN) → centered*NaN = "
        f"all-NaN frame. LSHOULDER={out[0, H36Key.LSHOULDER]}"
    )


# ---------------------------------------------------------------------------
# BUG B — coco_to_h36m HEAD eye-midpoint: NaN-coords-with-high-conf bypass
# ---------------------------------------------------------------------------


def test_bug_b_nan_eye_coords_high_conf_poisons_head_single():
    """RED: NaN eye xy coords with conf>=0.3 bypass confidence gate → HEAD=NaN.

    Root cause: h36m.py:192-204. `eye_conf_ok = left_eye[2] >= 0.3 and
    right_eye[2] >= 0.3` checks the CONFIDENCE channel only. A detector glitch
    can return NaN xy coordinates WITH high confidence (0.8 >= 0.3), so
    `eye_conf_ok=True` and `head_pos = (NaN + valid) / 2 = NaN`. The
    hip/shoulder midpoints were guarded with _finite_midpoint (finiteness
    gate) but the HEAD eye-midpoint was not. Same bug-class as #451.
    """
    coco = np.zeros((17, 3), dtype=np.float32)
    coco[5] = [100, 100, 0.9]  # LEFT_SHOULDER
    coco[6] = [110, 100, 0.9]  # RIGHT_SHOULDER
    coco[11] = [100, 150, 0.9]  # LEFT_HIP
    coco[12] = [110, 150, 0.9]  # RIGHT_HIP
    coco[0] = [105, 80, 0.9]  # NOSE
    coco[1] = [np.nan, np.nan, 0.8]  # LEFT_EYE: NaN xy, HIGH conf (bypasses gate)
    coco[2] = [108, 78, 0.8]  # RIGHT_EYE: valid

    h = coco_to_h36m(coco)

    assert np.isfinite(h[H36Key.HEAD.value, :2]).all(), (
        "BUG B (single): NaN eye coords with conf>=0.3 bypass the confidence "
        "gate (eye_conf_ok=True) and poison HEAD via (NaN+valid)/2=NaN. The "
        "hip/shoulder midpoints use _finite_midpoint (finiteness guard); the "
        "HEAD eye-midpoint was not given that guard. Same class as #451. "
        f"HEAD={h[H36Key.HEAD.value]}"
    )


def test_bug_b_nan_eye_coords_high_conf_poisons_head_batch():
    """RED: batch path of BUG B — coco_to_h36m_batch has the same eye-conf-only gate.

    Root cause: h36m.py:276-287. `eye_conf_ok = (left_eye[:, 2] >= 0.3) &
    (right_eye[:, 2] >= 0.3)` — confidence-only gate, no finiteness check on xy.
    Frames with NaN eye xy + high conf flow into `head_pos = (NaN + valid)/2`.
    """
    coco = np.zeros((17, 3), dtype=np.float32)
    coco[5] = [100, 100, 0.9]
    coco[6] = [110, 100, 0.9]
    coco[11] = [100, 150, 0.9]
    coco[12] = [110, 150, 0.9]
    coco[0] = [105, 80, 0.9]
    coco[1] = [np.nan, np.nan, 0.8]  # LEFT_EYE NaN xy, high conf
    coco[2] = [108, 78, 0.8]

    hb = coco_to_h36m_batch(np.stack([coco, coco.copy()]))

    assert np.isfinite(hb[:, H36Key.HEAD.value, :2]).all(), (
        "BUG B (batch): NaN eye coords with conf>=0.3 bypass the per-frame "
        "confidence gate in coco_to_h36m_batch and poison HEAD. "
        f"HEAD frames={hb[:, H36Key.HEAD.value]}"
    )
