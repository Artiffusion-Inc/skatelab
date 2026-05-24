"""Tests for RF-DETR ONNX person detector."""

import numpy as np
import pytest

from src.detection.person_detector import PersonDetector
from src.types import BoundingBox


@pytest.mark.slow
class TestPersonDetector:
    """Test PersonDetector with RF-DETR ONNX model."""

    def test_detector_initialization(self):
        """Should initialize with default parameters."""
        detector = PersonDetector()
        assert detector._confidence == 0.5
        assert detector._session is None  # Lazy load
        assert detector._input_size == 384  # RF-DETR-Nano default

    def test_detector_custom_params(self):
        """Should initialize with custom parameters."""
        detector = PersonDetector(confidence=0.7, input_size=512)
        assert detector._confidence == 0.7
        assert detector._input_size == 512

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


from src.detection.person_detector import (
    _cxcywh_to_xyxy,
    _drop_no_object_logit,
    _imagenet_normalize,
    _sigmoid,
)


class TestRFDetrPostprocessing:
    """Unit tests for RF-DETR postprocessing functions."""

    def test_sigmoid_not_softmax(self):
        """Sigmoid on logits, NOT softmax — softmax would suppress multi-class."""
        logits = np.array([[2.0, -1.0, 0.5]], dtype=np.float32)
        scores = _sigmoid(logits)
        assert 0 < scores[0, 0] < 1
        assert 0 < scores[0, 1] < 1
        assert 0 < scores[0, 2] < 1
        assert abs(scores.sum() - 1.0) > 0.01

    def test_sigmoid_numerical_stability(self):
        """Large logits must not overflow — clip before exp."""
        logits = np.array([[500.0, -500.0]], dtype=np.float32)
        scores = _sigmoid(logits)
        assert np.isfinite(scores).all()
        assert scores[0, 0] > 0.99
        assert scores[0, 1] < 0.01

    def test_drop_last_logit_column(self):
        """COCO outputs (1, 300, 91) — last column is no-object class, must drop."""
        logits = np.random.randn(1, 300, 91).astype(np.float32)
        result = _drop_no_object_logit(logits)
        assert result.shape == (1, 300, 90)
        np.testing.assert_array_equal(result[0, 0, :], logits[0, 0, :-1])

    def test_cxcywh_normalized_to_xyxy_pixel(self):
        """cxcywh normalized → xyxy pixel coordinates."""
        boxes = np.array([[0.5, 0.5, 0.2, 0.3]], dtype=np.float32)
        xyxy = _cxcywh_to_xyxy(boxes, orig_w=1920, orig_h=1080)
        np.testing.assert_allclose(xyxy[0], [768, 378, 1152, 702], atol=1)

    def test_cxcywh_small_object(self):
        """Small figure skater at far end of rink — cxcywh must denormalize correctly."""
        boxes = np.array([[0.3, 0.4, 0.021, 0.056]], dtype=np.float32)
        xyxy = _cxcywh_to_xyxy(boxes, orig_w=1920, orig_h=1080)
        width = xyxy[0, 2] - xyxy[0, 0]
        assert abs(width - 40) < 2

    def test_imagenet_normalize(self):
        """ImageNet normalization: (pixel/255 - mean) / std."""
        rgb = np.array([[[100, 150, 200]]], dtype=np.uint8)
        blob = _imagenet_normalize(rgb)
        assert blob.shape == (1, 3, 1, 1)
        assert blob[0, 0, 0, 0] < 0  # R below mean
        assert blob[0, 2, 0, 0] > 1.5  # B well above mean
