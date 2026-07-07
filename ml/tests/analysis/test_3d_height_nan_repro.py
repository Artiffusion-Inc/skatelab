"""Regression guard — 3D body-height foot/head NaN-arg-order family (#1313).

`ml/src/pose_3d/normalizer_3d.py` has three sites that compute body height from
LFOOT/RFOOT/HEAD y-coordinates:

    normalize (line 73)             — per-frame scale
    get_body_height (line 109)      — average across frames
    calculate_body_heights (line 182) — vectorized per-frame

The pre-fix bug class was Python `min(left_foot_y, right_foot_y)`:
arg-order-dependent NaN-unsafe (`min(NaN, val) = NaN`, `min(val, NaN) = val`).
Fix: `np.fmin` (NaN-safe — finite operand wins) + `np.isfinite` guard at every
site so a single occluded foot falls back to the finite foot, and both-NaN-foot
frames degenerate to the documented default (1.7 / scale=1.0) instead of
propagating NaN.

This file locks the post-fix contract (#861, #454) with explicit NaN tests at
each of the three sites. Tests pass on master (the fix is in place) and serve
as a regression guard if anyone reverts the contract.

Family: NaN-tranche via Python `min` (vs `np.fmin`) on NaN body part. Mirror of
#962/#915 NaN-tranche family. See `audit/test_body_height_nan_foot_repro.py`
for the historical RED/REPRO coverage and `test_get_body_height_nan_repro.py`
for the per-method regression guard on `get_body_height`.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.pose_3d.normalizer_3d import Pose3DNormalizer, calculate_body_heights
from src.types import H36Key


def _frame(
    left_foot_y: float,
    right_foot_y: float,
    head_y: float,
    *,
    hip_center: tuple[float, float, float] = (0.0, 0.9, 0.0),
) -> np.ndarray:
    """A single (17, 3) H3.6M frame with controllable foot/head y. Other kp=0."""
    frame = np.zeros((17, 3), dtype=np.float32)
    frame[H36Key.LFOOT] = [0.0, left_foot_y, 0.0]
    frame[H36Key.RFOOT] = [0.0, right_foot_y, 0.0]
    frame[H36Key.HEAD] = [0.0, head_y, 0.0]
    frame[H36Key.HIP_CENTER] = list(hip_center)
    return frame


# ---------------------------------------------------------------------------
# 1. get_body_height: one-NaN-foot must not poison the average.
# ---------------------------------------------------------------------------


def test_get_body_height_one_nan_foot_falls_back_to_finite():
    """Contract: a frame with one NaN foot must NOT be silently dropped or
    poison the average. `np.fmin(NaN, finite) = finite` keeps the frame, so
    the average stays finite. Symmetric for LFOOT and RFOOT (no asymmetry).
    """
    norm = Pose3DNormalizer(target_height=1.7)
    f0 = _frame(left_foot_y=0.0, right_foot_y=0.0, head_y=1.5)
    f1 = _frame(left_foot_y=float("nan"), right_foot_y=0.0, head_y=1.9)
    poses_3d = np.stack([f0, f1], axis=0)
    result = norm.get_body_height(poses_3d)
    assert np.isfinite(result), (
        f"#1313: get_body_height={result} (NaN) — LFOOT-NaN frame poisoned "
        f"body_height via head - NaN = NaN. Use np.fmin + np.isfinite guard."
    )
    assert abs(result - 1.7) < 1e-6, (
        f"#1313: get_body_height={result} — LFOOT-NaN frame must be kept "
        f"via np.fmin fallback (not dropped). Expected 1.7 = mean of (1.5, 1.9)."
    )


# ---------------------------------------------------------------------------
# 2. get_body_height: both-NaN-foot must fall to 1.7 default (no NaN leak).
# ---------------------------------------------------------------------------


def test_get_body_height_both_nan_feet_returns_default():
    """Contract: both feet NaN — no finite foot to fall back to → drop frame →
    return 1.7 default (NOT NaN). The drop must be INTENTIONAL via
    `np.isfinite`, not a side-effect of bare `min` arg-order semantics.
    """
    norm = Pose3DNormalizer(target_height=1.7)
    f0 = _frame(left_foot_y=0.0, right_foot_y=0.0, head_y=1.7)  # finite baseline
    f1 = _frame(left_foot_y=float("nan"), right_foot_y=float("nan"), head_y=1.7)
    poses_3d = np.stack([f0, f1], axis=0)
    result = norm.get_body_height(poses_3d)
    # f0 is kept (body_height=1.7), f1 is dropped (NaN body_height) — mean = 1.7.
    assert np.isfinite(result), (
        f"#1313: get_body_height={result} (NaN) — both-NaN-feet frame leaked "
        f"NaN into the average. Use np.isfinite guard to drop the frame."
    )
    assert abs(result - 1.7) < 1e-6, (
        f"#1313: get_body_height={result} — expected 1.7 (f0 kept, f1 dropped). "
        f"The fix must drop both-NaN-feet frames via np.isfinite, not silently "
        f"include them via bare min arg-order."
    )


# ---------------------------------------------------------------------------
# 3. calculate_body_heights: vectorized per-frame heights must use np.fmin
#    (not bare min) so a single occluded foot does not poison the whole
#    frame's body_height entry.
# ---------------------------------------------------------------------------


def test_calculate_body_heights_one_nan_foot_returns_finite():
    """Contract: `calculate_body_heights` (the vectorized sibling of
    `get_body_height`) must use `np.fmin` (NaN-safe) so a single occluded foot
    in any frame produces a FINITE body_height for that frame (the finite
    foot wins). A bare `min` would produce NaN for `min(NaN, val)` arg order
    and silently poison the downstream scale (the parent of
    `calculate_body_heights` is a vectorized consumer chain).
    """
    f0 = _frame(left_foot_y=0.0, right_foot_y=0.0, head_y=1.5)
    f1 = _frame(left_foot_y=float("nan"), right_foot_y=0.0, head_y=1.9)
    f2 = _frame(left_foot_y=0.0, right_foot_y=float("nan"), head_y=1.7)
    poses_3d = np.stack([f0, f1, f2], axis=0)
    heights = calculate_body_heights(poses_3d)
    # f0=1.5, f1=1.9 (RFOOT finite), f2=1.7 (LFOOT finite).
    assert np.all(np.isfinite(heights)), (
        f"#1313: calculate_body_heights={heights} has NaN — np.fmin missing. "
        f"A single occluded foot in any frame must fall back to the finite "
        f"foot via np.fmin (NaN-safe), not poison body_height via bare min."
    )
    assert abs(heights[0] - 1.5) < 1e-6
    assert abs(heights[1] - 1.9) < 1e-6
    assert abs(heights[2] - 1.7) < 1e-6


# ---------------------------------------------------------------------------
# 4. normalize: a single occluded foot must NOT poison the whole frame's
#    17-joint output. Per-frame scale must be finite (fall back to scale=1.0
#    via the np.isfinite guard, not NaN).
# ---------------------------------------------------------------------------


def test_normalize_one_nan_foot_does_not_poison_valid_joints():
    """Contract: `normalize` (per-frame scale) must guard `np.isfinite` on
    body_height. A NaN body_height (one or both feet occluded) must fall back
    to `scale=1.0` (no rescaling) instead of `scale=NaN` (which would
    `centered * NaN` = all-NaN frame, even valid joints). The fix is
    `np.fmin` + `np.isfinite` on the body_height branch.

    A pre-fix bare `min(NaN, 0.0) = NaN` → `body_height = NaN` → `NaN < 0.1`
    is False (NaN-blind guard) → `scale = target/NaN = NaN` → every
    `centered * NaN = NaN` joint, including the perfectly valid LSHOULDER.
    A post-fix `np.fmin(NaN, 0.0) = 0.0` → `body_height = head - 0.0 = 1.7`
    → finite → `scale = target/1.7 = 1.0` (matches) → LSHOULDER survives.
    """
    pose = np.zeros((1, 17, 3), dtype=np.float32)
    pose[0, H36Key.HEAD, 1] = 1.7
    pose[0, H36Key.LFOOT, 1] = float("nan")  # left foot missing
    pose[0, H36Key.RFOOT, 1] = 0.0
    pose[0, H36Key.LSHOULDER] = [0.1, 1.5, 0.0]  # a valid joint — must survive
    pose[0, H36Key.HIP_CENTER] = [0.0, 0.9, 0.0]

    out = Pose3DNormalizer().normalize(pose)

    # LSHOULDER (a finite input) must remain finite in the output. If normalize
    # is buggy, scale=NaN poisons the whole frame and LSHOULDER goes NaN.
    assert np.all(np.isfinite(out[0, H36Key.LSHOULDER])), (
        f"#1313: normalize() poisoned LSHOULDER (a valid joint) with NaN — "
        f"LFOOT-NaN → body_height=NaN → scale=NaN (NaN<0.1 is False, guard "
        f"misses NaN) → centered*NaN = all-NaN frame. Use np.fmin (NaN-safe "
        f"foot selection) + np.isfinite guard so a single occluded foot falls "
        f"back to scale=1.0. LSHOULDER={out[0, H36Key.LSHOULDER]}"
    )


# ---------------------------------------------------------------------------
# 5. Source check: the three sites in normalizer_3d.py must use np.fmin
#    (not bare min) and an np.isfinite guard on body_height. Locks the root
#    cause — if anyone reverts the fix, this test fails.
# ---------------------------------------------------------------------------


def test_normalizer_3d_uses_nan_safe_min_and_isfinite_guard_source():
    """Contract: the three foot-min sites in `normalizer_3d.py` must use
    `np.fmin` (NaN-safe) and guard with `np.isfinite`. The bare NaN-unsafe
    `min(left_foot_y, right_foot_y)` pattern must NOT appear. The bare
    `min(right_foot_y, left_foot_y)` (swapped arg order) must also NOT appear
    — symmetry in either order means the same bug class.
    """
    src = inspect.getsource(Pose3DNormalizer)
    module_src = inspect.getsource(
        __import__("src.pose_3d.normalizer_3d", fromlist=["calculate_body_heights"])
    )

    # NaN-unsafe patterns: bare `min(left_foot_y,` (Python's min, not np.fmin).
    # `np.fmin(left_foot_y,` is fine — fmin shadows the substring.
    for label, body in (("class", src), ("module", module_src)):
        assert "= min(left_foot_y" not in body, (
            f"#1313: NaN-unsafe `min(left_foot_y, right_foot_y)` is back in "
            f"{label} — min(NaN, val) = NaN silently drops LFOOT-NaN frames. "
            f"Use np.fmin (NaN-safe) + np.isfinite guard."
        )
        assert "= min(right_foot_y" not in body, (
            f"#1313: NaN-unsafe `min(right_foot_y, left_foot_y)` is back in "
            f"{label} — arg-order-swapped min still NaN-unsafe. Use np.fmin."
        )
        # Must contain a NaN-safe min: either np.fmin or np.nanmin.
        assert "np.fmin" in body or "np.nanmin" in body, (
            f"#1313: {label} must use a NaN-safe min (np.fmin or np.nanmin) "
            f"on foot pairs — bare Python min is NaN-arg-order-dependent."
        )
        # Must contain a finiteness guard on body_height.
        assert "np.isfinite" in body, (
            f"#1313: {label} must guard body_height with np.isfinite — "
            f"`body_height < 0.1` is NaN-blind (NaN<0.1 is False, lets NaN "
            f"through to scale = target/NaN = NaN)."
        )
