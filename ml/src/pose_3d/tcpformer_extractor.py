"""TCPFormer 3D pose lifter wrapper (ONNX Runtime).

Memory-Induced Transformer for monocular 3D human pose estimation.
Uses 81-frame temporal window with ONNX Runtime — no PyTorch dependency.

Reference: https://github.com/AsukaCamellia/TCPFormer
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .model_downloader import resolve_model
from .onnx_extractor import ONNXPoseExtractor

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class TCPFormerExtractor:
    """3D pose lifting using TCPFormer (ONNX Runtime).

    High-accuracy 3D pose estimation with ~105MB FP16 model.
    Uses 81-frame temporal window for smooth 3D trajectories.

    Model is resolved automatically — searches local paths first,
    then downloads from S3 if credentials are configured.
    """

    TEMPORAL_WINDOW = 81

    def __init__(
        self,
        model_path: Path | str | None = None,
        device: str = "auto",
    ) -> None:
        """Initialize TCPFormer 3D pose lifter.

        Args:
            model_path: Path to TCPFormer .onnx model file.
                If None, resolves automatically (local search → S3 download).
            device: "cuda", "cpu", or "auto" (default).
        """
        if model_path is not None:
            model_path = Path(model_path)
        else:
            model_path = resolve_model("tcpformer", device=device)

        if model_path is None:
            raise FileNotFoundError(
                "TCPFormer model not found and S3 download unavailable. "
                "Place model at data/models/tcpformer/TCPFormer_ap3d_81_fp16.onnx "
                "or configure S3 credentials for auto-download."
            )

        self.model_path = model_path
        self._onnx = ONNXPoseExtractor(model_path, device=device)

    def extract_sequence(
        self,
        poses_2d: NDArray[np.float32],
    ) -> NDArray[np.float32]:
        """Extract 3D poses from 2D pose sequence.

        Args:
            poses_2d: (N, 17, 2) or (N, 17, 3) array in H3.6M format

        Returns:
            poses_3d: (N, 17, 3) array with x, y, z coordinates
        """
        return self._onnx.estimate_3d(poses_2d[:, :, :2])

    def reset(self) -> None:
        """Reset internal state (ONNX extractor is stateless — no-op)."""
