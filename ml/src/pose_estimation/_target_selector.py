from __future__ import annotations

import numpy as np  # noqa: TC002
from numpy.typing import NDArray  # noqa: TC002


class TargetSelector:
    """Selects target person via click proximity or auto-select by detection frequency."""

    def __init__(
        self,
        click_norm: tuple[float, float] | None = None,
        click_lock_window: int = 6,
    ) -> None:
        self.click_norm = click_norm
        self.click_lock_window = click_lock_window
        self._target_track_id: int | None = None

    @property
    def target_track_id(self) -> int | None:
        return self._target_track_id

    def select_target(
        self,
        h36m_poses: NDArray[np.float32],
        track_ids: list[int],
        frame_idx: int,
    ) -> int | None:
        """Try to select target via click proximity. Returns selected track_id or None."""
        if self._target_track_id is not None:
            return None
        if self.click_norm is None:
            return None
        if frame_idx >= self.click_lock_window:
            return None

        best_dist = float("inf")
        best_tid = None
        cx_click, cy_click = self.click_norm

        for p, tid in enumerate(track_ids):
            # ponytail: NaN hip (occluded) must not silently pick a different person.
            # Prefer hip midpoint; if a hip is NaN fall back to finite-hip midpoint,
            # then to mean of all finite keypoints; all-NaN person is skipped.
            ref = self._hip_reference(h36m_poses[p])
            if ref is None:
                continue
            ref_x, ref_y = ref
            dist = (ref_x - cx_click) ** 2 + (ref_y - cy_click) ** 2
            if dist < best_dist:
                best_dist = dist
                best_tid = tid

        if best_tid is not None:
            self._target_track_id = best_tid
        return best_tid

    @staticmethod
    def _hip_reference(
        pose: NDArray[np.float32],
    ) -> tuple[float, float] | None:
        """NaN-robust hip reference. Returns (x, y) or None if all keypoints NaN.

        LHIP=4, RHIP=1. Prefer midpoint; fall back to the single finite hip; then to
        the mean of all finite keypoints (torso centroid proxy).
        """
        lhip = pose[4]
        rhip = pose[1]
        l_finite = bool(np.isfinite(lhip).all())
        r_finite = bool(np.isfinite(rhip).all())
        if l_finite and r_finite:
            return float((lhip[0] + rhip[0]) / 2), float((lhip[1] + rhip[1]) / 2)
        if r_finite:
            return float(rhip[0]), float(rhip[1])
        if l_finite:
            return float(lhip[0]), float(lhip[1])
        finite_mask = np.isfinite(pose[:, 0]) & np.isfinite(pose[:, 1])
        if not finite_mask.any():
            return None
        return float(pose[finite_mask, 0].mean()), float(pose[finite_mask, 1].mean())

    @staticmethod
    def auto_select_by_hits(track_hit_counts: dict[int, int]) -> int | None:
        if not track_hit_counts:
            return None
        return max(track_hit_counts, key=lambda k: track_hit_counts[k])
