"""GET /api/models — check which ML models are available on disk."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence  # noqa: TC003
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from litestar import Controller, get
from pydantic import BaseModel

from app.auth.deps import CurrentUser
from app.config import get_settings

logger = logging.getLogger(__name__)


# #777: config-based path instead of fragile parent⁴ chain
@lru_cache(maxsize=1)
def _get_models_dir() -> Path:
    return Path(get_settings().app.data_dir) / "models"


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
    # #778: size_mb removed from anonymous response (infra leak)


class ModelsController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["models"]

    @get("")
    async def list_models(self, user: CurrentUser) -> list[ModelStatus]:
        # #775: auth required (removed /v1/models from JWTAuth.exclude)
        # #776: async filesystem I/O via to_thread
        models_dir = _get_models_dir()
        results = []
        for model_id, filename in _MODEL_FILES.items():
            path = models_dir / filename
            available = await asyncio.to_thread(path.exists)
            results.append(ModelStatus(id=model_id, available=available))
        return results
