"""RED repro — ElementSegmenter.segment crashes (ValueError) on a 1-frame video.

BUG #2 (MEDIUM — worker job dies on degenerate upload):
    ml/src/analysis/element_segmenter.py:243  `_compute_motion_energy`:
        diff = np.diff(poses, axis=0)             # line 237
        energy = np.linalg.norm(diff, axis=(1,2))  # line 240
        energy = np.pad(energy, (1, 0), mode="edge")  # line 243

    When num_frames == 1:
        np.diff(poses, axis=0)          → shape (0, 17, 2)  (empty)
        np.linalg.norm(..., axis=(1,2)) → shape (0,)        (empty)
        np.pad(empty, (1,0), mode="edge")
            → ValueError: can't extend empty axis 0 using modes
              other than 'constant' or 'empty'

Reachability:
    ml/src/pipeline.py:461  `segmenter.segment(smoothed, video_path, meta)`
    — no min-frame guard before calling segment(). A degenerate / very-short /
    corrupt upload that yields a single pose frame crashes the ENTIRE
    process_video_task arq worker job instead of degrading gracefully to an
    empty SegmentationResult.

Bug-class: empty-array-crash / unhandled-empty-axis. np.pad with mode='edge'
cannot pad an empty array (no edge value to replicate).

This test asserts segment() does NOT crash on a 1-frame input. It currently
raises ValueError → `assert not raised` FAILS → RED.
"""

from pathlib import Path

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter
from src.types import VideoMeta


def test_segment_one_frame_no_crash():
    poses = np.zeros((1, 17, 2), dtype=np.float32)
    meta = VideoMeta(
        path=Path("t.mp4"),
        width=640,
        height=480,
        fps=30.0,
        num_frames=1,
    )
    seg = ElementSegmenter()
    raised = False
    exc: BaseException | None = None
    try:
        seg.segment(poses, Path("t.mp4"), meta)
    except (ValueError, IndexError) as e:  # noqa: B017 — bug-hunt repro
        raised = True
        exc = e
    assert not raised, (
        f"BUG #2: ElementSegmenter.segment crashes on 1-frame video: "
        f"{type(exc).__name__}: {exc}. np.diff(poses, axis=0) is empty when "
        f"num_frames==1 → np.pad(energy, (1,0), mode='edge') on an empty axis "
        f"raises ValueError. Reachable via pipeline.py:461 on a degenerate "
        f"upload → crashes process_video_task worker job instead of returning "
        f"an empty SegmentationResult."
    )
