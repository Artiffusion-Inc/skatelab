"""End-to-end TAS inference: poses → BiGRU coarse → segments → RF fine.

Replaces rule-based ElementSegmenter.
"""

from pathlib import Path

import numpy as np
import torch

from ..device import DeviceConfig
from .classifier import SegmentClassifier, extract_segment_features
from .model import BiGRUTAS


class TASElementSegmenter:
    """ML-based element segmenter: BiGRU coarse → segment extraction → RF fine."""

    def __init__(
        self,
        model_path: Path | str,
        classifier_path: Path | str | None = None,
        device: str | None = None,
        min_segment_duration: float = 0.5,
    ) -> None:
        cfg = DeviceConfig(device=device) if device else DeviceConfig.default()
        self.device = torch.device(cfg.device)  # type: ignore[reportPrivateImportUsage]
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=True)
        cfg = checkpoint.get("config", {})
        self.model = BiGRUTAS(
            hidden_dim=cfg.get("hidden_dim", 128),
            num_layers=cfg.get("num_layers", 2),
            dropout=cfg.get("dropout", 0.3),
        )
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()

        self.classifier: SegmentClassifier | None = None
        if classifier_path is not None:
            import joblib

            self.classifier = joblib.load(classifier_path)

        self.min_segment_duration = min_segment_duration
        self.id2label = {0: "None", 1: "Jump", 2: "Spin", 3: "Step"}

    def segment(
        self,
        poses: np.ndarray,  # (T, 17, 2) normalized H3.6M
        fps: float = 30.0,
    ) -> list[dict]:
        """Segment poses into elements."""
        T = poses.shape[0]
        poses_tensor = torch.from_numpy(poses).unsqueeze(0).to(self.device)  # type: ignore[reportPrivateImportUsage]
        lengths = torch.tensor([T], dtype=torch.long)  # type: ignore[reportPrivateImportUsage]

        with torch.no_grad():
            logits = self.model(poses_tensor, lengths)
        pred_labels = logits.argmax(dim=-1).cpu().numpy()[0]  # (T,)

        return self._extract_segments(pred_labels, poses, fps)

    def _extract_segments(
        self,
        labels: np.ndarray,
        poses: np.ndarray,
        fps: float,
    ) -> list[dict]:
        """Extract contiguous segments from frame-wise labels."""
        segments: list[dict] = []
        if len(labels) == 0:
            return segments

        current = int(labels[0])
        start = 0
        for i in range(1, len(labels)):
            if int(labels[i]) != current:
                if current != 0:
                    duration = (i - start) / fps
                    if duration >= self.min_segment_duration:
                        seg_poses = poses[start:i]
                        element_type = self.id2label[current]
                        confidence = 1.0

                        # RF classification if available
                        if self.classifier is not None and current in (1, 2, 3):
                            features = extract_segment_features(seg_poses, fps)
                            element_type, confidence = self.classifier.predict(features)

                        segments.append(
                            {
                                "element_type": element_type,
                                "start": start,
                                "end": i - 1,
                                "confidence": confidence,
                            }
                        )
                current = int(labels[i])
                start = i

        # Last segment
        if current != 0:
            duration = (len(labels) - start) / fps
            if duration >= self.min_segment_duration:
                seg_poses = poses[start:]
                element_type = self.id2label[current]
                confidence = 1.0
                if self.classifier is not None and current in (1, 2, 3):
                    features = extract_segment_features(seg_poses, fps)
                    element_type, confidence = self.classifier.predict(features)
                segments.append(
                    {
                        "element_type": element_type,
                        "start": start,
                        "end": len(labels) - 1,
                        "confidence": confidence,
                    }
                )

        return segments


__all__ = ["TASElementSegmenter"]
