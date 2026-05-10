"""Batch MogaNet-B ONNX inference — direct ONNX Runtime calls for top-down pose estimation.

Provides preprocessing (letterbox resize, normalization), heatmap decoding,
keypoint rescaling, and the MogaNetBatch class for batched inference.

MogaNet-B specifics:
    - Input size: 384x288 (WxH)
    - Normalization: ImageNet mean/std
    - Output: 17-channel heatmaps decoded via argmax
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import TracebackType

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Model input dimensions (W, H)
MOGANET_INPUT_SIZE = (384, 288)

# ImageNet normalization constants
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preprocess_crops(
    crops: list[np.ndarray],
    input_size: tuple[int, int] = MOGANET_INPUT_SIZE,
) -> np.ndarray:
    """Preprocess cropped person images for MogaNet-B inference.

    For each crop: resize with aspect ratio preservation, pad to input_size,
    convert BGR to RGB, normalize with ImageNet mean/std, transpose to CHW.

    Args:
        crops: List of BGR crop images (H, W, 3) uint8.
        input_size: (W, H) model input dimensions.

    Returns:
        Batch tensor (B, 3, H, W) float32 normalized and ready for ONNX.
    """
    batch_size = len(crops)
    input_w, input_h = input_size

    if batch_size == 0:
        return np.zeros((0, 3, input_h, input_w), dtype=np.float32)

    batch_tensor = np.zeros((batch_size, 3, input_h, input_w), dtype=np.float32)

    for i, crop in enumerate(crops):
        crop_h, crop_w = crop.shape[:2]

        # Aspect-ratio-preserving scale
        scale = min(input_w / crop_w, input_h / crop_h)
        new_w = int(crop_w * scale)
        new_h = int(crop_h * scale)

        # Resize
        resized = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # Pad to input_size with zeros
        # (after normalization: (0 - mean)/std ≈ -2.12)
        padded = np.zeros((input_h, input_w, 3), dtype=np.uint8)
        pad_top = (input_h - new_h) // 2
        pad_left = (input_w - new_w) // 2
        padded[pad_top : pad_top + new_h, pad_left : pad_left + new_w] = resized

        # BGR -> RGB, normalize, transpose HWC -> CHW
        rgb = padded[..., ::-1]  # BGR to RGB
        normalized = rgb.astype(np.float32) / 255.0
        normalized = (normalized - MEAN) / STD
        batch_tensor[i] = np.ascontiguousarray(normalized.transpose(2, 0, 1), dtype=np.float32)

    return batch_tensor


def decode_heatmaps(
    heatmaps: np.ndarray,
    input_size: tuple[int, int] = MOGANET_INPUT_SIZE,
) -> tuple[np.ndarray, np.ndarray]:
    """Decode argmax positions from heatmaps and scale to model input space.

    Args:
        heatmaps: (B, 17, H_hm, W_hm) float32 heatmaps from the model.
        input_size: (W, H) model input dimensions for coordinate scaling.

    Returns:
        (keypoints, scores) where:
            keypoints: (B, 17, 2) pixel coordinates in model input space.
            scores: (B, 17) confidence scores (heatmap max values).
    """
    batch_size, num_joints, hm_h, hm_w = heatmaps.shape
    input_w, input_h = input_size

    # Flatten and argmax
    flat = heatmaps.reshape(batch_size, num_joints, -1)
    flat_max = flat.max(axis=2)
    flat_idx = flat.argmax(axis=2)

    # Unravel to (y, x) in heatmap space
    y_hm = flat_idx // hm_w
    x_hm = flat_idx % hm_w

    # Scale to model input space
    x_input = x_hm.astype(np.float32) * (input_w / hm_w)
    y_input = y_hm.astype(np.float32) * (input_h / hm_h)

    keypoints = np.stack([x_input, y_input], axis=2)  # (B, 17, 2)
    scores = flat_max  # (B, 17)

    return keypoints, scores


def rescale_keypoints(
    keypoints: np.ndarray,
    crops: list[np.ndarray],
    bboxes: list[tuple[int, int, int, int]],
    input_size: tuple[int, int] = MOGANET_INPUT_SIZE,
) -> np.ndarray:
    """Undo letterbox padding and translate by bbox origin to original frame coords.

    Args:
        keypoints: (B, 17, 2) keypoints in model input space.
        crops: List of BGR crop images (H, W, 3) uint8.
        bboxes: List of (x1, y1, x2, y2) bounding boxes in original frame coords.
        input_size: (W, H) model input dimensions.

    Returns:
        (B, 17, 2) keypoints in original frame pixel coordinates.
    """
    batch_size = keypoints.shape[0]
    input_w, input_h = input_size
    rescaled = np.zeros_like(keypoints)

    for i in range(batch_size):
        crop_h, crop_w = crops[i].shape[:2]
        x1, y1, _x2, _y2 = bboxes[i]

        # Undo letterbox: must match exact forward computation in preprocess_crops
        scale = min(input_w / crop_w, input_h / crop_h)
        new_w = int(crop_w * scale)
        new_h = int(crop_h * scale)
        pad_left = (input_w - new_w) // 2
        pad_top = (input_h - new_h) // 2

        # Reverse padding and scaling, then translate by bbox origin
        rescaled[i, :, 0] = (keypoints[i, :, 0] - pad_left) / scale + x1
        rescaled[i, :, 1] = (keypoints[i, :, 1] - pad_top) / scale + y1

    return rescaled


class MogaNetBatch:
    """Batch MogaNet-B ONNX inference for top-down pose estimation.

    Args:
        model_path: Path to the MogaNet-B ONNX model file.
        device: "auto", "cpu", or "cuda".
        score_thr: Minimum keypoint confidence threshold (scores below this are zeroed).
    """

    def __init__(
        self,
        model_path: str = "data/models/moganet/moganet_b_ap2d_384x288.onnx",
        device: str = "auto",
        score_thr: float = 0.3,
    ) -> None:
        """Initialize MogaNetBatch.

        Args:
            model_path: Path to MogaNet-B ONNX model.
            device: Device — "auto", "cpu", "cuda".
            score_thr: Keypoint score threshold.

        Raises:
            FileNotFoundError: If the model file does not exist.
        """
        self._score_thr = score_thr

        # Resolve device
        if device == "auto":
            try:
                import onnxruntime

                if "CUDAExecutionProvider" in onnxruntime.get_available_providers():
                    self._device = "cuda"
                else:
                    self._device = "cpu"
            except ImportError:
                self._device = "cpu"
        else:
            self._device = device

        # Verify model exists
        model_path_obj = Path(model_path)
        if not model_path_obj.exists():
            raise FileNotFoundError(
                f"MogaNet-B model not found: {model_path_obj}\n"
                f"Download models with: uv run python ml/scripts/download_ml_models.py"
            )

        # Load ONNX model
        import onnxruntime

        opts = onnxruntime.SessionOptions()
        opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.enable_mem_pattern = True
        opts.enable_mem_reuse = True
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 1

        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if self._device == "cuda"
            else ["CPUExecutionProvider"]
        )
        self._session = onnxruntime.InferenceSession(
            str(model_path_obj),
            sess_options=opts,
            providers=providers,
        )

        # Get input/output names
        self._input_name = self._session.get_inputs()[0].name
        self._output_names = [o.name for o in self._session.get_outputs()]

        # Warm-up inference
        dummy = np.zeros((1, 3, MOGANET_INPUT_SIZE[1], MOGANET_INPUT_SIZE[0]), dtype=np.float32)
        self._session.run(self._output_names, {self._input_name: dummy})

        logger.info(
            "MogaNetBatch initialized: model=%s, device=%s, score_thr=%.2f",
            model_path_obj.name,
            self._device,
            self._score_thr,
        )

    _MAX_GPU_BATCH = 32

    def infer_batch(
        self,
        crops: list[np.ndarray],
        bboxes: list[tuple[int, int, int, int]],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run batch inference on cropped person images.

        Preprocesses crops, runs ONNX inference in chunks of _MAX_GPU_BATCH,
        decodes heatmaps, rescales keypoints to original frame coordinates,
        and applies score threshold.

        Args:
            crops: List of BGR crop images (H, W, 3) uint8.
            bboxes: List of (x1, y1, x2, y2) bounding boxes in original frame coords.

        Returns:
            (keypoints, scores) where:
                keypoints: (B, 17, 2) pixel coords in original frame.
                scores: (B, 17) keypoint confidence scores.
        """
        if not crops:
            return (
                np.zeros((0, 17, 2), dtype=np.float32),
                np.zeros((0, 17), dtype=np.float32),
            )

        if len(crops) != len(bboxes):
            raise ValueError(
                f"crops and bboxes must have same length, got {len(crops)} and {len(bboxes)}"
            )

        # Chunked inference to avoid GPU OOM
        all_keypoints = []
        all_scores = []
        chunk_size = self._MAX_GPU_BATCH
        for start in range(0, len(crops), chunk_size):
            end = min(start + chunk_size, len(crops))
            chunk_crops = crops[start:end]
            chunk_bboxes = bboxes[start:end]

            batch_tensor = preprocess_crops(chunk_crops)
            outputs = self._session.run(
                self._output_names,
                {self._input_name: batch_tensor},
            )
            heatmaps = np.asarray(outputs[0])
            keypoints, scores = decode_heatmaps(heatmaps)
            keypoints = rescale_keypoints(keypoints, chunk_crops, chunk_bboxes)
            all_keypoints.append(keypoints)
            all_scores.append(scores)

        keypoints = np.concatenate(all_keypoints, axis=0)
        scores = np.concatenate(all_scores, axis=0)

        # Apply score threshold without mutating raw scores
        thresholded_scores = scores.copy()
        thresholded_scores[thresholded_scores < self._score_thr] = 0.0

        return keypoints, thresholded_scores

    def close(self) -> None:
        """Release ONNX session resources."""
        if hasattr(self, "_session"):
            del self._session

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
