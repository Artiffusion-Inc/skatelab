from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


class TrackValidator:
    """Anti-steal detection and biometric track migration."""

    CENTROID_JUMP_THRESHOLD = 0.15
    RATIO_CHANGE_THRESHOLD = 0.25
    MAX_LOST_FRAMES = 60
    MIGRATION_THRESHOLD = 1.5

    def is_stolen(
        self,
        current_pose: NDArray[np.float32],
        last_target_pose: NDArray[np.float32],
        last_target_ratios: NDArray[np.float32] | None = None,
    ) -> bool:
        cur_cx = float(np.nanmean(current_pose[:, 0]))
        cur_cy = float(np.nanmean(current_pose[:, 1]))
        prev_cx = float(np.nanmean(last_target_pose[:, 0]))
        prev_cy = float(np.nanmean(last_target_pose[:, 1]))
        jump = np.sqrt((cur_cx - prev_cx) ** 2 + (cur_cy - prev_cy) ** 2)

        skeletal_anomaly = False
        if last_target_ratios is not None:
            from ..tracking.skeletal_identity import compute_2d_skeletal_ratios

            curr_ratios = compute_2d_skeletal_ratios(current_pose)
            ratio_change = float(np.linalg.norm(curr_ratios - last_target_ratios))
            # NaN means a ratio-relevant joint was occluded (one dropped keypoint
            # poisons that bone's norm) — we cannot confirm the skater is the same.
            # Treat NaN as an anomaly (conservative): at a centroid-jump frame this is
            # exactly the steal signal the AND-gate exists to catch. NaN > threshold is
            # False in Python, which silently zeroed the biometric half of the AND-gate
            # before this guard (#451).
            skeletal_anomaly = (
                not np.isfinite(ratio_change) or ratio_change > self.RATIO_CHANGE_THRESHOLD
            )

        return jump > self.CENTROID_JUMP_THRESHOLD and skeletal_anomaly

    def migration_score(
        self,
        candidate_pose: NDArray[np.float32],
        last_target_pose: NDArray[np.float32],
        elapsed: int,
    ) -> float:
        from ..pose_estimation.h36m import biometric_distance

        cur_cx = float(np.nanmean(candidate_pose[:, 0]))
        cur_cy = float(np.nanmean(candidate_pose[:, 1]))
        prev_cx = float(np.nanmean(last_target_pose[:, 0]))
        prev_cy = float(np.nanmean(last_target_pose[:, 1]))
        pos_dist = np.sqrt((cur_cx - prev_cx) ** 2 + (cur_cy - prev_cy) ** 2)
        bio_dist = biometric_distance(candidate_pose, last_target_pose)

        w_pos = max(0.2, 1.0 - elapsed * 0.02)
        w_bio = 1.0 - w_pos
        return w_pos * pos_dist / 0.15 + w_bio * bio_dist / 0.08
