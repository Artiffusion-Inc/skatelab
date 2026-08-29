"""RED repro — SegmentationResult.get_timeline + export_segments_json crash
(ZeroDivisionError) on fps=0. duration_frames/fps no guard.
VideoMeta.duration_sec HAS the guard — inconsistent-guard-across-siblings
intra-types.py.

BUG #3 (MEDIUM — SegmentationResult crash on fps=0):
    ml/src/types.py:770  get_timeline:
        `duration = seg.duration_frames / self.video_meta.fps`  (no guard)
    ml/src/types.py:796  export_segments_json:
        `"duration_sec": s.duration_frames / self.video_meta.fps`  (no guard)
    ml/src/types.py:450  VideoMeta.duration_sec:
        `return self.num_frames / self.fps if self.fps > 0 else 0.0`  (HAS guard)

    fps=0 is an anticipated edge (corrupt / unreadable video, VideoMeta built
    before fps is known — see test_types.py:148 `test_video_meta_zero_fps`).
    The 2 sibling methods don't guard → ZeroDivisionError on the user-facing
    timeline + export summary.

    Bug-class: divide-by-zero / inconsistent-guard-across-siblings (11th
    instance intra-types.py). Existing test_types.py tests VideoMeta fps=0
    (:148) but NO SegmentationResult tests exist.

This test asserts get_timeline + export_segments_json do NOT raise on
fps=0. They currently raise ZeroDivisionError → `assert not raised` FAILS
→ RED.
"""

from pathlib import Path

import pytest

from src.types import ElementSegment, SegmentationResult, VideoMeta


def _make_fps_zero_result(tmp_path: Path) -> SegmentationResult:
    """Build a SegmentationResult with a fps=0 VideoMeta (the corrupt-video
    edge that VideoMeta.duration_sec already guards)."""
    meta = VideoMeta(
        path=tmp_path / "corrupt.mp4",
        width=640,
        height=480,
        fps=0.0,
        num_frames=10,
    )
    seg = ElementSegment(
        element_type="3A",
        start=0,
        end=5,
        confidence=0.8,
    )
    return SegmentationResult(
        segments=[seg],
        video_path=tmp_path / "corrupt.mp4",
        video_meta=meta,
        method="test",
        confidence=0.5,
    )


def test_segmentation_result_get_timeline_fps_zero_no_crash(tmp_path: Path):
    """SegmentationResult.get_timeline must not raise ZeroDivisionError on
    fps=0. VideoMeta.duration_sec (:450) guards `if self.fps > 0 else 0.0`;
    get_timeline (:770) does `seg.duration_frames / self.video_meta.fps`
    with no guard → ZeroDivisionError on a corrupt-video VideoMeta.
    """
    result = _make_fps_zero_result(tmp_path)

    raised = False
    exc: BaseException | None = None
    try:
        result.get_timeline()
    except ZeroDivisionError as e:
        raised = True
        exc = e

    assert not raised, (
        f"BUG: SegmentationResult.get_timeline crashes on fps=0: {exc}. "
        f"types.py:770 `seg.duration_frames / self.video_meta.fps` has no "
        f"guard, but VideoMeta.duration_sec (:450) HAS `if self.fps > 0 "
        f"else 0.0`. inconsistent-guard-across-siblings intra-types.py. "
        f"fps=0 anticipated (corrupt/unreadable video — test_types.py:148 "
        f"tests VideoMeta fps=0) → ZeroDivisionError on user-facing timeline."
    )


def test_segmentation_result_export_segments_json_fps_zero_no_crash(
    tmp_path: Path,
):
    """SegmentationResult.export_segments_json must not raise
    ZeroDivisionError on fps=0. types.py:796
    `s.duration_frames / self.video_meta.fps` has no guard (same as
    get_timeline :770). export_segments_json writes the export summary JSON
    — a user-facing surface that crashes on a corrupt-video VideoMeta.
    """
    result = _make_fps_zero_result(tmp_path)
    out = tmp_path / "segments.json"

    raised = False
    exc: BaseException | None = None
    try:
        result.export_segments_json(out)
    except ZeroDivisionError as e:
        raised = True
        exc = e

    assert not raised, (
        f"BUG: SegmentationResult.export_segments_json crashes on fps=0: {exc}. "
        f"types.py:796 `s.duration_frames / self.video_meta.fps` has no "
        f"guard (same as get_timeline :770). VideoMeta.duration_sec (:450) "
        f"HAS the guard. inconsistent-guard-across-siblings intra-types.py."
    )
