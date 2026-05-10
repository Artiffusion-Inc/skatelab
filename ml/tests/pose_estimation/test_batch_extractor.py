"""Tests for BatchPoseExtractor and extract_poses_batched convenience function."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.pose_estimation.batch_extractor import (
    BatchPoseExtractor,
    _get_tqdm,
    extract_poses_batched,
)
from src.types import PersonClick, TrackedExtraction, VideoMeta


@pytest.fixture
def dummy_video_meta():
    """Return a minimal VideoMeta for mocking."""
    return VideoMeta(
        path=Path("dummy.mp4"),
        width=640,
        height=480,
        fps=30.0,
        num_frames=10,
    )


@pytest.fixture
def mock_moganet_batch(monkeypatch):
    """Mock MogaNetBatch so no ONNX model is loaded."""

    class FakeMogaNetBatch:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False

        def infer_batch(self, crops, bboxes):
            if not crops:
                return np.zeros((0, 17, 2), np.float32), np.zeros((0, 17), np.float32)
            keypoints = []
            scores = []
            for crop in crops:
                h, w = crop.shape[:2]
                kp = np.zeros((1, 17, 2), dtype=np.float32)
                kp[0, :, 0] = w / 2
                kp[0, :, 1] = h / 2
                keypoints.append(kp[0])
                scores.append(np.ones(17, dtype=np.float32))
            return np.array(keypoints), np.array(scores)

        def close(self):
            self.closed = True

    monkeypatch.setattr(
        "src.pose_estimation.moganet_batch.MogaNetBatch",
        FakeMogaNetBatch,
    )
    return FakeMogaNetBatch


@pytest.fixture
def mock_person_detector(monkeypatch):
    """Mock PersonDetector to always return a fixed bbox."""

    class FakePersonDetector:
        def __init__(self, **kwargs):
            pass

        def detect_frame(self, frame):
            h, w = frame.shape[:2]
            return type(
                "BBox",
                (),
                {
                    "x1": float(w * 0.1),
                    "y1": float(h * 0.1),
                    "x2": float(w * 0.9),
                    "y2": float(h * 0.9),
                    "confidence": 0.9,
                },
            )()

    monkeypatch.setattr(
        "src.detection.person_detector.PersonDetector",
        FakePersonDetector,
    )
    return FakePersonDetector


@pytest.fixture
def mock_video_capture(monkeypatch):
    """Mock cv2.VideoCapture to yield synthetic frames."""
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
        "src.pose_estimation.batch_extractor.cv2.VideoCapture",
        FakeCapture,
    )
    return FakeCapture


@pytest.fixture
def mock_get_video_meta(monkeypatch, dummy_video_meta):
    """Mock get_video_meta to return fixed metadata."""
    monkeypatch.setattr(
        "src.pose_estimation.batch_extractor.get_video_meta",
        lambda path: dummy_video_meta,
    )
    return dummy_video_meta


class TestBatchPoseExtractorInit:
    def test_default_init(self, mock_moganet_batch, mock_person_detector):
        """Should initialize with default parameters."""
        extractor = BatchPoseExtractor()
        assert extractor.batch_size == 8
        assert extractor._conf_threshold == 0.3
        assert extractor._output_format == "normalized"

    def test_custom_init(self, mock_moganet_batch, mock_person_detector):
        """Should accept custom parameters."""
        extractor = BatchPoseExtractor(
            batch_size=16,
            model_path="custom.onnx",
            conf_threshold=0.5,
            output_format="pixels",
            device="cpu",
        )
        assert extractor.batch_size == 16
        assert extractor._conf_threshold == 0.5
        assert extractor._output_format == "pixels"
        assert extractor._device == "cpu"
        assert extractor._model_path == "custom.onnx"

    def test_batch_size_clamped_to_one(self, mock_moganet_batch, mock_person_detector):
        """Negative batch size should be clamped to 1."""
        extractor = BatchPoseExtractor(batch_size=-5)
        assert extractor.batch_size == 1


class TestBatchPoseExtractorExtractVideoTracked:
    def test_extract_video_tracked_returns_tracked_extraction(
        self,
        mock_moganet_batch,
        mock_person_detector,
        mock_video_capture,
        mock_get_video_meta,
    ):
        """extract_video_tracked should return a TrackedExtraction."""
        extractor = BatchPoseExtractor(batch_size=4, device="cpu")
        result = extractor.extract_video_tracked("dummy.mp4")

        assert isinstance(result, TrackedExtraction)
        assert result.poses.shape == (10, 17, 3)
        assert result.frame_indices.shape == (10,)
        assert result.fps == 30.0
        assert result.video_meta.num_frames == 10

    def test_extract_video_tracked_with_person_click(
        self,
        mock_moganet_batch,
        mock_person_detector,
        mock_video_capture,
        mock_get_video_meta,
    ):
        """Should accept person_click parameter without error."""
        extractor = BatchPoseExtractor(batch_size=4, device="cpu")
        click = PersonClick(x=320, y=240)
        result = extractor.extract_video_tracked(
            "dummy.mp4",
            person_click=click,
        )
        assert isinstance(result, TrackedExtraction)

    def test_extract_video_tracked_progress_cb(
        self,
        mock_moganet_batch,
        mock_person_detector,
        mock_video_capture,
        mock_get_video_meta,
    ):
        """Should call progress_cb if provided."""
        extractor = BatchPoseExtractor(batch_size=4, device="cpu")
        calls = []

        def cb(fraction, msg):
            calls.append((fraction, msg))

        extractor.extract_video_tracked("dummy.mp4", progress_cb=cb)
        assert len(calls) > 0
        assert all(0.0 <= c[0] <= 1.0 for c in calls)

    def test_extract_video_tracked_video_open_failure(
        self,
        mock_moganet_batch,
        mock_person_detector,
        mock_get_video_meta,
        monkeypatch,
    ):
        """Should raise RuntimeError when video cannot be opened."""

        class FailingCapture:
            def isOpened(self):
                return False

            def release(self):
                pass

        monkeypatch.setattr(
            "src.pose_estimation.batch_extractor.cv2.VideoCapture",
            lambda path: FailingCapture(),
        )
        extractor = BatchPoseExtractor(device="cpu")
        with pytest.raises(RuntimeError, match="Failed to open video"):
            extractor.extract_video_tracked("bad.mp4")

    def test_extract_video_tracked_no_valid_poses(
        self,
        mock_video_capture,
        mock_get_video_meta,
        monkeypatch,
    ):
        """Should raise ValueError when no valid poses are detected."""

        class EmptyPersonDetector:
            def __init__(self, **kwargs):
                pass

            def detect_frame(self, frame):
                return None

        monkeypatch.setattr(
            "src.detection.person_detector.PersonDetector",
            EmptyPersonDetector,
        )

        class FakeMogaNetBatch:
            def __init__(self, **kwargs):
                pass

            def infer_batch(self, crops, bboxes):
                if not crops:
                    return np.zeros((0, 17, 2), np.float32), np.zeros((0, 17), np.float32)
                return np.zeros((len(crops), 17, 2), np.float32), np.zeros(
                    (len(crops), 17), np.float32
                )

            def close(self):
                pass

        monkeypatch.setattr(
            "src.pose_estimation.moganet_batch.MogaNetBatch",
            FakeMogaNetBatch,
        )
        extractor = BatchPoseExtractor(batch_size=4, device="cpu")
        with pytest.raises(ValueError, match="No valid pose detected"):
            extractor.extract_video_tracked("dummy.mp4")


class TestBatchPoseExtractorDetectAndCrop:
    def test_detect_and_crop_no_detection(self, mock_moganet_batch, monkeypatch):
        """_detect_and_crop returns empty lists when no person detected."""

        class NoDetection:
            def __init__(self, **kwargs):
                pass

            def detect_frame(self, frame):
                return None

        monkeypatch.setattr(
            "src.detection.person_detector.PersonDetector",
            NoDetection,
        )

        extractor = BatchPoseExtractor(batch_size=4, device="cpu")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        crops, bboxes = extractor._detect_and_crop(frame)
        assert crops == []
        assert bboxes == []

    def test_detect_and_crop_with_detection(self, mock_moganet_batch, monkeypatch):
        """_detect_and_crop returns padded crop and expanded bbox when person detected."""

        class FixedDetection:
            def __init__(self, **kwargs):
                pass

            def detect_frame(self, frame):
                # Returns a simple detection bbox
                return type(
                    "BBox",
                    (),
                    {"x1": 50.0, "y1": 30.0, "x2": 200.0, "y2": 300.0, "confidence": 0.9},
                )()

        monkeypatch.setattr(
            "src.detection.person_detector.PersonDetector",
            FixedDetection,
        )

        extractor = BatchPoseExtractor(batch_size=4, device="cpu")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        crops, bboxes = extractor._detect_and_crop(frame)

        assert len(crops) == 1
        assert len(bboxes) == 1
        # Verify crop was extracted from frame
        x1, y1, x2, y2 = bboxes[0]
        assert crops[0].shape[:2] == (y2 - y1, x2 - x1)
        # Verify bbox is padded (10% expansion)
        # Original: (50, 30, 200, 300) -> bw=150, bh=270
        # pad_x=15, pad_y=27
        # Expanded: x1=max(0, 35), y1=max(0, 3), x2=min(640, 215), y2=min(480, 327)
        assert bboxes[0][0] == 35  # max(0, 50 - 15)
        assert bboxes[0][1] == 3  # max(0, 30 - 27)

    def test_detect_and_crop_clips_to_frame_bounds(self, mock_moganet_batch, monkeypatch):
        """_detect_and_crop clips padded bbox to frame boundaries."""

        class EdgeDetection:
            def __init__(self, **kwargs):
                pass

            def detect_frame(self, frame):
                # Detection near top-left corner, padding should clip to 0
                return type(
                    "BBox", (), {"x1": 5.0, "y1": 5.0, "x2": 100.0, "y2": 100.0, "confidence": 0.9}
                )()

        monkeypatch.setattr(
            "src.detection.person_detector.PersonDetector",
            EdgeDetection,
        )

        extractor = BatchPoseExtractor(batch_size=4, device="cpu")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        _crops, bboxes = extractor._detect_and_crop(frame)

        x1, y1, x2, y2 = bboxes[0]
        # bbox should not go below 0
        assert x1 >= 0
        assert y1 >= 0
        # bbox should not exceed frame dimensions
        assert x2 <= 640
        assert y2 <= 480


class TestBatchPoseExtractorLargeFrame:
    def test_extract_resizes_large_frames(
        self,
        mock_moganet_batch,
        mock_get_video_meta,
        monkeypatch,
    ):
        """Frames larger than 1920px are resized for detection."""

        # Create frames that are 2560x1440 (exceeds 1920)
        large_frames = [np.zeros((1440, 2560, 3), dtype=np.uint8) for _ in range(3)]

        class FakeCaptureLarge:
            def __init__(self, path):
                self._idx = 0
                self._opened = True

            def isOpened(self):
                return self._idx < len(large_frames)

            def read(self):
                if self._idx < len(large_frames):
                    frame = large_frames[self._idx]
                    self._idx += 1
                    return True, frame
                return False, None

            def release(self):
                self._opened = False

        monkeypatch.setattr(
            "src.pose_estimation.batch_extractor.cv2.VideoCapture",
            FakeCaptureLarge,
        )

        # Use a video meta matching the large frames
        large_meta = VideoMeta(
            path=Path("large.mp4"),
            width=2560,
            height=1440,
            fps=30.0,
            num_frames=3,
        )
        monkeypatch.setattr(
            "src.pose_estimation.batch_extractor.get_video_meta",
            lambda path: large_meta,
        )

        # PersonDetector that records the frame size it received
        received_shapes = []

        class ShapeRecordingDetector:
            def __init__(self, **kwargs):
                pass

            def detect_frame(self, frame):
                received_shapes.append(frame.shape[:2])
                h, w = frame.shape[:2]
                return type(
                    "BBox",
                    (),
                    {
                        "x1": 10.0,
                        "y1": 10.0,
                        "x2": float(w) - 10.0,
                        "y2": float(h) - 10.0,
                        "confidence": 0.9,
                    },
                )()

        monkeypatch.setattr(
            "src.detection.person_detector.PersonDetector",
            ShapeRecordingDetector,
        )

        extractor = BatchPoseExtractor(batch_size=4, device="cpu")
        result = extractor.extract_video_tracked("large.mp4")

        # After resize, max dimension should be <= 1920
        # 2560 -> scale = 1920/2560 = 0.75 -> 1920x1080
        for shape in received_shapes:
            assert max(shape) <= 1920

    def test_extract_pixels_format(
        self,
        mock_moganet_batch,
        mock_person_detector,
        mock_video_capture,
        mock_get_video_meta,
    ):
        """output_format='pixels' should produce poses in pixel coordinates."""

        extractor = BatchPoseExtractor(
            batch_size=4,
            device="cpu",
            output_format="pixels",
        )
        result = extractor.extract_video_tracked("dummy.mp4")

        # Pixel format poses should have values scaled to frame dimensions
        # rather than normalized [0,1]. With our mock detector, all frames
        # get valid poses. Check that at least some values exceed 1.0
        # (pixel format scales normalized coords back to pixel space).
        valid_mask = ~np.isnan(result.poses[:, 0, 0])
        if np.any(valid_mask):
            valid_poses = result.poses[valid_mask]
            # In pixel format, x and y are multiplied by frame width/height
            # so values should be significantly larger than 1.0
            max_x = np.nanmax(np.abs(valid_poses[:, :, 0]))
            assert max_x > 1.0, f"Expected pixel coords > 1.0, got max_x={max_x}"


class TestBatchPoseExtractorLifecycle:
    def test_close_releases_resources(self, mock_moganet_batch, mock_person_detector):
        """close should clear internal references."""
        extractor = BatchPoseExtractor(batch_size=2, device="cpu")
        extractor.close()
        assert extractor._moganet is None
        assert extractor._person_detector is None

    def test_context_manager(self, mock_moganet_batch, mock_person_detector):
        """Should work as a context manager."""
        with BatchPoseExtractor(batch_size=2, device="cpu") as extractor:
            assert isinstance(extractor, BatchPoseExtractor)
        # After exit, resources should be released
        assert extractor._moganet is None

    def test_context_manager_with_exception(self, mock_moganet_batch, mock_person_detector):
        """Context manager should close resources even when exception is raised."""
        extractor = BatchPoseExtractor(batch_size=2, device="cpu")
        try:
            with extractor:
                raise ValueError("test error")
        except ValueError:
            pass
        assert extractor._moganet is None
        assert extractor._person_detector is None


class TestExtractPosesBatched:
    def test_convenience_function(
        self,
        mock_moganet_batch,
        mock_person_detector,
        mock_video_capture,
        mock_get_video_meta,
    ):
        """extract_poses_batched should return TrackedExtraction."""
        result = extract_poses_batched("dummy.mp4", batch_size=4)
        assert isinstance(result, TrackedExtraction)
        assert result.poses.shape == (10, 17, 3)

    def test_convenience_function_with_person_click(
        self,
        mock_moganet_batch,
        mock_person_detector,
        mock_video_capture,
        mock_get_video_meta,
    ):
        """Should accept person_click parameter."""
        click = PersonClick(x=100, y=200)
        result = extract_poses_batched(
            "dummy.mp4",
            batch_size=4,
            person_click=click,
        )
        assert isinstance(result, TrackedExtraction)


class TestGetTqdm:
    def test_get_tqdm_returns_callable(self):
        """_get_tqdm returns a usable progress bar class."""
        tqdm_cls = _get_tqdm()
        assert tqdm_cls is not None
        # Should be callable (either real tqdm or fallback)
        pbar = tqdm_cls(total=10)
        pbar.update(1)
        pbar.close()

    def test_get_tqdm_context_manager(self):
        """_get_tqdm result supports context manager protocol."""
        tqdm_cls = _get_tqdm()
        with tqdm_cls() as pbar:
            pbar.update(1)
        # Should not raise

    def test_get_tqdm_iteration(self):
        """_get_tqdm result supports iteration over an iterable."""
        tqdm_cls = _get_tqdm()
        items = list(tqdm_cls([10, 20, 30]))
        assert items == [10, 20, 30]


class TestTqdmFallback:
    """Test the _TqdmMock fallback class directly (lines 38-66)."""

    def test_fallback_no_iterable(self):
        """_TqdmMock with no iterable yields empty iteration."""
        # Import the fallback class by forcing _get_tqdm to return it
        # Simulate ImportError scenario
        import sys

        saved_tqdm = sys.modules.get("tqdm")
        sys.modules["tqdm"] = None  # type: ignore[assignment]

        try:
            # Re-import to pick up the module-level function with patched import
            import importlib

            import src.pose_estimation.batch_extractor as be_mod

            importlib.reload(be_mod)
            TqdmMock = be_mod._get_tqdm()

            # Test no-iterable case
            pbar = TqdmMock()
            items = list(pbar)
            assert items == []

            # Test with iterable
            items = list(TqdmMock([1, 2, 3]))
            assert items == [1, 2, 3]

            # Test update and close
            pbar2 = TqdmMock(total=10)
            pbar2.update(5)
            pbar2.close()

            # Test context manager
            with TqdmMock() as pbar3:
                pbar3.update(1)

        finally:
            # Restore tqdm module
            if saved_tqdm is not None:
                sys.modules["tqdm"] = saved_tqdm
            else:
                sys.modules.pop("tqdm", None)
            importlib.reload(be_mod)


class TestBatchPoseExtractorVideoReadBreak:
    def test_extract_stops_on_frame_read_failure(
        self,
        mock_moganet_batch,
        mock_person_detector,
        mock_get_video_meta,
        monkeypatch,
    ):
        """extract_video_tracked should handle ret=False from cap.read() gracefully."""

        # Provide 3 frames then fail
        frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(3)]

        class PartialCapture:
            def __init__(self, path):
                self._idx = 0
                self._opened = True

            def isOpened(self):
                return True

            def read(self):
                if self._idx < len(frames):
                    frame = frames[self._idx]
                    self._idx += 1
                    return True, frame
                return False, None

            def release(self):
                self._opened = False

        monkeypatch.setattr(
            "src.pose_estimation.batch_extractor.cv2.VideoCapture",
            PartialCapture,
        )

        extractor = BatchPoseExtractor(batch_size=4, device="cpu")
        # Video meta says 10 frames, but only 3 are readable
        result = extractor.extract_video_tracked("partial.mp4")
        # Should have 10 frames pre-allocated, but only 3 with valid poses
        assert result.poses.shape == (10, 17, 3)
        # First 3 frames should have valid (non-NaN) poses
        valid = ~np.isnan(result.poses[:, 0, 0])
        assert valid.sum() == 3
