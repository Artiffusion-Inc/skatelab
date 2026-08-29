"""RED repro for issue #971: TargetSelector NaN hip → wrong-person click target.

When the click-near skater has a NaN hip keypoint on the click frame, the
NaN-unsafe `dist < best_dist` comparison (NaN < x always False) silently
skips that person and selects a further-away skater. This file must FAIL
on master and PASS after the guard is added.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.pose_estimation._target_selector import TargetSelector


def _two_person_poses(nan_left_hip_person0: bool) -> np.ndarray:
    poses = np.zeros((2, 17, 2), dtype=np.float32)
    # Person 0 — click-near, on the click point (0.5, 0.5)
    poses[0, 1, :] = [0.5, 0.5]  # RHIP
    if nan_left_hip_person0:
        poses[0, 4, :] = np.nan  # LHIP NaN → mid_hip NaN
    else:
        poses[0, 4, :] = [0.5, 0.5]
    # Person 1 — far away
    poses[1, 1, :] = [0.9, 0.9]
    poses[1, 4, :] = [0.9, 0.9]
    return poses


def test_nan_hip_click_near_person_selected_not_far_person() -> None:
    """Click near person whose LHIP is NaN must NOT silently pick the far person."""
    sel = TargetSelector(click_norm=(0.5, 0.5), click_lock_window=6)
    poses = _two_person_poses(nan_left_hip_person0=True)
    tid = sel.select_target(poses, [10, 20], 0)
    # Correct contract: NaN-hip click-near person (tid=10) selected, NOT far (tid=20).
    assert tid == 10, f"expected click-near person tid=10, got {tid}"


def test_all_finite_regression_unchanged() -> None:
    """All-finite case: nearest hip still wins (regression)."""
    sel = TargetSelector(click_norm=(0.5, 0.5), click_lock_window=6)
    poses = _two_person_poses(nan_left_hip_person0=False)
    tid = sel.select_target(poses, [10, 20], 0)
    assert tid == 10


def test_all_nan_hip_no_crash_defined_fallback() -> None:
    """All persons have NaN hips — must not crash, return defined fallback (None or first)."""
    sel = TargetSelector(click_norm=(0.5, 0.5), click_lock_window=6)
    poses = np.full((2, 17, 2), np.nan, dtype=np.float32)
    tid = sel.select_target(poses, [10, 20], 0)
    # Defined fallback: None (fail closed) is acceptable. No crash, no Exception.
    assert tid is None or tid in (10, 20), f"expected None or one of track_ids, got {tid}"


def test_nan_rhip_only_same_bug_class() -> None:
    """NaN in RHIP alone (LHIP finite) → same NaN mid_hip bug class. Must pick click-near."""
    sel = TargetSelector(click_norm=(0.5, 0.5), click_lock_window=6)
    poses = np.zeros((2, 17, 2), dtype=np.float32)
    poses[0, 4, :] = [0.5, 0.5]  # LHIP finite
    poses[0, 1, :] = np.nan  # RHIP NaN → mid_hip NaN
    poses[1, 1, :] = [0.9, 0.9]
    poses[1, 4, :] = [0.9, 0.9]
    tid = sel.select_target(poses, [10, 20], 0)
    assert tid == 10, f"expected click-near person tid=10 even with NaN RHIP, got {tid}"


def test_source_has_isfinite_or_nan_guard() -> None:
    """Root cause lock: select_target path must contain an explicit NaN/isfinite guard.

    Checks the whole class source since the guard may live in a helper the
    selection loop calls. The contract is: a NaN hip must be handled explicitly,
    not via the NaN < x == False comparison-semantics accident.
    """
    src = inspect.getsource(TargetSelector)
    assert "isfinite" in src or "nan_to_num" in src or "isnan" in src, (
        "TargetSelector missing NaN/isfinite guard (root cause not fixed)"
    )
