# RF-DETR Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace YOLOv8n (AGPL-3.0) with RF-DETR (Apache 2.0) for person detection, removing all ultralytics dependencies.

**Architecture:** Drop-in replacement of PersonDetector internals — same API (`detect_frame`, `detect_video`, `detect_first_frame`), different preprocessing (ImageNet normalize + BGR→RGB) and postprocessing (sigmoid, drop last logit, cxcywh→xyxy denormalize). Staged pipeline releases detector VRAM after detection phase.

**Tech Stack:** RF-DETR ONNX (opset 17), onnxruntime-gpu (CUDA EP), Python 3.12 (export), rfdetr >=1.7.0

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Rewrite** | `ml/src/detection/person_detector.py` | RF-DETR ONNX inference: preprocess, postprocess, warmup |
| **Modify** | `ml/gpu_server/server.py:58,64,83-84` | Rename YOLO→RF-DETR paths and variables |
| **Modify** | `ml/pyproject.toml:19` | Remove `ultralytics>=8.0.0` |
| **Modify** | `ml/scripts/download_ml_models.py` | Add RF-DETR model download entries |
| **Modify** | `data/models/models.manifest.json` | Add RF-DETR manifest entries |
| **Modify** | `ml/tests/detection/test_person_detector.py` | Add RF-DETR-specific tests |
| **Delete** | `ml/yolov8n.pt` | PyTorch YOLOv8n weights |
| **Delete** | `ml/scripts/create_yolo_subset.py` | YOLO dataset creator |
| **Delete** | `ml/scripts/train_yolo26_pose.py` | YOLO pose training |
| **Delete** | `ml/scripts/train_yolo26n_distill.py` | YOLO distillation |
| **Create** | `ml/scripts/benchmark_detector.py` | Compare RF-DETR N/S/M on skating video |
| **Create** | `ml/scripts/export_rf_detr.py` | Export RF-DETR PyTorch→ONNX |

---

## Task 1: Write failing tests for RF-DETR postprocessing

**Files:**

- Modify: `ml/tests/detection/test_person_detector.py`

- [ ] **Step 1: Add RF-DETR postprocessing unit tests**

```python
"""Tests for RF-DETR ONNX person detector."""

import numpy as np
import pytest

from src.detection.person_detector import (
    _sigmoid,
    _drop_no_object_logit,
    _cxcywh_to_xyxy,
    _imagenet_normalize,
)


class TestRFDetrPostprocessing:
    """Unit tests for RF-DETR postprocessing functions."""

    def test_sigmoid_not_softmax(self):
        """Sigmoid on logits, NOT softmax — softmax would suppress multi-class."""
        logits = np.array([[2.0, -1.0, 0.5]], dtype=np.float32)
        scores = _sigmoid(logits)
        # Sigmoid: each score independent, all in (0, 1)
        assert 0 < scores[0, 0] < 1
        assert 0 < scores[0, 1] < 1
        assert 0 < scores[0, 2] < 1
        # Softsoft would sum to 1 — sigmoid doesn't
        assert abs(scores.sum() - 1.0) > 0.01

    def test_sigmoid_numerical_stability(self):
        """Large logits must not overflow — clip before exp."""
        logits = np.array([[500.0, -500.0]], dtype=np.float32)
        scores = _sigmoid(logits)
        assert np.isfinite(scores).all()
        assert scores[0, 0] > 0.99  # exp(500) ≈ 1
        assert scores[0, 1] < 0.01  # exp(-500) ≈ 0

    def test_drop_last_logit_column(self):
        """COCO outputs (1, 300, 81) — last column is no-object class, must drop."""
        logits = np.random.randn(1, 300, 81).astype(np.float32)
        result = _drop_no_object_logit(logits)
        assert result.shape == (1, 300, 80)
        # Verify it's the LAST column dropped, not first
        np.testing.assert_array_equal(result[0, 0, :], logits[0, 0, :-1])

    def test_cxcywh_normalized_to_xyxy_pixel(self):
        """cxcywh normalized → xyxy pixel coordinates."""
        # cx=0.5, cy=0.5, w=0.2, h=0.3 at 1920×1080
        boxes = np.array([[0.5, 0.5, 0.2, 0.3]], dtype=np.float32)
        xyxy = _cxcywh_to_xyxy(boxes, orig_w=1920, orig_h=1080)
        # x1 = (0.5 - 0.1) * 1920 = 768
        # y1 = (0.5 - 0.15) * 1080 = 378
        # x2 = (0.5 + 0.1) * 1920 = 1152
        # y2 = (0.5 + 0.15) * 1080 = 702
        np.testing.assert_allclose(xyxy[0], [768, 378, 1152, 702], atol=1)

    def test_cxcywh_small_object(self):
        """Small figure skater at far end of rink — cxcywh must denormalize correctly."""
        # Skater 40px wide in 1920 frame: w = 40/1920 ≈ 0.021
        boxes = np.array([[0.3, 0.4, 0.021, 0.056]], dtype=np.float32)
        xyxy = _cxcywh_to_xyxy(boxes, orig_w=1920, orig_h=1080)
        width = xyxy[0, 2] - xyxy[0, 0]
        assert abs(width - 40) < 2  # ≈40px

    def test_imagenet_normalize(self):
        """ImageNet normalization: (pixel/255 - mean) / std."""
        rgb = np.array([[[100, 150, 200]]], dtype=np.uint8)  # 1×1×3
        blob = _imagenet_normalize(rgb)
        # R: (100/255 - 0.485) / 0.229 ≈ -0.551
        # G: (150/255 - 0.456) / 0.224 ≈ 0.526
        # B: (200/255 - 0.406) / 0.225 ≈ 2.192
        assert blob.shape == (1, 3, 1, 1)
        assert blob[0, 0, 0, 0] < 0  # R below mean
        assert blob[0, 2, 0, 0] > 1.5  # B well above mean
```

