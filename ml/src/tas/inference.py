"""End-to-end TAS inference: poses → ONNX BiGRU(+Refiner) coarse → segments → ONNX/CNN fine."""

from pathlib import Path

import numpy as np
import onnxruntime as ort

from ..device import DeviceConfig
from .classifier import SegmentClassifier, extract_segment_features

# Per-element minimum duration in seconds
MIN_DURATION = {
    "Jump": 0.5,
    "Spin": 2.0,
    "Step": 3.0,
}


class TASElementSegmenter:
    """ONNX-based element segmenter: BiGRU+Refiner coarse → segment extraction → fine classifier.

    Uses ONNX Runtime for inference — no PyTorch dependency at runtime.
    Models are exported from PyTorch via torch.onnx.export during training.
    """

    def __init__(
        self,
        model_path: Path | str,
        classifier_path: Path | str | None = None,
        device: str | None = None,
        min_segment_duration: float = 0.5,
    ) -> None:
        cfg = DeviceConfig(device=device) if device else DeviceConfig.default()

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 2
        self.session = ort.InferenceSession(
            str(model_path),
            sess_options=opts,
            providers=cfg.onnx_providers,
        )

        self.classifier: SegmentClassifier | None = None
        if classifier_path is not None:
            import joblib

            self.classifier = joblib.load(classifier_path)

        self.min_segment_duration = min_segment_duration
        self.id2label = {0: "None", 1: "Jump", 2: "Spin", 3: "Step"}

        # Cache input/output names for faster inference
        self._input_names = [inp.name for inp in self.session.get_inputs()]
        self._output_names = [out.name for out in self.session.get_outputs()]

    def segment(
        self,
        poses: np.ndarray,  # (T, 17, 2) normalized H3.6M
        fps: float = 30.0,
    ) -> list[dict]:
        """Segment poses into elements with per-type minimum duration filtering."""
        T = poses.shape[0]
        # ONNX model expects (B, T, 17, 2) — model flattens internally
        poses_batch = poses.reshape(1, T, 17, 2).astype(np.float32)
        lengths = np.array([T], dtype=np.int64)

        feeds = dict(zip(self._input_names, [poses_batch, lengths], strict=True))
        logits = self.session.run(self._output_names, feeds)[0]  # (1, T, 4)
        pred_labels = logits[0].argmax(axis=-1)  # (T,)

        return self._extract_segments(pred_labels, poses, fps)

    def _extract_segments(
        self,
        labels: np.ndarray,
        poses: np.ndarray,
        fps: float,
    ) -> list[dict]:
        """Extract contiguous segments with per-type minimum duration filter."""
        segments: list[dict] = []
        if len(labels) == 0:
            return segments

        current = int(labels[0])
        start = 0
        for i in range(1, len(labels)):
            if int(labels[i]) != current:
                if current != 0:
                    seg = self._try_add_segment(current, start, i, poses, fps)
                    if seg is not None:
                        segments.append(seg)
                current = int(labels[i])
                start = i

        # Last segment
        if current != 0:
            seg = self._try_add_segment(current, start, len(labels), poses, fps)
            if seg is not None:
                segments.append(seg)

        return segments

    def _try_add_segment(
        self,
        label: int,
        start: int,
        end: int,
        poses: np.ndarray,
        fps: float,
    ) -> dict | None:
        """Add segment if it passes per-type minimum duration check."""
        element_type = self.id2label[label]
        duration = (end - start) / fps
        min_dur = MIN_DURATION.get(element_type, self.min_segment_duration)
        if duration < min_dur:
            return None

        seg_poses = poses[start:end]
        confidence = 1.0

        if self.classifier is not None and label in (1, 2, 3):
            features = extract_segment_features(seg_poses, fps)
            element_type, confidence = self.classifier.predict(features)

        return {
            "element_type": element_type,
            "start": start,
            "end": end - 1,
            "confidence": confidence,
        }


__all__ = ["TASElementSegmenter"]
