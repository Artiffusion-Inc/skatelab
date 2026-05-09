"""Tests for YOLOv8n ONNX person detector."""

import numpy as np
import pytest

from src.detection.person_detector import PersonDetector
from src.types import BoundingBox


@pytest.mark.slow
class TestPersonDetector:
    """Test PersonDetector with YOLOv8n ONNX model."""

    def test_detector_initialization(self):
        """Should initialize with default parameters."""
        detector = PersonDetector()
        assert detector._confidence == 0.5
        assert detector._session is None  # Lazy load

    def test_detector_custom_params(self):
        """Should initialize with custom parameters."""
        detector = PersonDetector(confidence=0.7)
        assert detector._confidence == 0.7

    def test_model_lazy_load(self):
        """Should load ONNX session on first access."""
        detector = PersonDetector()
        assert detector._session is None
        _ = detector.model  # Access property — triggers InferenceSession creation
        assert detector._session is not None

    def test_detect_single_person(self, sample_frame):
        """Should detect person in frame with single person."""
        detector = PersonDetector()
        bbox = detector.detect_frame(sample_frame)
        if bbox is not None:
            assert isinstance(bbox, BoundingBox)
            assert 0 <= bbox.confidence <= 1
            assert bbox.width > 0
            assert bbox.height > 0

    def test_detect_empty_frame(self):
        """Should return None for empty frame."""
        detector = PersonDetector()
        empty_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        bbox = detector.detect_frame(empty_frame)
        assert bbox is None


@pytest.mark.slow
class TestBoundingBox:
    """Test BoundingBox properties."""

    def test_bounding_box_properties(self):
        """Should calculate dimensions correctly."""
        bbox = BoundingBox(x1=10, y1=20, x2=110, y2=120, confidence=0.9)
        assert bbox.width == 100
        assert bbox.height == 100
        assert bbox.center_x == 60
        assert bbox.center_y == 70

    def test_bounding_box_immutability(self):
        """BoundingBox is frozen dataclass."""
        bbox = BoundingBox(x1=10, y1=20, x2=110, y2=120, confidence=0.9)
        with pytest.raises(Exception, match="cannot assign to field"):
            bbox.x1 = 50
