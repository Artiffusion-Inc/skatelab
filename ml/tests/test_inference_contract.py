from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest

if TYPE_CHECKING:
    from pathlib import Path

from src.inference_result import InferenceResult, build_annotations, result_from_report
from src.model_config import ModelConfig, ModelConfigurationError
from src.pose_preparation import prepare_poses
from src.types import AnalysisReport, ElementPhase, MetricResult


def test_model_config_uses_explicit_project_paths(tmp_path: Path) -> None:
    config = ModelConfig.from_root(tmp_path)

    assert config.moganet == tmp_path / "data/models/moganet_b_ap2d_384x288.onnx"
    assert config.rf_detr == tmp_path / "data/models/rf_detr_nano.onnx"
    assert config.tcpformer == tmp_path / "data/models/tcpformer/TCPFormer_ap3d_81_fp16.onnx"


def test_model_config_requires_2d_models_and_warns_for_missing_tcpformer(
    tmp_path: Path,
) -> None:
    config = ModelConfig.from_root(tmp_path)
    config.moganet.parent.mkdir(parents=True)
    config.rf_detr.parent.mkdir(parents=True, exist_ok=True)
    config.moganet.write_bytes(b"model")
    config.rf_detr.write_bytes(b"model")

    warnings = config.validate()

    assert len(warnings) == 1
    assert "3D disabled" in warnings[0]
    assert "TCPFormer" in warnings[0]


def test_model_config_fails_before_launch_when_required_model_is_missing(tmp_path: Path) -> None:
    config = ModelConfig.from_root(tmp_path)

    with pytest.raises(ModelConfigurationError, match="moganet"):
        config.validate()


def test_prepare_poses_validates_required_models_before_video_io(tmp_path: Path) -> None:
    config = ModelConfig.from_root(tmp_path)

    with pytest.raises(ModelConfigurationError, match="moganet"):
        prepare_poses(tmp_path / "missing.mp4", model_config=config)


def test_result_from_report_preserves_variable_analysis_values() -> None:
    report = AnalysisReport(
        element_type="waltz_jump",
        phases=ElementPhase("waltz_jump", 0, 1, 2, 3, 4),
        metrics=[MetricResult("airtime", 0.2, "s", False, (0.3, 0.7))],
        recommendations=["Keep the landing stable"],
        overall_score=2.5,
        video={"width": 640, "height": 480, "fps": 30.0, "total_frames": 5},
        processed_frames=5,
        valid_frames=4,
        stages={"pose_2d": True, "pose_3d": False},
        warnings=["3D disabled: TCPFormer model not found"],
        annotations={"coordinate_space": "normalized"},
    )

    result = result_from_report(report)

    assert result.analysis["overall_score"] == 2.5
    assert result.metrics[0]["value"] == 0.2
    assert result.processed_frames == 5


def test_inference_result_contains_overlay_annotations_and_strict_json() -> None:
    poses = np.zeros((2, 17, 2), dtype=np.float32)
    poses[0, 0] = [1.25, -0.5]
    poses[1, 0] = [np.nan, 0.5]
    confidence = np.ones((2, 17), dtype=np.float32)
    confidence[1, 0] = np.nan
    confidence[0, 1] = 2.0

    result = InferenceResult(
        video={"width": 1280, "height": 720, "fps": 25.0, "total_frames": 2},
        processed_frames=2,
        valid_frames=1,
        metrics=[{"name": "airtime", "value": 0.4, "unit": "s"}],
        timings={"total_wall_time_s": 1.25},
        stages={"pose_2d": True, "pose_3d": False},
        warnings=["3D disabled: TCPFormer model not found"],
        annotations=build_annotations(poses, confidence, np.array([0, 1]), fps=25.0),
    )

    payload = result.to_dict()
    json.dumps(payload, allow_nan=False)

    assert payload["schema_version"] == "skatelab.inference.v1"
    assert payload["processed_frames"] == 2
    assert payload["annotations"]["coordinate_space"] == "normalized"
    assert payload["annotations"]["frame_indices"] == [0, 1]
    assert payload["annotations"]["poses"][0][0] == [1.0, 0.0]
    assert payload["annotations"]["poses"][1][0] is None
    assert payload["annotations"]["confidence"][1][0] is None
    assert payload["annotations"]["confidence"][0][1] == 1.0
    assert payload["stages"]["pose_3d"] is False
    assert payload["warnings"]
