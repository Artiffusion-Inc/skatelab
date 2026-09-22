"""Stable, JSON-safe result contract for ML inference consumers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np

RESULT_SCHEMA_VERSION = "skatelab.inference.v1"


def _json_safe(value: Any) -> Any:
    """Convert numpy values and non-finite floats to strict-JSON values."""
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def build_annotations(
    poses_norm: np.ndarray,
    confidence: np.ndarray,
    frame_indices: np.ndarray,
    *,
    fps: float,
) -> dict[str, Any]:
    """Build per-frame H3.6M overlay data in normalized video coordinates."""
    if poses_norm.ndim != 3 or poses_norm.shape[1:] != (17, 2):
        raise ValueError(f"poses_norm must have shape (N, 17, 2), got {poses_norm.shape}")
    if confidence.shape != poses_norm.shape[:2]:
        raise ValueError(
            f"confidence must have shape {poses_norm.shape[:2]}, got {confidence.shape}"
        )
    if frame_indices.shape != (len(poses_norm),):
        raise ValueError(
            f"frame_indices must have shape {(len(poses_norm),)}, got {frame_indices.shape}"
        )
    if not math.isfinite(float(fps)) or fps <= 0:
        raise ValueError(f"fps must be finite and > 0, got {fps}")
    if len(frame_indices) > 1 and np.any(np.diff(frame_indices) <= 0):
        raise ValueError("frame_indices must be strictly increasing")

    def point_list(point: np.ndarray) -> list[float] | None:
        if not np.all(np.isfinite(point)):
            return None
        return [
            float(np.clip(point[0], 0.0, 1.0)),
            float(np.clip(point[1], 0.0, 1.0)),
        ]

    poses = [[point_list(point) for point in frame] for frame in poses_norm]
    confs = [
        [
            min(1.0, max(0.0, float(value))) if math.isfinite(float(value)) else None
            for value in frame
        ]
        for frame in confidence
    ]
    indices = [int(value) for value in frame_indices]
    return {
        "keypoint_format": "h36m17",
        "coordinate_space": "normalized",
        "frame_indices": indices,
        "timestamps_s": [round(index / fps, 6) for index in indices],
        "poses": poses,
        "confidence": confs,
    }


def result_from_report(
    report: Any,
    *,
    timings: dict[str, float] | None = None,
) -> InferenceResult:
    """Convert an AnalysisReport into the stable inference result contract."""
    report_timings = report.profiling or {}
    if timings is None:
        timings = {"total_wall_time_s": float(report_timings.get("total_wall_time_s", 0.0))}
        timings.update(
            {
                stage["name"]: float(stage["wall_time_s"])
                for stage in report_timings.get("stages", [])
            }
        )
    metrics = [
        {
            "name": metric.name,
            "value": metric.value,
            "unit": metric.unit,
            "is_good": metric.is_good,
            "reference_range": metric.reference_range,
        }
        for metric in report.metrics
    ]
    phases = vars(report.phases).copy() if report.phases is not None else None
    goe_grade = vars(report.goe_grade).copy() if report.goe_grade is not None else None
    return InferenceResult(
        video=dict(report.video),
        processed_frames=report.processed_frames,
        valid_frames=report.valid_frames,
        metrics=metrics,
        timings=timings,
        stages=dict(report.stages),
        warnings=list(report.warnings),
        annotations=report.annotations or {},
        analysis={
            "element_type": report.element_type,
            "phases": phases,
            "recommendations": list(report.recommendations),
            "overall_score": report.overall_score,
            "dtw_distance": report.dtw_distance,
            "goe_grade": goe_grade,
        },
    )


@dataclass(frozen=True)
class InferenceResult:
    """Machine-readable inference output shared by smoke and GPU-worker paths."""

    video: dict[str, Any]
    processed_frames: int
    valid_frames: int
    metrics: list[dict[str, Any]]
    timings: dict[str, float]
    stages: dict[str, bool]
    warnings: list[str]
    annotations: dict[str, Any]
    analysis: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.processed_frames < 0 or self.valid_frames < 0:
            raise ValueError("frame counts must be non-negative")
        if self.valid_frames > self.processed_frames:
            raise ValueError("valid_frames cannot exceed processed_frames")
        for name, seconds in self.timings.items():
            if not math.isfinite(float(seconds)) or seconds < 0:
                raise ValueError(f"timing {name!r} must be finite and >= 0")
        if any(not isinstance(cast("Any", enabled), bool) for enabled in self.stages.values()):
            raise ValueError("stage flags must be booleans")
        if any(
            not isinstance(cast("Any", warning), str) or not warning for warning in self.warnings
        ):
            raise ValueError("warnings must be non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        """Return a strict-JSON-compatible result payload."""
        payload = {
            "schema_version": self.schema_version,
            "video": self.video,
            "processed_frames": self.processed_frames,
            "valid_frames": self.valid_frames,
            "metrics": self.metrics,
            "timings": self.timings,
            "stages": self.stages,
            "warnings": self.warnings,
            "annotations": self.annotations,
            "analysis": self.analysis,
        }
        return _json_safe(payload)