- [ ] **Step 2: Run tests — expect import failures**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python -m pytest ml/tests/detection/test_person_detector.py::TestRFDetrPostprocessing -v`
Expected: FAIL — `_sigmoid`, `_drop_no_object_logit`, `_cxcywh_to_xyxy`, `_imagenet_normalize` not yet defined

- [ ] **Step 3: Commit failing tests**

```bash
git add ml/tests/detection/test_person_detector.py
git commit -m "test(detection): add RF-DETR postprocessing unit tests (failing)"
```

---

## Task 2: Rewrite person_detector.py for RF-DETR

**Files:**

- Rewrite: `ml/src/detection/person_detector.py`

- [ ] **Step 1: Rewrite person_detector.py**

```python
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

# COCO class 0 = person
_PERSON_CLASS = 0

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

    COCO: (1, 300, 81) → (1, 300, 80). Last column suppresses
    all class scores if not removed.
    """
    return logits[..., :-1]


def _cxcywh_to_xyxy(
    boxes: np.ndarray, orig_w: int, orig_h: int
) -> np.ndarray:
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
            dummy = np.zeros(
                (1, 3, self._input_size, self._input_size), dtype=np.float32
            )
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
        # outputs[1]: (1, 300, 81) logits (80 classes + 1 no-object)
        boxes = outputs[0]  # (1, 300, 4)
        logits = outputs[1]  # (1, 300, 81)

        # Step 1: Drop no-object logit column
        logits = _drop_no_object_logit(logits)  # (1, 300, 80)

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
```

- [ ] **Step 2: Run postprocessing tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python -m pytest ml/tests/detection/test_person_detector.py::TestRFDetrPostprocessing -v`
Expected: PASS

- [ ] **Step 3: Run existing PersonDetector tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python -m pytest ml/tests/detection/test_person_detector.py::TestPersonDetector -v --timeout=60`
Expected: `test_detector_initialization` and `test_detector_custom_params` PASS (no model load). Slow tests (requiring model) skip if `yolov8n.onnx` missing.

- [ ] **Step 4: Commit**

```bash
git add ml/src/detection/person_detector.py ml/tests/detection/test_person_detector.py
git commit -m "feat(detection): replace YOLOv8n with RF-DETR ONNX inference"
```

---

## Task 3: Update gpu_server/server.py

**Files:**

- Modify: `ml/gpu_server/server.py:58,64,83-84`

- [ ] **Step 1: Replace YOLO paths with RF-DETR**

Change line 58:
```python
# Before:
YOLO_MODEL_PATH = _PROJECT_ROOT / "data/models/yolov8n.onnx"
# After:
RF_DETR_MODEL_PATH = _PROJECT_ROOT / "data/models/rf_detr_nano.onnx"
```

Change line 64 in `_R2_MODELS`:
```python
# Before:
(YOLO_MODEL_PATH, "models/yolov8n.onnx"),
# After:
(RF_DETR_MODEL_PATH, "models/rf_detr_nano.onnx"),
```

Change lines 83-84 in `_background_init`:
```python
# Before:
if not YOLO_MODEL_PATH.exists():
    raise OSError(f"Model not found: {YOLO_MODEL_PATH}")
# After:
if not RF_DETR_MODEL_PATH.exists():
    raise OSError(f"Model not found: {RF_DETR_MODEL_PATH}")
```

- [ ] **Step 2: Verify server starts (no GPU needed for syntax check)**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python -c "import ast; ast.parse(open('ml/gpu_server/server.py').read()); print('Syntax OK')"`

- [ ] **Step 3: Commit**

```bash
git add ml/gpu_server/server.py
git commit -m "feat(server): replace YOLO model path with RF-DETR"
```

---

## Task 4: Remove ultralytics dependency

**Files:**

- Modify: `ml/pyproject.toml:19`

- [ ] **Step 1: Remove ultralytics from dependencies**

In `ml/pyproject.toml`, delete line 19:
```python
# Delete this line:
    "ultralytics>=8.0.0",
```

- [ ] **Step 2: Verify no other references to ultralytics in ml/ code**

Run: `cd /home/michael/Github/skating-biomechanics-ml && grep -r "ultralytics" ml/src/ ml/tests/ ml/gpu_server/ ml/pyproject.toml`
Expected: No matches (or only in comments/docstrings being removed in Task 5)

- [ ] **Step 3: Verify uv sync resolves without ultralytics**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv sync 2>&1 | tail -5`

- [ ] **Step 4: Commit**

```bash
git add ml/pyproject.toml
git commit -m "chore(deps): remove ultralytics (AGPL-3.0) from ML dependencies"
```

---

## Task 5: Delete YOLO scripts and weights

**Files:**

- Delete: `ml/yolov8n.pt`
- Delete: `ml/scripts/create_yolo_subset.py`
- Delete: `ml/scripts/train_yolo26_pose.py`
- Delete: `ml/scripts/train_yolo26n_distill.py`

- [ ] **Step 1: Delete the files**

```bash
cd /home/michael/Github/skating-biomechanics-ml
rm ml/yolov8n.pt
rm ml/scripts/create_yolo_subset.py
rm ml/scripts/train_yolo26_pose.py
rm ml/scripts/train_yolo26n_distill.py
```

- [ ] **Step 2: Verify no import references to deleted files**

Run: `cd /home/michael/Github/skating-biomechanics-ml && grep -r "create_yolo_subset\|train_yolo26\|yolov8n\.pt" ml/src/ ml/tests/ ml/gpu_server/`
Expected: No matches

- [ ] **Step 3: Commit**

```bash
git add -A ml/yolov8n.pt ml/scripts/create_yolo_subset.py ml/scripts/train_yolo26_pose.py ml/scripts/train_yolo26n_distill.py
git commit -m "chore(detection): remove YOLO scripts and weights"
```

---

## Task 6: Update download script and manifest for RF-DETR

**Files:**

- Modify: `ml/scripts/download_ml_models.py`
- Modify: `data/models/models.manifest.json`

- [ ] **Step 1: Add RF-DETR entries to download_ml_models.py**

Add to `MODELS` dict (after `moganet_b` entry):

```python
    "rf_detr_nano": {
        "source": "hf",
        "repo_id": "PierreMarieCurie/rf-detr-onnx",
        "filename": "rf-detr-nano.onnx",
        "local_filename": "rf_detr_nano.onnx",
        "size_mb": "~120MB",
        "description": "RF-DETR-Nano person detector (384x384, Apache 2.0)",
    },
    "rf_detr_small": {
        "source": "manual",
        "local_filename": "rf_detr_small.onnx",
        "size_mb": "~128MB",
        "description": "RF-DETR-Small person detector (512x512, Apache 2.0) — requires export_rf_detr.py",
    },
    "rf_detr_medium": {
        "source": "manual",
        "local_filename": "rf_detr_medium.onnx",
        "size_mb": "~135MB",
        "description": "RF-DETR-Medium person detector (576x576, Apache 2.0) — requires export_rf_detr.py",
    },
```

Note: `PierreMarieCurie/rf-detr-onnx` has Nano only. Small/Medium need self-export (Task 10). If HF repo has different filename structure, adjust `filename` field accordingly after verifying the repo.

- [ ] **Step 2: Add RF-DETR entries to models.manifest.json**

Add to `models` dict:

```json
    "rf_detr_nano": {
      "version": "1.0.0",
      "sha256": null,
      "local_filename": "rf_detr_nano.onnx",
      "size_bytes": null,
      "source": "hf",
      "repo_id": "PierreMarieCurie/rf-detr-onnx",
      "filename": "rf-detr-nano.onnx"
    },
    "rf_detr_small": {
      "version": "1.0.0",
      "sha256": null,
      "local_filename": "rf_detr_small.onnx",
      "size_bytes": null,
      "source": "manual"
    },
    "rf_detr_medium": {
      "version": "1.0.0",
      "sha256": null,
      "local_filename": "rf_detr_medium.onnx",
      "size_bytes": null,
      "source": "manual"
    }
```

- [ ] **Step 3: Verify download script list works**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python ml/scripts/download_ml_models.py --list`
Expected: Shows `rf_detr_nano`, `rf_detr_small`, `rf_detr_medium` entries

- [ ] **Step 4: Commit**

```bash
git add ml/scripts/download_ml_models.py data/models/models.manifest.json
git commit -m "feat(models): add RF-DETR model download entries and manifest"
```

---

## Task 7: Write export_rf_detr.py script

**Files:**

- Create: `ml/scripts/export_rf_detr.py`

- [ ] **Step 1: Create ONNX export script**

```python
#!/usr/bin/env python3
"""Export RF-DETR PyTorch models to ONNX.

