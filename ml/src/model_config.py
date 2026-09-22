"""Explicit model locations and startup validation for inference."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ModelConfigurationError(RuntimeError):
    """Required inference models are not available."""


@dataclass(frozen=True)
class ModelConfig:
    """Canonical model paths for the 2D and optional 3D pipeline stages."""

    root: Path
    moganet: Path
    rf_detr: Path
    tcpformer: Path | None
    tas: Path | None

    @classmethod
    def from_root(cls, root: Path | str | None = None) -> ModelConfig:
        """Build config from a project root and optional environment overrides."""
        project_root = Path(
            root or os.environ.get("PROJECT_ROOT") or Path(__file__).resolve().parents[2]
        ).resolve()

        def model_path(env_name: str, relative: str) -> Path | None:
            if env_name in os.environ:
                value = os.environ[env_name].strip()
                if not value:
                    return None
                path = Path(value)
            else:
                path = Path(relative)
            return path if path.is_absolute() else project_root / path

        def required_model_path(env_name: str, relative: str) -> Path:
            path = model_path(env_name, relative)
            if path is None:
                raise ValueError(f"{env_name} cannot be empty")
            return path

        moganet = required_model_path(
            "SKATELAB_MOGANET_MODEL",
            "data/models/moganet_b_ap2d_384x288.onnx",
        )
        rf_detr = required_model_path("SKATELAB_RF_DETR_MODEL", "data/models/rf_detr_nano.onnx")

        return cls(
            root=project_root,
            moganet=moganet,
            rf_detr=rf_detr,
            tcpformer=model_path(
                "SKATELAB_TCPFORMER_MODEL",
                "data/models/tcpformer/TCPFormer_ap3d_81_fp16.onnx",
            ),
            tas=model_path(
                "SKATELAB_TAS_MODEL",
                "data/models/tas/bigr_refiner_best.onnx",
            ),
        )

    @classmethod
    def default(cls) -> ModelConfig:
        """Build the config using the current project/container environment."""
        return cls.from_root()

    def validate(self, *, require_3d: bool = False, require_tas: bool = False) -> list[str]:
        """Validate required models and return explicit optional-stage warnings."""
        required: dict[str, Path | None] = {"moganet": self.moganet, "rf_detr": self.rf_detr}
        if require_3d:
            required["tcpformer"] = self.tcpformer
        if require_tas:
            required["tas"] = self.tas

        missing = [name for name, path in required.items() if path is None or not path.is_file()]
        if missing:
            details = ", ".join(f"{name}={getattr(self, name)!s}" for name in missing)
            raise ModelConfigurationError(f"Required model(s) missing: {details}")

        warnings: list[str] = []
        if self.tcpformer is None or not self.tcpformer.is_file():
            warnings.append(f"3D disabled: TCPFormer model not found at {self.tcpformer}")
        return warnings

    def as_dict(self) -> dict[str, str | None]:
        """Return resolved paths for logs and machine-readable results."""
        return {
            "moganet": str(self.moganet),
            "rf_detr": str(self.rf_detr),
            "tcpformer": str(self.tcpformer) if self.tcpformer else None,
            "tas": str(self.tas) if self.tas else None,
        }
