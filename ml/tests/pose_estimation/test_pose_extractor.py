"""Tests for PoseExtractor and extract_poses convenience function."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.pose_estimation.pose_extractor import PoseExtractor, extract_poses
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
        "src.pose_estimation.pose_extractor.cv2.VideoCapture",
        FakeCapture,
    )
    return FakeCapture


@pytest.fixture
def mock_async_frame_reader(monkeypatch):
    """Mock AsyncFrameReader to yield synthetic frames synchronously."""

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
    """Mock get_video_meta to return fixed metadata."""
    monkeypatch.setattr(
        "src.pose_estimation.pose_extractor.get_video_meta",
        lambda path: dummy_video_meta,
    )
    return dummy_video_meta


@pytest.fixture
def mock_moganet_batch(monkeypatch):
    """Mock MogaNetBatch so no ONNX model is loaded."""

    class FakeMogaNetBatch:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def infer_batch(self, crops, bboxes):
            if not crops:
                return (
                    np.zeros((0, 17, 2), dtype=np.float32),
                    np.zeros((0, 17), dtype=np.float32),
                )
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
            pass

    monkeypatch.setattr(
        "src.pose_estimation.pose_extractor.MogaNetBatch",
        FakeMogaNetBatch,
    )
    return FakeMogaNetBatch


@pytest.fixture
def mock_person_detector(monkeypatch):
    """Mock PersonDetector to return a single synthetic bbox per frame."""

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
    """Suppress tqdm progress bars in tests."""

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


@pytest.fixture
def mock_device_config(monkeypatch):
    """Mock DeviceConfig for auto device resolution."""

    class FakeDeviceConfig:
        def __init__(self, device="auto"):
            self.device = "cuda"

    monkeypatch.setattr(
        "src.device.DeviceConfig",
        FakeDeviceConfig,
    )
    return FakeDeviceConfig


class TestPoseExtractorInit:
    def test_default_init(self, mock_moganet_batch, mock_person_detector):
        """Should initialize with default parameters."""
        extractor = PoseExtractor()
        assert extractor._model_path == "data/models/moganet/moganet_b_ap2d_384x288_fp16.onnx"
        assert extractor._tracking_backend == "custom"
        assert extractor._tracking_mode == "auto"
        assert extractor._conf_threshold == 0.3
        assert extractor._output_format == "normalized"
        assert extractor._frame_skip == 1

    def test_custom_init(self, mock_moganet_batch, mock_person_detector):
        """Should accept custom parameters."""
        extractor = PoseExtractor(
            model_path="custom.onnx",
            tracking_backend="custom",
            tracking_mode="sports2d",
            conf_threshold=0.5,
            output_format="pixels",
            frame_skip=0,
            device="cuda",
        )
        assert extractor._model_path == "custom.onnx"
        assert extractor._tracking_backend == "custom"
        assert extractor._tracking_mode == "sports2d"
        assert extractor._conf_threshold == 0.5
        assert extractor._output_format == "pixels"
        assert extractor._frame_skip == 1  # clamped to minimum 1
        assert extractor._device == "cuda"

    def test_auto_device(self, mock_device_config, mock_moganet_batch, mock_person_detector):
        """Should resolve 'auto' device via DeviceConfig."""
        extractor = PoseExtractor(device="auto")
        assert extractor._device == "cuda"


class TestPoseExtractorResolveTrackingMode:
    def test_explicit_mode_returns_unchanged(self, mock_moganet_batch, mock_person_detector):
        """Should return the explicitly set tracking mode."""
        extractor = PoseExtractor(tracking_mode="sports2d")
        assert extractor._resolve_tracking_mode() == "sports2d"

    def test_auto_prefers_deepsort(self, mock_moganet_batch, mock_person_detector):
        """Auto mode should prefer deepsort when available."""
        extractor = PoseExtractor(tracking_mode="auto")
        # deep_sort_realtime is installed in this environment
        assert extractor._resolve_tracking_mode() == "deepsort"

    def test_auto_falls_back_to_sports2d(
        self, monkeypatch, mock_moganet_batch, mock_person_detector
    ):
        """Auto mode should fall back to sports2d when deepsort unavailable."""
        monkeypatch.setitem(sys.modules, "deep_sort_realtime", None)
        # Re-import to pick up the changed module state
        from src.pose_estimation.pose_extractor import PoseExtractor as PE

        extractor = PE(tracking_mode="auto")
        assert extractor._resolve_tracking_mode() == "sports2d"


class TestPoseExtractorExtractVideoTracked:
    def test_extract_video_tracked_streaming_returns_tracked_extraction(
        self,
        mock_video_capture,
        mock_async_frame_reader,
        mock_get_video_meta,
        mock_moganet_batch,
        mock_person_detector,
    ):
        """Streaming path should return TrackedExtraction with valid poses."""
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        result = extractor.extract_video_tracked("dummy.mp4", use_batch=False)

        assert isinstance(result, TrackedExtraction)
        assert result.poses.shape == (10, 17, 3)
        assert result.frame_indices.shape == (10,)
        assert result.fps == 30.0
        assert result.video_meta.num_frames == 10
        assert result.first_frame is not None
        assert result.target_track_id is not None

    def test_extract_video_tracked_batch_returns_tracked_extraction(
        self,
        mock_video_capture,
        mock_get_video_meta,
        mock_moganet_batch,
        mock_person_detector,
    ):
        """Batch path should return TrackedExtraction with valid poses."""
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        result = extractor.extract_video_tracked("dummy.mp4", use_batch=True)

        assert isinstance(result, TrackedExtraction)
        assert result.poses.shape == (10, 17, 3)
        assert result.frame_indices.shape == (10,)
        assert result.fps == 30.0
        assert result.video_meta.num_frames == 10
        assert result.first_frame is not None
        assert result.target_track_id is not None

    def test_extract_video_tracked_with_person_click_streaming(
        self,
        mock_video_capture,
        mock_async_frame_reader,
        mock_get_video_meta,
        mock_moganet_batch,
        mock_person_detector,
    ):
        """Streaming path should handle person_click selection."""
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        click = PersonClick(x=320, y=300)
        result = extractor.extract_video_tracked(
            "dummy.mp4",
            person_click=click,
            use_batch=False,
        )
        assert isinstance(result, TrackedExtraction)
        assert result.target_track_id is not None

    def test_extract_video_tracked_with_person_click_batch(
        self,
        mock_video_capture,
        mock_get_video_meta,
        mock_moganet_batch,
        mock_person_detector,
    ):
        """Batch path should handle person_click selection."""
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        click = PersonClick(x=320, y=300)
        result = extractor.extract_video_tracked(
            "dummy.mp4",
            person_click=click,
            use_batch=True,
        )
        assert isinstance(result, TrackedExtraction)
        assert result.target_track_id is not None

    def test_extract_video_tracked_no_poses_raises_value_error_streaming(
        self,
        mock_video_capture,
        mock_async_frame_reader,
        mock_get_video_meta,
        mock_moganet_batch,
        monkeypatch,
    ):
        """Streaming path should raise ValueError when no poses detected."""

        class EmptyDetector:
            def __init__(self, **kwargs):
                pass

            def detect_frame(self, frame):
                return None

        monkeypatch.setattr(
            "src.pose_estimation.pose_extractor.PersonDetector",
            EmptyDetector,
        )
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        with pytest.raises(ValueError, match="No valid pose detected"):
            extractor.extract_video_tracked("dummy.mp4", use_batch=False)

    def test_extract_video_tracked_no_poses_raises_value_error_batch(
        self,
        mock_video_capture,
        mock_get_video_meta,
        mock_moganet_batch,
        monkeypatch,
    ):
        """Batch path should raise ValueError when no poses detected."""

        class EmptyDetector:
            def __init__(self, **kwargs):
                pass

            def detect_frame(self, frame):
                return None

        monkeypatch.setattr(
            "src.pose_estimation.pose_extractor.PersonDetector",
            EmptyDetector,
        )
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        with pytest.raises(ValueError, match="No valid pose detected"):
            extractor.extract_video_tracked("dummy.mp4", use_batch=True)

    def test_extract_video_tracked_progress_callback_streaming(
        self,
        mock_video_capture,
        mock_async_frame_reader,
        mock_get_video_meta,
        mock_moganet_batch,
        mock_person_detector,
    ):
        """Streaming path should call progress_cb if provided."""
        progress_calls = []

        def progress_cb(fraction, message):
            progress_calls.append((fraction, message))

        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        extractor.extract_video_tracked(
            "dummy.mp4",
            progress_cb=progress_cb,
            use_batch=False,
        )
        assert len(progress_calls) > 0

    def test_extract_video_tracked_progress_callback_batch(
        self,
        mock_video_capture,
        mock_get_video_meta,
        mock_moganet_batch,
        mock_person_detector,
    ):
        """Batch path should call progress_cb if provided."""
        progress_calls = []

        def progress_cb(fraction, message):
            progress_calls.append((fraction, message))

        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        extractor.extract_video_tracked(
            "dummy.mp4",
            progress_cb=progress_cb,
            use_batch=True,
        )
        assert len(progress_calls) > 0


class TestPoseExtractorPreviewPersons:
    def test_preview_persons_returns_list_and_path(
        self,
        mock_video_capture,
        mock_get_video_meta,
        mock_moganet_batch,
        mock_person_detector,
    ):
        """Should return a list of person dicts and a preview path."""
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        persons, preview_path = extractor.preview_persons("dummy.mp4", num_frames=10)

        assert isinstance(persons, list)
        assert len(persons) > 0
        assert all("track_id" in p for p in persons)
        assert all("hits" in p for p in persons)
        assert all("bbox" in p for p in persons)
        assert all("mid_hip" in p for p in persons)
        assert preview_path is not None
        assert isinstance(preview_path, str)
        assert preview_path.endswith(".jpg")

    def test_preview_persons_empty_video(
        self,
        mock_video_capture,
        mock_get_video_meta,
        mock_moganet_batch,
        monkeypatch,
    ):
        """Should return empty list when no persons detected."""

        class EmptyDetector:
            def __init__(self, **kwargs):
                pass

            def detect_frame(self, frame):
                return None

        monkeypatch.setattr(
            "src.pose_estimation.pose_extractor.PersonDetector",
            EmptyDetector,
        )
        extractor = PoseExtractor(device="cpu", tracking_mode="sports2d")
        persons, preview_path = extractor.preview_persons("dummy.mp4", num_frames=10)
        assert persons == []
        assert preview_path is None


class TestPoseExtractorBuildPersonGrid:
    def test_build_person_grid(self):
        """Should generate a preview image path."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        persons = [
            {
                "best_kps": np.random.rand(17, 3).astype(np.float32),
                "hits": 5,
            }
        ]
        # Ensure enough valid keypoints for bbox computation
        persons[0]["best_kps"][:, 2] = 1.0

        path = PoseExtractor._build_person_grid(frame, persons)
        assert isinstance(path, str)
        assert path.endswith(".jpg")
        assert Path(path).exists()

    def test_build_person_grid_empty(self):
        """Should return empty string for empty persons."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        path = PoseExtractor._build_person_grid(frame, [])
        assert path == ""


class TestPoseExtractorContextManager:
    def test_context_manager(self, mock_moganet_batch, mock_person_detector):
        """Should support with-statement."""
        with PoseExtractor(device="cpu") as extractor:
            assert isinstance(extractor, PoseExtractor)

    def test_close_releases_resources(self, mock_moganet_batch, mock_person_detector):
        """close() should call moganet.close()."""
        extractor = PoseExtractor(device="cpu")
        extractor.close()
        assert True  # Just verify no exception


class TestExtractPoses:
    def test_convenience_function(self, monkeypatch, mock_moganet_batch, mock_person_detector):
        """extract_poses should create extractor and return TrackedExtraction."""
        mock_result = TrackedExtraction(
            poses=np.zeros((10, 17, 3), dtype=np.float32),
            frame_indices=np.arange(10),
            first_detection_frame=0,
            target_track_id=0,
            fps=30.0,
            video_meta=VideoMeta(Path("dummy.mp4"), 640, 480, 30.0, 10),
            first_frame=None,
        )

        def mock_extract(self, video_path, person_click=None):
            return mock_result

        monkeypatch.setattr(PoseExtractor, "extract_video_tracked", mock_extract)

        result = extract_poses("dummy.mp4")
        assert result is mock_result
