"""GET /api/models — check which ML models are available on disk."""

from __future__ import annotations

from collections.abc import Sequence  # noqa: TC003
from pathlib import Path
from typing import ClassVar

from litestar import Controller, get
from pydantic import BaseModel

_MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "models"

_MODEL_FILES: dict[str, str] = {
    "lift_3d": "depth_anything_v2_small.onnx",
    "optical_flow": "neuflowv2_mixed.onnx",
    "segment": "sam2/vision_encoder.onnx",
    "foot_track": "foot_tracker.onnx",
    "matting": "rvm_mobilenetv3.onnx",
    "inpainting": "lama_fp32.onnx",
}


class ModelStatus(BaseModel):
    id: str
    available: bool
    size_mb: float | None = None


class ModelsController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["models"]

    @get("")
    async def list_models(self) -> list[ModelStatus]:
        results = []
        for model_id, filename in _MODEL_FILES.items():
            path = _MODELS_DIR / filename
            available = path.exists()
            size_mb = round(path.stat().st_size / (1024 * 1024), 1) if available else None
            results.append(ModelStatus(id=model_id, available=available, size_mb=size_mb))
        return results
