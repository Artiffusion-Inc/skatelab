"""Person detection using YOLOv8n ONNX.

Replaces Ultralytics-based detection with pure ONNX inference.
No torch/ultralytics dependency — runs on onnxruntime only.
"""

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from ..types import BoundingBox
from ..utils.video import extract_frames

# Default model path (relative to PROJECT_ROOT)
_DEFAULT_MODEL = Path("data/models/yolov8n.onnx")

# YOLOv8 input size
_INPUT_SIZE = 640

# COCO class 0 = person
_PERSON_CLASS = 0


def _letterbox(
    frame: np.ndarray, new_shape: int = _INPUT_SIZE
) -> tuple[np.ndarray, tuple[float, float], tuple[int, int]]:
    """Resize + pad frame to square, keeping aspect ratio."""
    h, w = frame.shape[:2]
    r = min(new_shape / h, new_shape / w)
    new_unpad = (round(w * r), round(h * r))
    dw = new_shape - new_unpad[0]
    dh = new_shape - new_unpad[1]
    dw /= 2
    dh /= 2

    resized = cv2.resize(frame, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = round(dh - 0.1), round(dh + 0.1)
    left, right = round(dw - 0.1), round(dw + 0.1)
    padded = cv2.copyMakeBorder(
        resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )
    return padded, (r, r), (left, top)


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
    """Person detector using YOLOv8n ONNX.

    Detects people in video frames using YOLOv8n (nano) model.
    Pure onnxruntime — no torch/ultralytics dependency.
    """

    def __init__(
        self, model_path: str | Path = str(_DEFAULT_MODEL), confidence: float = 0.5
    ) -> None:
        self._model_path = Path(model_path)
        self._confidence = confidence
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
        return self._session

    def detect_frame(self, frame: np.ndarray) -> BoundingBox | None:
        """Detect person in a single frame.

        Args:
            frame: Input frame (H, W, 3) BGR.

        Returns:
            BoundingBox of highest confidence person, or None.
        """
        img, (r, _), (pad_w, pad_h) = _letterbox(frame)
        blob = img.transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = blob[np.newaxis, ...]  # (1, 3, 640, 640)

        session = self.model
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: blob})
        pred = outputs[0]  # (1, 84, 8400)

        pred = pred[0].T  # type: ignore[index]  # (8400, 84): [x_center, y_center, w, h, class_0_score, ...]

        # Filter person class
        person_scores = pred[:, 4 + _PERSON_CLASS]
        mask = person_scores > self._confidence
        if not mask.any():
            return None

        filtered = pred[mask]
        scores = person_scores[mask]

        # Convert xywh → xyxy
        xywh = filtered[:, :4]
        xyxy = np.empty_like(xywh)
        xyxy[:, 0] = xywh[:, 0] - xywh[:, 2] / 2  # x1
        xyxy[:, 1] = xywh[:, 1] - xywh[:, 3] / 2  # y1
        xyxy[:, 2] = xywh[:, 0] + xywh[:, 2] / 2  # x2
        xyxy[:, 3] = xywh[:, 1] + xywh[:, 3] / 2  # y2

        # NMS
        keep = _nms(xyxy, scores)
        if not keep:
            return None

        # Best detection
        best_idx = keep[0]
        bx = xyxy[best_idx]
        conf = float(scores[best_idx])

        # Undo letterbox: remove padding, scale back
        x1 = (bx[0] - pad_w) / r
        y1 = (bx[1] - pad_h) / r
        x2 = (bx[2] - pad_w) / r
        y2 = (bx[3] - pad_h) / r

        # Clip to frame bounds
        h, w = frame.shape[:2]
        x1 = max(0, min(x1, w))
        y1 = max(0, min(y1, h))
        x2 = max(0, min(x2, w))
        y2 = max(0, min(y2, h))

        return BoundingBox(x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2), confidence=conf)

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
