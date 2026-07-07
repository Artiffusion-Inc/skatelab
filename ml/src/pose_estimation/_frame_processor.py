from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .h36m import coco_to_h36m

if TYPE_CHECKING:
    from numpy.typing import NDArray


class FrameProcessor:
    """Converts raw RTMO output (COCO keypoints) to H3.6M format per frame."""

    def __init__(self, output_format: str = "normalized") -> None:
        self.output_format = output_format

    def convert_keypoints(
        self,
        keypoints: NDArray[np.float32],  # (P, 17, 2) pixels
        scores: NDArray[np.float32],  # (P, 17)
        frame_width: int,
        frame_height: int,
    ) -> NDArray[np.float32]:  # (P, 17, 3)
        n_persons = keypoints.shape[0]
        h36m_poses = np.zeros((n_persons, 17, 3), dtype=np.float32)
        # #1045: guard w, h at the trust boundary. `coco[:, 0] /= w` is
        # unguarded — w=0 → inf, w=-1 → -x, w=NaN → NaN. The two prod
        # callers (pose_extractor.py:329, :533) source w, h from
        # `frame.shape[:2]` so they never pass 0, but any future caller
        # (batched extractor, test fixture, video_key with 0-width meta)
        # gets silent poison. Strict: raise ValueError for non-positive
        # or non-finite dims — caller contract violation must fail loud.
        w_raw, h_raw = float(frame_width), float(frame_height)
        if not (np.isfinite(w_raw) and w_raw > 0):
            raise ValueError(f"frame_width must be a positive finite number, got {frame_width}")
        if not (np.isfinite(h_raw) and h_raw > 0):
            raise ValueError(f"frame_height must be a positive finite number, got {frame_height}")
        w, h = w_raw, h_raw

        for p in range(n_persons):
            coco = np.zeros((17, 3), dtype=np.float32)
            coco[:, :2] = keypoints[p].astype(np.float32)
            coco[:, 2] = scores[p].astype(np.float32)
            coco[:, 0] /= w
            coco[:, 1] /= h

            h36m = coco_to_h36m(coco)

            if self.output_format == "pixels":
                h36m[:, 0] *= w
                h36m[:, 1] *= h

            h36m_poses[p] = h36m

        return h36m_poses
