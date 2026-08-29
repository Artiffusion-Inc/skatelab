"""RED repro for issue #1332: moganet_batch.decode_heatmaps argmax NaN silent wrong-index.

Bug: heatmaps may contain NaN (numerical instability, upstream NaN-propagate).
`np.argmax(NaN_array)` returns 0 (first NaN) → keypoint at (0, 0) silently.
Affects ALL downstream pose-based analysis (phases, metrics, recommender).

These tests assert the decoder is robust to NaN inputs — must FAIL on master
where line 113 of moganet_batch.py uses unguarded `flat.argmax(axis=2)`.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.pose_estimation.moganet_batch import decode_heatmaps


def _make_heatmaps(
    num_joints: int = 17,
    hm_h: int = 72,
    hm_w: int = 96,
    batch_size: int = 1,
) -> np.ndarray:
    """Build a (B, 17, H_hm, W_hm) heatmap with a known peak per joint.

    Peak for joint 0: (y=10, x=20) → flat index 10*96 + 20 = 980.
    First-NaN index: depends on injection. We avoid early indices.
    """
    heatmaps = np.zeros((batch_size, num_joints, hm_h, hm_w), dtype=np.float32)
    for j in range(num_joints):
        # Place peak at (y=10, x=20) for joint j — flat index 980
        heatmaps[:, j, 10, 20] = 1.0
    return heatmaps


class TestDecodeHeatmapsNaNGuard:
    def test_single_nan_in_heatmap_does_not_silently_return_zero(self):
        """One NaN in heatmap[0, 0, 1, 1] must NOT decode to NaN-steal index.

        On master: `np.argmax` treats NaN as smallest value, returning the
        first NaN's index = 97. Real peak is at flat index 980 (y=10, x=20)
        → keypoint (80, 40) in model input space. With NaN at idx 97, master
        returns (4, 4) in input space — the NaN stole the argmax.

        After fix: either (a) the function raises on NaN, or (b) it returns
        the real peak location (80, 40). Forbidden: decoded keypoint at the
        NaN-injected location (4, 4).
        """
        heatmaps = _make_heatmaps()
        # Inject NaN at flat index 1*96+1 = 97 — well before real peak at 980
        heatmaps[0, 0, 1, 1] = np.nan

        keypoints, scores = decode_heatmaps(heatmaps)

        x, y = keypoints[0, 0]
        # Real peak scaled: x = 20*(384/96)=80, y = 10*(288/72)=40
        # Master returns (4, 4) — the NaN-stolen index
        assert x == pytest.approx(80.0, abs=0.01) and y == pytest.approx(40.0, abs=0.01), (
            f"NaN stole argmax: keypoint ({x}, {y}) instead of real peak (80, 40). "
            f"keypoints={keypoints[0, 0]}, scores={scores[0, 0]}"
        )

    def test_argmax_source_is_guarded(self):
        """Source check: lock the unguarded pattern out of the codebase.

        The buggy pattern is `flat.argmax(axis=...)` on raw heatmap flat.
        Acceptable alternatives: `np.nanargmax`, `np.argmax` only on
        `np.nan_to_num(...)` results, or explicit `np.isfinite` check.
        """
        import inspect

        from src.pose_estimation import moganet_batch

        source = inspect.getsource(moganet_batch.decode_heatmaps)
        assert "np.nanargmax" in source or "np.isfinite" in source or "nan_to_num" in source, (
            "decode_heatmaps lacks a NaN guard; np.argmax on NaN-tainted heatmap "
            "returns index 0 (first NaN), producing silent wrong keypoint (0, 0)."
        )

    def test_nan_in_one_joint_does_not_corrupt_other_joints(self):
        """NaN in joint 0 must not affect joint 1 decoding (which is clean).

        On master: joint 1 still decodes correctly (peak at (10, 20)).
        This test documents that the fix must be SCOPED — only NaN joints
        are affected, not the whole batch.
        """
        heatmaps = _make_heatmaps()
        heatmaps[0, 0, 1, 1] = np.nan  # joint 0 poisoned

        keypoints, scores = decode_heatmaps(heatmaps)

        # Joint 1 is clean — must decode to the real peak
        x, y = keypoints[0, 1]
        assert x == pytest.approx(80.0, abs=0.01), f"joint 1 x corrupted: {x}"
        assert y == pytest.approx(40.0, abs=0.01), f"joint 1 y corrupted: {y}"
        assert scores[0, 1] == pytest.approx(1.0, abs=1e-6)

    def test_finite_heatmaps_still_decode_correctly(self):
        """Regression guard: clean heatmaps must still hit the real peak.

        Ensures the NaN fix doesn't break the happy path. With peak at
        (10, 20) in heatmap (96, 72), scaled to model input (384, 288):
            x_input = 20 * (384/96) = 80.0
            y_input = 10 * (288/72) = 40.0
        """
        heatmaps = _make_heatmaps()
        keypoints, scores = decode_heatmaps(heatmaps)

        # Joint 0: peak at (10, 20)
        x, y = keypoints[0, 0]
        assert x == pytest.approx(80.0, abs=0.01), f"expected x=80, got {x}"
        assert y == pytest.approx(40.0, abs=0.01), f"expected y=40, got {y}"
        assert scores[0, 0] == pytest.approx(1.0, abs=1e-6)

    def test_argmax_finds_real_peak_when_nan_injected_after_peak(self):
        """NaN injected AFTER the real peak must not pull argmax to NaN index.

        On master: argmax(NaN_array) returns the FIRST NaN index. With NaN
        at flat index 30*96+50 = 2930 (after real peak at 980), master
        returns 2930 → keypoint (200, 120) in input space, NOT real peak
        (80, 40). Forbidden: keypoint at the NaN-stolen index.
        """
        heatmaps = _make_heatmaps()
        heatmaps[0, 0, 30, 50] = np.nan  # NaN at flat index 2930

        keypoints, _scores = decode_heatmaps(heatmaps)

        x, y = keypoints[0, 0]
        # Real peak at (10, 20) → (80, 40). NaN-stolen = (200, 120).
        assert x == pytest.approx(80.0, abs=0.01), f"NaN stole argmax: x={x}, expected 80"
        assert y == pytest.approx(40.0, abs=0.01), f"NaN stole argmax: y={y}, expected 40"
