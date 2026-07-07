"""RED repro — Issue #1352: _compute_edge_indicator NaN-propagates through
np.sign(NaN)=NaN, corrupting edge indicator and downstream edge_change_count.

Bug
---
`ml/src/analysis/element_segmenter.py:728-737` computes:
    left_vel = np.diff(left_foot, axis=0, prepend=left_foot[:1])
    right_vel = np.diff(right_foot, axis=0, prepend=right_foot[:1])
    edge_left = np.sign(left_vel[:, 0])
    edge_right = np.sign(right_vel[:, 0])
    edge = (edge_left + edge_right) / 2

When `left_foot` contains NaN (occluded keypoint — NORMAL during skating
crossovers / spins / deep leans), `np.diff(NaN)=NaN` and `np.sign(NaN)=NaN`.
The averaged `edge` array then contains NaN at the contaminated frame,
and downstream `edge_change_count` (line 581) silently produces a
plausible-looking value via the `NaN > 0.3 = False` comparison.

Fix pattern: `np.nan_to_num(..., nan=0.0)` BEFORE `np.sign` so NaN becomes
0 (no edge contribution) — sign(0)=0, sign(finite)=±1.
"""

from __future__ import annotations

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter
from src.types import H36Key


def _make_poses_with_nan(n_frames: int, *, nan_frame: int) -> np.ndarray:
    """Build a (n_frames, 17, 2) pose array. Monotonic LFOOT x across frames
    so the diff is +1 (sign=+1) for non-NaN frames. LFOOT[nan_frame, 0]=NaN.
    """
    poses = np.full((n_frames, 17, 2), 0.5, dtype=np.float32)
    # Monotonic x for LFOOT: 0.1, 0.2, 0.3, 0.4, ...
    poses[:, H36Key.LFOOT, 0] = np.arange(n_frames, dtype=np.float32) * 0.1 + 0.1
    # Constant x for RFOOT — diffs are 0, sign=0 — so edge contribution
    # from RFOOT is 0 across the board. Isolates LFOOT contamination.
    poses[:, H36Key.RFOOT, 0] = 0.5
    # Inject one NaN into LFOOT x at the requested frame.
    poses[nan_frame, H36Key.LFOOT, 0] = np.nan
    return poses


def test_edge_indicator_nan_in_foot_yields_zero_not_nan_repro():
    """CORRECT behavior: a single NaN in LFOOT (occluded foot keypoint) must
    produce edge[2] == 0.0 (NaN treated as no edge) — NOT NaN. Pre-fix
    (master): np.sign(NaN)=NaN propagates, edge[2]=NaN. Post-fix:
    np.nan_to_num(..., nan=0.0) before np.sign → edge[2]=0.0.

    RED on master, GREEN after fix.
    """
    seg = ElementSegmenter()
    n_frames = 5
    poses = _make_poses_with_nan(n_frames, nan_frame=2)
    edge = seg._compute_edge_indicator(poses)
    assert not np.isnan(edge).any(), (
        f"BUG (#1352): NaN in LFOOT propagated through np.sign(NaN)=NaN "
        f"to edge indicator. edge={edge}. The fix must apply "
        f"np.nan_to_num(..., nan=0.0) before np.sign so contaminated "
        f"frames yield 0 (no edge), not NaN."
    )
    assert edge[2] == 0.0, (
        f"BUG (#1352): contaminated frame edge[2]={edge[2]}, expected "
        f"0.0 (NaN masked to no-edge). Got edge={edge}."
    )


def test_edge_indicator_all_finite_unchanged_repro():
    """Regression guard: with no NaN, a monotonic LFOOT (diff=+0.1, sign=+1)
    and constant RFOOT (diff=0, sign=0) must yield edge==0.5 for frames 1..N-1.
    Frame 0 is always 0 (prepend makes diff[0]=0). Locks the typical-case
    contract so the fix doesn't break the valid-finite path.
    """
    seg = ElementSegmenter()
    n_frames = 5
    poses = _make_poses_with_nan(n_frames, nan_frame=0)  # no NaN injected
    # Force-clean: re-write to a finite value at index 0 (defensive).
    poses[:, H36Key.LFOOT, 0] = np.arange(n_frames, dtype=np.float32) * 0.1 + 0.1
    edge = seg._compute_edge_indicator(poses)
    assert not np.isnan(edge).any(), (
        f"BUG (regression): all-finite input produced NaN in edge. "
        f"edge={edge}. The fix must not break the valid-finite case."
    )
    # Frame 0: diff prepend → 0. Frames 1..N-1: sign(+0.1)=+1 from LFOOT,
    # sign(0)=0 from RFOOT → edge = 0.5.
    expected = np.array([0.0, 0.5, 0.5, 0.5, 0.5], dtype=np.float32)
    np.testing.assert_array_equal(
        edge,
        expected,
        err_msg=(
            f"BUG (regression): expected edge={expected} for all-finite "
            f"LFOOT+1, RFOOT=0, got edge={edge}."
        ),
    )