Requires: Python 3.12, rfdetr >=1.7.0
Usage:
    uv run python scripts/export_rf_detr.py --model nano
    uv run python scripts/export_rf_detr.py --model small
    uv run python scripts/export_rf_detr.py --model medium
    uv run python scripts/export_rf_detr.py --all
"""

import argparse
from pathlib import Path

import numpy as np

MODELS = {
    "nano": {"hub_id": "roboflow/rf-detr-nano", "size": 384},
    "small": {"hub_id": "roboflow/rf-detr-small", "size": 512},
    "medium": {"hub_id": "roboflow/rf-detr-medium", "size": 576},
}

OUTPUT_DIR = Path("data/models")


def export_model(name: str, config: dict) -> Path:
    """Export a single RF-DETR model to ONNX."""
    from rfdetr import RFDETRBase

    print(f"Loading {name} ({config['hub_id']})...")
    model = RFDETRBase.from_pretrained(config["hub_id"])

    size = config["size"]
    dummy_input = np.random.randn(1, 3, size, size).astype(np.float32)

    out_path = OUTPUT_DIR / f"rf_detr_{name}.onnx"
    print(f"Exporting to {out_path}...")

    model.to_onnx(
        str(out_path),
        opset=17,
        dynamic_batch=False,
    )

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Done: {out_path} ({size_mb:.1f} MB)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export RF-DETR to ONNX")
    parser.add_argument(
        "--model",
        choices=list(MODELS.keys()) + ["all"],
        default="all",
        help="Model variant to export",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.model == "all":
        for name, config in MODELS.items():
            export_model(name, config)
    else:
        export_model(args.model, MODELS[args.model])


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script syntax**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python -c "import ast; ast.parse(open('ml/scripts/export_rf_detr.py').read()); print('Syntax OK')"`

- [ ] **Step 3: Commit**

```bash
git add ml/scripts/export_rf_detr.py
git commit -m "feat(detection): add RF-DETR ONNX export script"
```

---

## Task 8: Write benchmark_detector.py script

**Files:**

- Create: `ml/scripts/benchmark_detector.py`

- [ ] **Step 1: Create benchmark script**

```python
#!/usr/bin/env python3
"""Benchmark RF-DETR variants (Nano/Small/Medium) on skating video.

