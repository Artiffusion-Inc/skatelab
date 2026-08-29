"""RED repro for issue #1036: extract_video_tracked resizes large frame
but w,h captured before resize are never updated → normalized coords
deflated by resize scale, pixel-format path inconsistent.

Mock _detect_and_crop + _moganet.infer_batch to return a keypoint at the
RESIZED-frame center. On 4K (3840×2160) input → resized 1920×1080,
center keypoint (resized x=960, y=540) MUST normalize to (0.5, 0.5).
On master, divides by original (3840, 2160) → (0.25, 0.25) — BUG.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.pose_estimation.batch_extractor import BatchPoseExtractor
from src.types import VideoMeta


def _make_extractor(monkeypatch) -> BatchPoseExtractor:
    """Build a BatchPoseExtractor with mocked detector + moganet.

    The mock detector/moganet never run — we override _detect_and_crop
    and _moganet.infer_batch directly per-test.
    """

    class FakeMogaNet:
        def __init__(self, **kwargs):
            self.closed = False

        def infer_batch(self, crops, bboxes):
            raise AssertionError("overridden per-test")

        def close(self):
            self.closed = True

    class FakeDetector:
        def __init__(self, **kwargs):
            pass

        def detect_frame(self, frame):
            raise AssertionError("overridden per-test")

    monkeypatch.setattr(
        "src.pose_estimation.moganet_batch.MogaNetBatch",
        FakeMogaNet,
    )
    monkeypatch.setattr(
        "src.detection.person_detector.PersonDetector",
        FakeDetector,
    )
    return BatchPoseExtractor(batch_size=4, device="cpu")


def _patch_video(monkeypatch, frames, meta):
    class FakeCapture:
        def __init__(self, path):
            self._idx = 0

        def isOpened(self):
            return self._idx < len(frames)

        def read(self):
            if self._idx < len(frames):
                f = frames[self._idx]
                self._idx += 1
                return True, f
            return False, None

        def release(self):
            pass

    monkeypatch.setattr(
        "src.pose_estimation.batch_extractor.cv2.VideoCapture",
        FakeCapture,
    )
    monkeypatch.setattr(
        "src.pose_estimation.batch_extractor.get_video_meta",
        lambda path: meta,
    )


def _stub_detect_and_crop(extractor, frame):
    """Stub _detect_and_crop to return a single crop covering the full frame
    and a bbox spanning (0, 0, w, h) of the (resized) frame it receives."""
    h, w = frame.shape[:2]
    crop = np.zeros((h, w, 3), dtype=np.uint8)
    return [crop], [(0, 0, w, h)]


def _stub_infer_center(resized_w, resized_h):
    """Return a MogaNet-style infer_batch that places every keypoint at the
    RESIZED-frame center (resized px)."""
    kp = np.full((1, 17, 2), np.float32(np.nan), dtype=np.float32)
    kp[0, :, 0] = resized_w / 2
    kp[0, :, 1] = resized_h / 2
    scores = np.ones((1, 17), dtype=np.float32)

    def _infer(crops, bboxes):
        return kp.copy(), scores.copy()

    return _infer


# ---------- RED: 4K frame, normalized path ----------


def test_large_frame_normalized_keypoint_not_collapsed_by_scale(monkeypatch):
    """4K 3840×2160 → resized 1920×1080 (scale=0.5). Keypoint at resized
    center (960, 540) MUST normalize to (0.5, 0.5), not (0.25, 0.25)."""
    frames = [np.zeros((2160, 3840, 3), dtype=np.uint8) for _ in range(2)]
    meta = VideoMeta(
        path=Path("4k.mp4"),
        width=3840,
        height=2160,
        fps=30.0,
        num_frames=2,
    )
    _patch_video(monkeypatch, frames, meta)
    extractor = _make_extractor(monkeypatch)

    captured_shapes: list[tuple[int, int]] = []

    def detect_and_crop(self, frame):
        captured_shapes.append(frame.shape[:2])
        return _stub_detect_and_crop(self, frame)

    monkeypatch.setattr(BatchPoseExtractor, "_detect_and_crop", detect_and_crop)
    # MogaNet receives the crop of the RESIZED frame → returns resized-px kp.
    # _detect_and_crop returns crop at full resized frame, so center is
    # resized_w/2, resized_h/2 = 960, 540.
    extractor._moganet.infer_batch = MagicMock(side_effect=_stub_infer_center(1920, 1080))

    result = extractor.extract_video_tracked("4k.mp4")

    # Detector saw the resized 1920×1080 frame.
    assert captured_shapes, "detector never called"
    assert max(captured_shapes[0]) <= 1920
    assert captured_shapes[0] == (1080, 1920)

    valid = ~np.isnan(result.poses[:, 0, 0])
    assert np.any(valid), "no valid pose extracted"
    first = result.poses[int(np.argmax(valid))]
    xs = first[:, 0]
    ys = first[:, 1]
    # All keypoints placed at resized-frame center → normalized (0.5, 0.5).
    # Bug on master: divides by original (3840, 2160) → (0.25, 0.25).
    assert np.allclose(xs[~np.isnan(xs)], 0.5, atol=1e-5), f"normalized x collapsed: {xs}"
    assert np.allclose(ys[~np.isnan(ys)], 0.5, atol=1e-5), f"normalized y collapsed: {ys}"


# ---------- RED: 4K frame, pixels-format path ----------


def test_large_frame_pixels_format_uses_resized_dims(monkeypatch):
    """Pixel-format output must be self-consistent with the resized space:
    normalized (0.5, 0.5) × resized (1920, 1080) = (960, 540).
    On master: × original (3840, 2160) = (1920, 1080) — wrong, inconsistent
    with the /= w normalization that used original dims too (giving 0.25).
    After fix both use resized dims → pixels = resized-px center (960, 540).
    """
    frames = [np.zeros((2160, 3840, 3), dtype=np.uint8) for _ in range(2)]
    meta = VideoMeta(
        path=Path("4k.mp4"),
        width=3840,
        height=2160,
        fps=30.0,
        num_frames=2,
    )
    _patch_video(monkeypatch, frames, meta)
    extractor = _make_extractor(monkeypatch)
    extractor._output_format = "pixels"

    monkeypatch.setattr(
        BatchPoseExtractor,
        "_detect_and_crop",
        _stub_detect_and_crop,
    )
    extractor._moganet.infer_batch = MagicMock(side_effect=_stub_infer_center(1920, 1080))

    result = extractor.extract_video_tracked("4k.mp4")

    valid = ~np.isnan(result.poses[:, 0, 0])
    assert np.any(valid)
    first = result.poses[int(np.argmax(valid))]
    xs = first[:, 0]
    ys = first[:, 1]
    # After fix: normalized 0.5 × resized 1920 = 960, × resized 1080 = 540.
    # Both / and * use the SAME (resized) w,h → consistent.
    assert np.allclose(xs[~np.isnan(xs)], 960.0, atol=1e-3), f"pixel x inconsistent: {xs}"
    assert np.allclose(ys[~np.isnan(ys)], 540.0, atol=1e-3), f"pixel y inconsistent: {ys}"


# ---------- Regression: small frame, no resize ----------


def test_small_frame_no_resize_normalized_keypoint_correct(monkeypatch):
    """Small frame (640×480, no resize): keypoint at center (320, 240)
    normalizes to (0.5, 0.5). Unchanged by the fix — regression guard."""
    frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(2)]
    meta = VideoMeta(
        path=Path("small.mp4"),
        width=640,
        height=480,
        fps=30.0,
        num_frames=2,
    )
    _patch_video(monkeypatch, frames, meta)
    extractor = _make_extractor(monkeypatch)

    monkeypatch.setattr(
        BatchPoseExtractor,
        "_detect_and_crop",
        _stub_detect_and_crop,
    )
    extractor._moganet.infer_batch = MagicMock(side_effect=_stub_infer_center(640, 480))

    result = extractor.extract_video_tracked("small.mp4")

    valid = ~np.isnan(result.poses[:, 0, 0])
    assert np.any(valid)
    first = result.poses[int(np.argmax(valid))]
    xs = first[:, 0]
    ys = first[:, 1]
    assert np.allclose(xs[~np.isnan(xs)], 0.5, atol=1e-5)
    assert np.allclose(ys[~np.isnan(ys)], 0.5, atol=1e-5)


# ---------- Regression: resize and no-resize paths agree ----------


def test_resize_path_matches_no_resize_path_after_fix(monkeypatch):
    """A 4K frame resized to 1920×1080 with center keypoint should produce
    the SAME normalized coords as a native 1920×1080 frame with center
    keypoint. Both must be (0.5, 0.5). On master they differ (0.25 vs 0.5).
    """

    def run(monkeypatch, frames, meta, resized_w, resized_h):
        _patch_video(monkeypatch, frames, meta)
        extractor = _make_extractor(monkeypatch)
        monkeypatch.setattr(
            BatchPoseExtractor,
            "_detect_and_crop",
            _stub_detect_and_crop,
        )
        extractor._moganet.infer_batch = MagicMock(
            side_effect=_stub_infer_center(resized_w, resized_h)
        )
        return extractor.extract_video_tracked(str(meta.path))

    # Native 1920×1080
    meta_native = VideoMeta(
        path=Path("native.mp4"),
        width=1920,
        height=1080,
        fps=30.0,
        num_frames=1,
    )
    res_native = run(
        monkeypatch,
        [np.zeros((1080, 1920, 3), dtype=np.uint8)],
        meta_native,
        1920,
        1080,
    )

    # 4K → resized to 1920×1080
    meta_4k = VideoMeta(
        path=Path("4k.mp4"),
        width=3840,
        height=2160,
        fps=30.0,
        num_frames=1,
    )
    res_4k = run(
        monkeypatch,
        [np.zeros((2160, 3840, 3), dtype=np.uint8)],
        meta_4k,
        1920,
        1080,
    )

    v_n = ~np.isnan(res_native.poses[:, 0, 0])
    v_4 = ~np.isnan(res_4k.poses[:, 0, 0])
    assert np.any(v_n) and np.any(v_4)
    a = res_native.poses[int(np.argmax(v_n))][0]
    b = res_4k.poses[int(np.argmax(v_4))][0]
    assert np.allclose(a[:2], b[:2], atol=1e-5, equal_nan=True), (
        f"resize and no-resize paths diverge: {a[:2]} vs {b[:2]}"
    )
    assert np.allclose(a[:2], [0.5, 0.5], atol=1e-5)


# ---------- Root-cause lock: source must re-read w,h after resize ----------


def test_extract_video_tracked_source_recomputes_w_h_after_resize():
    """Source of extract_video_tracked MUST re-read frame.shape after
    cv2.resize so downstream normalization uses resized dims. Locks the
    root-cause fix against regression."""
    src = inspect.getsource(BatchPoseExtractor.extract_video_tracked)
    # Find the resize call and a subsequent h, w = frame.shape read.
    resize_idx = src.find("cv2.resize")
    assert resize_idx != -1, "cv2.resize not found in source"
    after = src[resize_idx:]
    # Accept either `h, w = frame.shape[:2]` or `h, w = frame.shape[:2].`
    # re-read occurring AFTER the resize call.
    assert "frame.shape[:2]" in after, "no h, w re-read after cv2.resize — stale dims bug (#1036)"
    # Ensure there is an assignment to h, w from frame.shape AFTER resize.
    # Count occurrences: original capture + re-read = at least 2.
    assert src.count("frame.shape[:2]") >= 2, (
        "w,h must be re-read after resize (expected ≥2 frame.shape[:2] reads)"
    )
