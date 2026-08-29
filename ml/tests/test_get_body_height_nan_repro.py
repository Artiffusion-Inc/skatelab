"""RED repro — `Pose3DNormalizer.get_body_height` (ml/src/pose_3d/normalizer_3d.py:86-114).

Family: NaN-tranche via Python `min` (vs `np.fmin`) on NaN body part. Mirror of
#962/#915 NaN-tranche family. The companion function `normalize` (line 73)
correctly uses `np.fmin` (NaN-safe — falls back to the finite value) and has a
comment citing #454. `get_body_height` was missed — Python's `min(nan, val) = nan`
(arg-order-dependent) silently dropped frames with a NaN foot, biasing the
average toward the tracker's failure side.

Contract (GREEN — fix is in place on master via #861):
  - `get_body_height` must return FINITE (not NaN) for any pose with at most
    ONE NaN foot. A NaN foot must fall back to the finite foot via `np.fmin`
    (or `np.nanmin`/`np.isfinite` guard), not silently drop the frame.
  - Source check: `get_body_height` must contain `np.fmin` (or `nanmin` +
    `isfinite`) and must NOT contain the NaN-unsafe `min(left_foot_y,`
    pattern. The companion `normalize` must still use `np.fmin`.
  - All-valid pose must still return the mean of frame body heights.
  - All-NaN-foot frames still drop to the 1.7 default (no finite foot to fall
    back to).

This test file is the regression guard. If anyone reverts the fix (drops
`np.fmin` back to bare `min`), these tests will fail. Currently GREEN on
master — see audit/test_body_height_nan_foot_repro.py for the historical
REPRO/RED-observable coverage.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.pose_3d.normalizer_3d import Pose3DNormalizer
from src.types import H36Key


def _frame(left_foot_y: float, right_foot_y: float, head_y: float) -> np.ndarray:
    """A single (17, 3) H3.6M frame with controllable foot/head y. Other kp=0."""
    frame = np.zeros((17, 3), dtype=np.float32)
    frame[H36Key.LFOOT] = [0.0, left_foot_y, 0.0]
    frame[H36Key.RFOOT] = [0.0, right_foot_y, 0.0]
    frame[H36Key.HEAD] = [0.0, head_y, 0.0]
    frame[H36Key.HIP_CENTER] = [0.0, 0.9, 0.0]
    return frame


def test_get_body_height_nan_left_foot_returns_finite():
    """One NaN LFOOT (first arg) must not silently drop the frame.

    Pre-fix: `min(NaN, 0.0) = NaN` (first-arg-wins) → `body_height = head - NaN
    = NaN` → `NaN > 0.1` is False → frame dropped. With 2 frames (f0 all-valid,
    f1 LFOOT-NaN), f1 dropped → mean of f0 only (1.5) ≠ true mean (1.7).

    Post-fix: `np.fmin(NaN, 0.0) = 0.0` (NaN-safe fallback) → body_height
    finite for both frames → mean = (1.5 + 1.9) / 2 = 1.7.
    """
    normalizer = Pose3DNormalizer(target_height=1.7)
    f0 = _frame(left_foot_y=0.0, right_foot_y=0.0, head_y=1.5)
    f1 = _frame(left_foot_y=float("nan"), right_foot_y=0.0, head_y=1.9)
    poses_3d = np.stack([f0, f1], axis=0)
    result = normalizer.get_body_height(poses_3d)
    assert np.isfinite(result), (
        f"#1050 RED: get_body_height={result} is NaN/inf — bare min(NaN, x) "
        f"poisoned body_height via head - NaN = NaN. Use np.fmin/nanmin + "
        f"np.isfinite guard to fall back to the finite foot."
    )
    assert abs(result - 1.7) < 1e-6, (
        f"#1050 RED: get_body_height={result} — LFOOT-NaN frame was silently "
        f"dropped (NaN-blind `body_height > 0.1` guard). Expected 1.7 = mean "
        f"of (1.5, 1.9) when frame 1 is kept via np.fmin fallback."
    )


def test_get_body_height_nan_right_foot_returns_finite():
    """One NaN RFOOT (second arg) must not poison body_height.

    Even though `min(val, NaN) = val` (first-arg-wins) — the bug is intermittent
    for RFOOT — the frame must still be kept via np.fmin. With asymmetric feet
    (LFOOT=0.0, RFOOT=NaN), the fallback to the finite foot must produce
    a finite body_height, not silently truncate the average.
    """
    normalizer = Pose3DNormalizer(target_height=1.7)
    f0 = _frame(left_foot_y=0.0, right_foot_y=0.0, head_y=1.5)
    f1 = _frame(left_foot_y=0.0, right_foot_y=float("nan"), head_y=1.9)
    poses_3d = np.stack([f0, f1], axis=0)
    result = normalizer.get_body_height(poses_3d)
    assert np.isfinite(result), (
        f"#1050 RED: get_body_height={result} is NaN/inf — RFOOT-NaN poisoned "
        f"body_height. Symmetric guard required (both LFOOT and RFOOT NaN must "
        f"fall back to the finite foot)."
    )
    assert abs(result - 1.7) < 1e-6, (
        f"#1050 RED: get_body_height={result} — expected 1.7 (mean of f0=1.5 "
        f"and f1=1.9 with RFOOT-NaN frame kept via np.fmin fallback)."
    )


def test_get_body_height_all_finite_unchanged():
    """Regression guard — all-finite pose must return the mean of frame
    body_heights. The fix (np.fmin) must not change the no-NaN case.
    """
    normalizer = Pose3DNormalizer(target_height=1.7)
    f0 = _frame(left_foot_y=0.0, right_foot_y=0.0, head_y=1.5)
    f1 = _frame(left_foot_y=0.0, right_foot_y=0.0, head_y=1.9)
    poses_3d = np.stack([f0, f1], axis=0)
    result = normalizer.get_body_height(poses_3d)
    assert np.isfinite(result), (
        f"REGRESSION: get_body_height(all_finite) = {result} — must be finite."
    )
    assert abs(result - 1.7) < 1e-6, (
        f"REGRESSION: get_body_height(all_finite) = {result} — expected 1.7 = mean of 1.5 and 1.9."
    )


def test_get_body_height_both_feet_nan_returns_default():
    """Both feet NaN — no finite foot to fall back to → drop frame → 1.7 default.

    Post-fix: `np.fmin(NaN, NaN) = NaN` (no finite operand) → body_height NaN
    → `not np.isfinite(...)` drops frame → returns the 1.7 default. Same as
    pre-fix for this edge case, but the drop must be INTENTIONAL (via
    np.isfinite), not a side-effect of bare `min`.
    """
    normalizer = Pose3DNormalizer(target_height=1.7)
    frame = _frame(left_foot_y=float("nan"), right_foot_y=float("nan"), head_y=1.7)
    poses_3d = frame[np.newaxis]
    result = normalizer.get_body_height(poses_3d)
    assert abs(result - 1.7) < 1e-6, (
        f"#1050: get_body_height(both_NaN) = {result} — expected 1.7 "
        f"(the no-heights default). Both-NaN-foot frames must be dropped "
        f"via np.isfinite, not by NaN-blind `body_height > 0.1`."
    )


def test_get_body_height_uses_nan_safe_min_source():
    """Source check — root cause locked.

    `Pose3DNormalizer.get_body_height` must use a NaN-safe min (np.fmin or
    nanmin) and an np.isfinite guard. The bare NaN-unsafe
    `min(left_foot_y, right_foot_y)` pattern must NOT appear. The companion
    `normalize` function must still use `np.fmin` (existing #454 contract).
    """
    src = inspect.getsource(Pose3DNormalizer.get_body_height)
    # NaN-unsafe pattern: bare `min(left_foot_y,` (Python's min, not np.fmin).
    # `np.fmin(left_foot_y,` is fine — fmin shadows the substring.
    assert "= min(left_foot_y" not in src, (
        "#1050: NaN-unsafe `min(left_foot_y, right_foot_y)` is back in "
        "`get_body_height` — min(NaN, val) = NaN silently drops LFOOT-NaN "
        "frames (asymmetric by which foot the tracker lost). Use np.fmin "
        "(NaN-safe, falls back to finite operand) + np.isfinite guard."
    )
    # Must contain a NaN-safe min: either np.fmin or np.nanmin.
    has_nan_safe_min = "np.fmin" in src or "np.nanmin" in src
    assert has_nan_safe_min, (
        "#1050: `get_body_height` must use a NaN-safe min (np.fmin or "
        "np.nanmin) — bare Python min is NaN-arg-order-dependent."
    )
    # Must contain a finiteness guard.
    assert "np.isfinite" in src, (
        "#1050: `get_body_height` must guard `np.isfinite(body_height)` "
        "before the `> 0.1` check — NaN-blind guard lets NaN foot poison "
        "body_height then silently drops the frame."
    )
    # Companion `normalize` must still use np.fmin (existing #454 fix).
    normalize_src = inspect.getsource(Pose3DNormalizer.normalize)
    assert "np.fmin" in normalize_src, (
        "REGRESSION: `np.fmin` was removed from `normalize` — the existing "
        "#454 fix was reverted. The observable tests assume `normalize` "
        "still has the np.fmin fix."
    )