Compares FPS, detection recall, and small-object detection quality
against YOLOv8n baseline.

Usage:
    uv run python scripts/benchmark_detector.py --video path/to/skating.mp4
    uv run python scripts/benchmark_detector.py --video path/to/skating.mp4 --models nano small
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from src.detection.person_detector import PersonDetector
from src.utils.video import extract_frames, get_video_meta


def benchmark_model(
    model_path: Path,
    input_size: int,
    frames: list[np.ndarray],
    confidence: float = 0.5,
) -> dict:
    """Run detection on all frames, return metrics."""
    detector = PersonDetector(
        model_path=str(model_path),
        confidence=confidence,
        input_size=input_size,
    )

    # Warmup
    detector.detect_frame(frames[0])

    detections: list[int] = []  # 1 = detected, 0 = miss
    times: list[float] = []

    for frame in frames:
        t0 = time.perf_counter()
        bbox = detector.detect_frame(frame)
        t1 = time.perf_counter()
        detections.append(1 if bbox is not None else 0)
        times.append(t1 - t0)

    recall = sum(detections) / len(detections) if detections else 0
    fps = 1.0 / (sum(times) / len(times)) if times else 0
    avg_ms = sum(times) / len(times) * 1000

    return {
        "model": model_path.stem,
        "recall": recall,
        "fps": fps,
        "avg_ms": avg_ms,
        "detected_frames": sum(detections),
        "total_frames": len(frames),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark RF-DETR on skating video")
    parser.add_argument("--video", type=Path, required=True, help="Path to skating video")
    parser.add_argument(
        "--models",
        nargs="+",
        choices=["nano", "small", "medium"],
        default=["nano", "small", "medium"],
        help="Model variants to benchmark",
    )
    parser.add_argument("--max-frames", type=int, default=100, help="Max frames to process")
    parser.add_argument("--confidence", type=float, default=0.5, help="Detection confidence")
    args = parser.parse_args()

    # Read frames
    frames = []
    for i, frame in enumerate(extract_frames(args.video)):
        if i >= args.max_frames:
            break
        frames.append(frame)

    print(f"Video: {args.video} ({len(frames)} frames)")
    print(f"Resolution: {frames[0].shape[1]}x{frames[0].shape[0]}")
    print()

    model_configs = {
        "nano": {"path": Path("data/models/rf_detr_nano.onnx"), "size": 384},
        "small": {"path": Path("data/models/rf_detr_small.onnx"), "size": 512},
        "medium": {"path": Path("data/models/rf_detr_medium.onnx"), "size": 576},
    }

    results = []
    for name in args.models:
        config = model_configs[name]
        if not config["path"].exists():
            print(f"SKIP {name}: {config['path']} not found")
            continue
        print(f"Benchmarking {name} ({config['size']}x{config['size']})...")
        result = benchmark_model(config["path"], config["size"], frames, args.confidence)
        results.append(result)
        print(f"  Recall: {result['recall']:.1%} | FPS: {result['fps']:.1f} | Avg: {result['avg_ms']:.1f}ms")

    # Summary table
    print("\n| Model | Recall | FPS | Avg ms |")
    print("|-------|--------|-----|--------|")
    for r in results:
        print(f"| {r['model']} | {r['recall']:.1%} | {r['fps']:.1f} | {r['avg_ms']:.1f} |")

    # Decision criteria
    print("\nSuccess criteria: recall >= YOLOv8n baseline, FPS >= 25")
    for r in results:
        status = "PASS" if r["fps"] >= 25 else "FAIL (FPS)"
        print(f"  {r['model']}: {status}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script syntax**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python -c "import ast; ast.parse(open('ml/scripts/benchmark_detector.py').read()); print('Syntax OK')"`

- [ ] **Step 3: Commit**

```bash
git add ml/scripts/benchmark_detector.py
git commit -m "feat(detection): add RF-DETR benchmark script for skating video"
```

---

## Task 9: Add detection stride + interpolation to pose_extractor.py

**Files:**

- Modify: `ml/src/pose_estimation/pose_extractor.py:115`
- Modify: `ml/src/pose_estimation/batch_extractor.py:108`

- [ ] **Step 1: Add detection stride parameter and interpolation to PoseExtractor**

Add `detection_stride` parameter to `PoseExtractor.__init__`:

```python
def __init__(
    self,
    model_path: str = "data/models/moganet/moganet_b_ap2d_384x288.onnx",
    tracking_backend: str = "custom",
    tracking_mode: str = "auto",
    conf_threshold: float = 0.3,
    output_format: str = "normalized",
    frame_skip: int = 1,
    detection_stride: int = 1,
    device: str = "auto",
) -> None:
    # ... existing init code ...
    self._detection_stride = max(1, detection_stride)
```

Add interpolation helper at module level (after imports):

```python
def _lerp_bbox(
    bboxes: dict[int, "BoundingBox | None"], frame_idx: int
) -> "BoundingBox | None":
    """Linear interpolation of bounding box for non-detected frames."""
    # Find nearest detected frames before and after
    prev_idx = None
    for i in range(frame_idx - 1, -1, -1):
        if i in bboxes and bboxes[i] is not None:
            prev_idx = i
            break
    next_idx = None
    for i in range(frame_idx + 1, max(bboxes.keys()) + 1):
        if i in bboxes and bboxes[i] is not None:
            next_idx = i
            break
    if prev_idx is None and next_idx is None:
        return None
    if prev_idx is None:
        return bboxes[next_idx]
    if next_idx is None:
        return bboxes[prev_idx]
    t = (frame_idx - prev_idx) / (next_idx - prev_idx)
    prev_box = bboxes[prev_idx]
    next_box = bboxes[next_idx]
    from ..types import BoundingBox
    return BoundingBox(
        x1=prev_box.x1 + t * (next_box.x1 - prev_box.x1),
        y1=prev_box.y1 + t * (next_box.y1 - prev_box.y1),
        x2=prev_box.x2 + t * (next_box.x2 - prev_box.x2),
        y2=prev_box.y2 + t * (next_box.y2 - prev_box.y2),
        confidence=min(prev_box.confidence, next_box.confidence),
    )
```

Modify `_extract_batch` to use detection stride — in the detection loop (around line 425), change:

```python
# Before:
for frame in frames_to_process:
    crops, bboxes = self._detect_and_crop(frame)

# After:
all_detection_results: dict[int, BoundingBox | None] = {}
for frame_i, frame in enumerate(frames_to_process):
    if frame_i % self._detection_stride == 0:
        detection = self._person_detector.detect_frame(frame)
        all_detection_results[frame_i] = detection
    else:
        all_detection_results[frame_i] = None  # interpolated later

# Interpolate missing detections
for frame_i in range(len(frames_to_process)):
    if all_detection_results[frame_i] is None:
        all_detection_results[frame_i] = _lerp_bbox(all_detection_results, frame_i)

# Now crop using interpolated bboxes
for frame_i, frame in enumerate(frames_to_process):
    det = all_detection_results[frame_i]
    if det is None:
        frame_detection_counts.append(0)
        continue
    # ... existing crop logic using det ...
```

- [ ] **Step 2: Add same stride to BatchPoseExtractor.__init__**

In `batch_extractor.py`, add `detection_stride: int = 1` parameter and apply same pattern in `extract_video_tracked`.

- [ ] **Step 3: Run existing tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python -m pytest ml/tests/pose_estimation/ -v --timeout=120 -x`
Expected: PASS (default `detection_stride=1` preserves behavior)

- [ ] **Step 4: Commit**

```bash
git add ml/src/pose_estimation/pose_extractor.py ml/src/pose_estimation/batch_extractor.py
git commit -m "feat(pose): add detection stride + bbox interpolation for RF-DETR throughput"
```

---

## Task 10: Update existing tests for RF-DETR

**Files:**

- Modify: `ml/tests/detection/test_person_detector.py`

- [ ] **Step 1: Update TestPersonDetector docstrings for RF-DETR**

```python
@pytest.mark.slow
class TestPersonDetector:
    """Test PersonDetector with RF-DETR ONNX model."""

    def test_detector_initialization(self):
        """Should initialize with default parameters."""
        detector = PersonDetector()
        assert detector._confidence == 0.5
        assert detector._input_size == 384  # RF-DETR-Nano default
        assert detector._session is None  # Lazy load

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
```

- [ ] **Step 2: Run all detection tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python -m pytest ml/tests/detection/ -v --timeout=120`
Expected: All unit tests PASS. Slow tests skip if RF-DETR model not yet downloaded.

- [ ] **Step 3: Commit**

```bash
git add ml/tests/detection/test_person_detector.py
git commit -m "test(detection): update PersonDetector tests for RF-DETR"
```

---

## Task 11: Verify full pipeline

**Files:**

- No file changes — verification only

- [ ] **Step 1: Run full test suite**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python -m pytest ml/tests/ --no-cov --timeout=120 -x`
Expected: All tests PASS (slow/inference tests may skip without GPU)

- [ ] **Step 2: Run lint**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run ruff check ml/src/`
Expected: No errors

- [ ] **Step 3: Run type check**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run basedpyright ml/src/ --level error`
Expected: No errors

- [ ] **Step 4: Verify no ultralytics references remain**

Run: `cd /home/michael/Github/skating-biomechanics-ml && grep -r "ultralytics\|yolov8\|YOLO" ml/src/ ml/tests/ ml/gpu_server/ --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"`
Expected: No matches (all YOLO references removed)

- [ ] **Step 5: Commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix(detection): address pipeline verification issues"
```

---

## Task 12: Export and benchmark RF-DETR models

**Files:**

- No file changes — this is a manual verification step

- [ ] **Step 1: Download Nano ONNX from HuggingFace**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python ml/scripts/download_ml_models.py --model rf_detr_nano`

- [ ] **Step 2: Export Small and Medium ONNX (Python 3.12 + rfdetr)**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python ml/scripts/export_rf_detr.py --model small` and `--model medium`

Note: May require separate venv with Python 3.12 and `pip install rfdetr>=1.7.0`. Export is a one-time operation — resulting ONNX files go to `data/models/`.

- [ ] **Step 3: Run benchmark on skating video**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run python ml/scripts/benchmark_detector.py --video <path-to-skating-video> --models nano small medium`

- [ ] **Step 4: Select model based on benchmark results**

Decision criteria: recall on small objects >= YOLOv8n baseline, FPS >= 25 on RTX 3050 Ti. Choose smallest model meeting criteria.

Update `_DEFAULT_MODEL` in `person_detector.py` if not Nano:

```bash
git add ml/src/detection/person_detector.py
git commit -m "feat(detection): set RF-DETR-<variant> as default detector based on benchmark"
```

---

## Dependency Graph

```
Task 1 (failing tests)
  ↓
Task 2 (rewrite person_detector.py) — depends on Task 1
  ↓
Task 3 (server.py) — depends on Task 2
Task 4 (remove ultralytics) — independent, can parallel with Task 3
Task 5 (delete YOLO files) — independent, can parallel with Task 3-4
Task 6 (download + manifest) — independent, can parallel with Task 3-5
Task 7 (export script) — independent, can parallel with Task 3-6
Task 8 (benchmark script) — independent, can parallel with Task 3-7
  ↓
Task 9 (detection stride) — depends on Task 2
Task 10 (update tests) — depends on Task 2
  ↓
Task 11 (full pipeline verify) — depends on all above
  ↓
Task 12 (export + benchmark) — depends on Task 7, 8, 11
```

## Parallelization Wave Plan

| Wave | Tasks | Rationale |
|------|-------|-----------|
| 1 | Task 1 | Foundation: failing tests |
| 2 | Task 2 | Core: rewrite detector |
| 3 | Task 3, 4, 5, 6, 7, 8 | All independent of each other |
| 4 | Task 9, 10 | Depend on Task 2 |
| 5 | Task 11 | Full verification |
| 6 | Task 12 | Manual: export + benchmark (requires GPU + skating video) |
