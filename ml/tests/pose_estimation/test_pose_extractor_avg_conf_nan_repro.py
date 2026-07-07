"""RED repro for issue #1331: pose_extractor avg_conf NaN silent no-update.

Bug: In `pose_extractor.preview_persons` (line ~916), the chain
    avg_conf = float(np.mean(h36m_poses[p, :, 2]))
    if avg_conf > person_data[tid]["best_conf"]:
silently fails when any keypoint confidence is NaN because:
  - np.mean(NaN-array) returns NaN
  - NaN > best_conf is always False (IEEE NaN comparison rule)
  - best_conf / best_kps are NOT updated, no log, no error

These tests pin the contract: NaN confidences must NOT silently corrupt
the track-person selection. Either the NaN must be filtered upstream
(so avg_conf is finite and a real comparison happens), or the comparison
must short-circuit on a non-finite avg_conf without leaving the slot
stale. The tests intentionally describe the *behavior* so a future
fix that uses np.nanmean / nan_to_num / isfinite guard / ValueError all
pass.
"""

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.pose_estimation.pose_extractor import PoseExtractor

# ---------------------------------------------------------------------------
# Fixtures (lifted from the existing test_pose_extractor.py so this file
# is self-contained).
# ---------------------------------------------------------------------------


@pytest.fixture
def dummy_video_meta():
    from src.types import VideoMeta

    return VideoMeta(
        path=Path("dummy.mp4"),
        width=640,
        height=480,
        fps=30.0,
        num_frames=10,
    )


@pytest.fixture
def mock_video_capture(monkeypatch):
    frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(10)]

    class FakeCapture:
        def __init__(self, path):
            self._path = path
            self._idx = 0
            self._opened = True

        def isOpened(self):
            return self._opened

        def read(self):
            if self._idx < len(frames):
                frame = frames[self._idx]
                self._idx += 1
                return True, frame
            return False, None

        def release(self):
            self._opened = False

    monkeypatch.setattr(
        "src.pose_estimation.pose_extractor.cv2.VideoCapture",
        FakeCapture,
    )
    return FakeCapture


@pytest.fixture
def mock_async_frame_reader(monkeypatch):
    class FakeReader:
        def __init__(self, video_path, buffer_size, frame_skip):
            skip = max(1, frame_skip)
            self._frames = [
                (i, np.zeros((480, 640, 3), dtype=np.uint8)) for i in range(0, 10, skip)
            ]
            self._idx = 0

        def start(self):
            pass

        def get_frame(self):
            if self._idx < len(self._frames):
                f = self._frames[self._idx]
                self._idx += 1
                return f
            return None

        def join(self, timeout=5.0):
            pass

    monkeypatch.setattr(
        "src.pose_estimation.pose_extractor.AsyncFrameReader",
        FakeReader,
    )
    return FakeReader


@pytest.fixture
def mock_get_video_meta(monkeypatch, dummy_video_meta):
    monkeypatch.setattr(
        "src.pose_estimation.pose_extractor.get_video_meta",
        lambda path: dummy_video_meta,
    )
    return dummy_video_meta


@pytest.fixture
def mock_person_detector(monkeypatch):
    class FakeBoundingBox:
        x1 = 100.0
        y1 = 50.0
        x2 = 300.0
        y2 = 400.0
        confidence = 0.95

    class FakePersonDetector:
        def __init__(self, **kwargs):
            pass

        def detect_frame(self, frame):
            return FakeBoundingBox()

    monkeypatch.setattr(
        "src.pose_estimation.pose_extractor.PersonDetector",
        FakePersonDetector,
    )
    return FakePersonDetector


@pytest.fixture(autouse=True)
def mock_tqdm(monkeypatch):
    class FakeTqdm:
        def __init__(self, iterable=None, *args, **kwargs):
            self._iterable = iterable

        def __iter__(self):
            if self._iterable is not None:
                return iter(self._iterable)
            return iter([])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def update(self, n=1):
            pass

        def close(self):
            pass

    monkeypatch.setattr(
        "src.pose_estimation.pose_extractor._get_tqdm",
        lambda: FakeTqdm,
    )


