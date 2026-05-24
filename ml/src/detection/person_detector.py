"""Person detection using RF-DETR ONNX.

Replaces YOLOv8n ONNX with RF-DETR (Apache 2.0).
Pure onnxruntime — no torch/ultralytics dependency.
"""

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from ..types import BoundingBox
from ..utils.video import extract_frames

# Default model path (relative to PROJECT_ROOT)
_DEFAULT_MODEL = Path("data/models/rf_detr_nano.onnx")

# Default input size for RF-DETR-Nano; configurable per model variant
_DEFAULT_INPUT_SIZE = 384

# COCO 91-class: index 0 = background/N/A, index 1 = person
# After _drop_no_object_logit (91→90), person is at index 1
_PERSON_CLASS = 1

# ImageNet normalization constants
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid — NOT softmax.

    RF-DETR outputs raw logits; apply per-element sigmoid.
    Clipping at ±88 prevents exp overflow (float32 safe).
    """
    return 1.0 / (1.0 + np.exp(-logits.clip(-88, 88)))


def _drop_no_object_logit(logits: np.ndarray) -> np.ndarray:
    """Drop last logit column (no-object class).

    COCO: (1, 300, 91) → (1, 300, 90). Last column suppresses
    all class scores if not removed.
    """
    return logits[..., :-1]


def _cxcywh_to_xyxy(boxes: np.ndarray, orig_w: int, orig_h: int) -> np.ndarray:
    """Convert cxcywh normalized → xyxy pixel coordinates.

    RF-DETR outputs boxes as (cx, cy, w, h) in [0, 1] range.
    Convert to (x1, y1, x2, y2) in original frame pixels.
    """
    cx, cy, w, h = boxes[..., 0], boxes[..., 1], boxes[..., 2], boxes[..., 3]
    x1 = (cx - w / 2) * orig_w
    y1 = (cy - h / 2) * orig_h
    x2 = (cx + w / 2) * orig_w
    y2 = (cy + h / 2) * orig_h
    return np.stack([x1, y1, x2, y2], axis=-1)


def _imagenet_normalize(rgb: np.ndarray) -> np.ndarray:
    """ImageNet normalize: /255, subtract mean, divide by std, to NCHW.

    Args:
        rgb: (H, W, 3) uint8 RGB image.

    Returns:
        (1, 3, H, W) float32 normalized blob.
    """
    blob = rgb.astype(np.float32) / 255.0
    blob = (blob - IMAGENET_MEAN) / IMAGENET_STD
    return blob.transpose(2, 0, 1)[np.newaxis]


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45) -> list[int]:
    """Simple NMS implementation."""
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while len(order) > 0:
        i = order[0]
        keep.append(i)
        if len(order) == 1:
            break
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (
            (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
            + (boxes[order[1:], 2] - boxes[order[1:], 0])
            * (boxes[order[1:], 3] - boxes[order[1:], 1])
            - inter
            + 1e-6
        )
        order = order[1:][iou <= iou_threshold]
    return keep


class PersonDetector:
    """Person detector using RF-DETR ONNX.

    Detects people in video frames using RF-DETR (Apache 2.0).
    Pure onnxruntime — no torch/ultralytics dependency.
    """

    def __init__(
        self,
        model_path: str | Path = str(_DEFAULT_MODEL),
        confidence: float = 0.5,
        input_size: int = _DEFAULT_INPUT_SIZE,
    ) -> None:
        self._model_path = Path(model_path)
        self._confidence = confidence
        self._input_size = input_size
        self._session: ort.InferenceSession | None = None

    @property
    def model(self) -> ort.InferenceSession:
        if self._session is None:
            from src.device import DeviceConfig

            cfg = DeviceConfig.default()
            self._session = ort.InferenceSession(
                str(self._model_path),
                providers=cfg.onnx_providers,
            )
            # Warmup: one dummy inference to load CUDA kernels
            input_name = self._session.get_inputs()[0].name
            dummy = np.zeros((1, 3, self._input_size, self._input_size), dtype=np.float32)
            self._session.run(None, {input_name: dummy})
        return self._session

    def detect_frame(self, frame: np.ndarray) -> BoundingBox | None:
        """Detect person in a single frame.

        Args:
            frame: Input frame (H, W, 3) BGR.

        Returns:
            BoundingBox of highest confidence person, or None.
        """
        h, w = frame.shape[:2]

        # Preprocess: BGR→RGB, resize, ImageNet normalize
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self._input_size, self._input_size))
        blob = _imagenet_normalize(resized)

        # Inference
        session = self.model
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: blob})

        # outputs[0]: (1, 300, 4) cxcywh normalized boxes
        # outputs[1]: (1, 300, 91) logits (90 classes + 1 no-object)
        boxes = outputs[0]  # (1, 300, 4)
        logits = outputs[1]  # (1, 300, 91)

        # Step 1: Drop no-object logit column
        logits = _drop_no_object_logit(logits)  # (1, 300, 90)

        # Step 2: Sigmoid (NOT softmax)
        scores_all = _sigmoid(logits)  # (1, 300, 80)

        # Step 3: Filter person class
        scores_all = scores_all.squeeze(0)  # (300, 80)
        boxes = boxes.squeeze(0)  # (300, 4)
        person_scores = scores_all[:, _PERSON_CLASS]
        mask = person_scores > self._confidence
        if not mask.any():
            return None

        # Step 4: cxcywh normalized → xyxy pixel
        xyxy = _cxcywh_to_xyxy(boxes[mask], w, h)
        scores = person_scores[mask]

        # Step 5: NMS
        keep = _nms(xyxy, scores)
        if not keep:
            return None

        # Best detection
        best_idx = keep[0]
        bx = xyxy[best_idx]
        conf = float(scores[best_idx])

        # Clip to frame bounds
        x1 = max(0.0, min(float(bx[0]), float(w)))
        y1 = max(0.0, min(float(bx[1]), float(h)))
        x2 = max(0.0, min(float(bx[2]), float(w)))
        y2 = max(0.0, min(float(bx[3]), float(h)))

        return BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf)

    def detect_video(self, video_path: Path) -> list[BoundingBox]:
        """Detect person in all frames of a video."""
        bboxes: list[BoundingBox | None] = []
        for frame in extract_frames(video_path):
            bboxes.append(self.detect_frame(frame))
        return [b for b in bboxes if b is not None]

    def detect_first_frame(self, video_path: Path) -> BoundingBox | None:
        """Detect person in the first frame only."""
        for frame in extract_frames(video_path, max_frames=1):
            return self.detect_frame(frame)
        return None