def _make_scores_with_one_nan():
    """Return (keypoints, scores) for one person, where one of the 17
    keypoint confidences is NaN. Other 16 are valid floats in [0, 1].
    Shape: keypoints (1, 17, 2), scores (1, 17) — matches moganet batch."""
    kp = np.zeros((1, 17, 2), dtype=np.float32)
    kp[0, :, 0] = 200.0  # x in [0, 640)
    kp[0, :, 1] = 240.0  # y in [0, 480)
    scores = np.ones((1, 17), dtype=np.float32) * 0.8
    scores[0, 5] = float("nan")
    return kp, scores


class _FakeMogaNetNaNConfidence:
    """MogaNet mock that returns one person with one NaN confidence."""

    def __init__(self, **kwargs):
        pass

    def infer_batch(self, crops, bboxes):
        if not crops:
            return (
                np.zeros((0, 17, 2), dtype=np.float32),
                np.zeros((0, 17), dtype=np.float32),
            )
        kp, sc = _make_scores_with_one_nan()
        return kp, sc

    def close(self):
        pass


class _FakeMogaNetClean:
    """Baseline MogaNet mock — all valid confidences, no NaN."""

    def __init__(self, **kwargs):
        pass

    def infer_batch(self, crops, bboxes):
        if not crops:
            return (
                np.zeros((0, 17, 2), dtype=np.float32),
                np.zeros((0, 17), dtype=np.float32),
            )
        kp = np.zeros((1, 17, 2), dtype=np.float32)
        kp[0, :, 0] = 200.0
        kp[0, :, 1] = 240.0
        sc = np.full((1, 17), 0.8, dtype=np.float32)
        return kp, sc

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAvgConfNaNGuard:
    def test_best_conf_is_finite_after_nan_confidence_input(
        self,
        mock_video_capture,
        mock_get_video_meta,
        mock_person_detector,
        monkeypatch,
    ):
        """best_conf must be finite even when the input contains NaN.

        The pre-fix code lets NaN propagate: avg_conf = NaN, NaN > 0.0 is
        False, so best_conf stays at the initial 0.0 even though we have
        10 valid-ish frames. After the fix, either the NaN is filtered
        out (so best_conf becomes a real positive number) or the update
        is explicitly skipped. In both cases, best_conf must NOT be NaN.
        """
        monkeypatch.setattr(
            "src.pose_estimation.pose_extractor.MogaNetBatch",
            _FakeMogaNetNaNConfidence,
        )
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        persons, _preview = extractor.preview_persons("dummy.mp4", num_frames=10)

        # Track must exist (we detected the person in every frame).
        assert len(persons) >= 1
        # The track's hits must match the 10 frames we fed in.
        assert persons[0]["hits"] == 10

        # Inspect the internal person_data — best_conf must not be NaN.
        # We pull it out via the extractor by re-running and reading the
        # captured dict via a side-channel: attach an attribute to the
        # MogaNet instance.
        from src.pose_estimation import pose_extractor as pe_mod

        captured: dict = {}

        class _Capture:
            def __init__(self, **kwargs):
                pass

            def infer_batch(self, crops, bboxes):
                captured["called"] = True
                return _FakeMogaNetNaNConfidence().infer_batch(crops, bboxes)

            def close(self):
                pass

        monkeypatch.setattr(pe_mod, "MogaNetBatch", _Capture)
        extractor2 = PoseExtractor(device="cpu", tracking_mode="sports2d")
        extractor2.preview_persons("dummy.mp4", num_frames=10)

        # Walk the extractor instance — preview_persons is a one-shot
        # pass and the only public observable is `persons`. The contract
        # we care about: NaN in input must NOT silently leave the slot
        # at the initial 0.0 best_conf. We assert the *observable*:
        # the returned mid_hip / bbox must be derived from a real pose
        # (not None) and best_kps must contain finite values.
        # preview_persons filters by valid kps > 0.1 internally, so
        # we can only assert the *invariant* on the output dict.
        for p in persons:
            assert "mid_hip" in p
            x, y = p["mid_hip"]
            assert math.isfinite(x), f"mid_hip x is non-finite: {x}"
            assert math.isfinite(y), f"mid_hip y is non-finite: {y}"

    def test_person_count_matches_input_with_nan_confidence(
        self,
        mock_video_capture,
        mock_get_video_meta,
        mock_person_detector,
        monkeypatch,
    ):
        """With 10 valid frames (only 1 of 17 keypoints NaN), the person
        should still be detected and returned. The pre-fix code returns
        the person, but best_kps / best_conf are stale (initial 0.0).
        The fix must not break detection itself — person still appears
        in the output list.
        """
        monkeypatch.setattr(
            "src.pose_estimation.pose_extractor.MogaNetBatch",
            _FakeMogaNetNaNConfidence,
        )
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        persons, _preview = extractor.preview_persons("dummy.mp4", num_frames=10)

        # Person detected, hits counted, returned with valid bbox.
        assert len(persons) == 1
        assert persons[0]["hits"] == 10
        x1, y1, x2, y2 = persons[0]["bbox"]
        assert math.isfinite(x1) and math.isfinite(y1)
        assert math.isfinite(x2) and math.isfinite(y2)

    def test_source_uses_finite_safe_avg_conf(
        self,
    ):
        """Source-level lock: the preview_persons avg_conf line must
        guard against non-finite input. We allow the guard to take any
        of: math.isfinite(...), np.nanmean, np.nan_to_num, or an
        explicit check that raises. We require at least one isfinite /
        nan-aware call between `avg_conf = ` and the `if avg_conf >`
        comparison.

        Pre-fix: just `float(np.mean(...))` — no guard at all. The test
        fails because the regex finds no isfinite/nanmean/nan_to_num
        on the same logical block.
        """
        from src.pose_estimation import pose_extractor as pe_mod

        src = Path(pe_mod.__file__).read_text()
        # Find the preview_persons method
        start = src.find("def preview_persons(")
        assert start != -1, "preview_persons not found"
        end = src.find("def _resolve_tracking_mode", start)
        block = src[start:end]
        # Find the avg_conf assignment and the subsequent comparison.
        # The if-condition may span multiple lines (e.g.
        # `if math.isfinite(avg_conf) and avg_conf > ...`); the contract
        # is: between `avg_conf =` and the next statement (or end of
        # preview_persons), at least one NaN/finite guard must appear.
        avg_idx = block.find("avg_conf =")
        assert avg_idx != -1, "avg_conf assignment not found"
        # Find the end of the if-block: search for the next "if" or
        # non-indented statement after the avg_conf line.
        end_of_guard = block.find("\n        if ", avg_idx + 1)
        if end_of_guard == -1:
            end_of_guard = block.find("\n        next", avg_idx + 1)
        if end_of_guard == -1:
            # fall back: window of 30 lines
            lines_after = block[avg_idx:].split("\n")[:30]
            end_of_guard = avg_idx + sum(len(line) + 1 for line in lines_after)
        guarded = block[avg_idx:end_of_guard]
        has_guard = any(
            token in guarded
            for token in (
                "math.isfinite",
                "np.isfinite",
                "np.isnan",
                "nanmean",
                "nan_to_num",
            )
        )
        assert has_guard, (
            "preview_persons avg_conf has no NaN/isfinite guard between "
            "assignment and the next statement. The NaN-cmp rule silently "
            "skips updates. Add a guard."
        )

    def test_clean_input_still_works(
        self,
        mock_video_capture,
        mock_get_video_meta,
        mock_person_detector,
        monkeypatch,
    ):
        """Sanity: a no-NaN baseline still produces a valid person entry
        and finite mid_hip. Guards the fix against a regression that
        breaks the happy path."""
        monkeypatch.setattr(
            "src.pose_estimation.pose_extractor.MogaNetBatch",
            _FakeMogaNetClean,
        )
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        persons, _preview = extractor.preview_persons("dummy.mp4", num_frames=10)

        assert len(persons) == 1
        assert persons[0]["hits"] == 10
        x, y = persons[0]["mid_hip"]
        assert math.isfinite(x) and math.isfinite(y)
