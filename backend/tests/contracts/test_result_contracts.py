"""Backend result schemas mirror the current frontend wire contracts."""

from __future__ import annotations

from app.schemas import (
    DiagnosticsResponse,
    ProcessResponse,
    ProcessStats,
    SessionMetricResponse,
    SessionPhaseResponse,
    SessionScoreResponse,
    TrendResponse,
)


def _subscore() -> dict:
    return {
        "name": "technique",
        "label_ru": "Tekhnika",
        "value": 8.0,
        "confidence": 0.9,
        "contributing_metrics": ["airtime"],
    }


def test_process_response_accepts_inference_contract_v1_fields() -> None:
    response = ProcessResponse(
        video_path="uploads/video.mp4",
        poses_path="output/poses.npy",
        csv_path="output/metrics.json",
        stats=ProcessStats(total_frames=2, valid_frames=2, fps=30.0, resolution="640x480"),
        status="Analysis complete!",
        metrics=[{"name": "airtime", "value": 0.5}],
        phases={"takeoff": 1},
        recommendations=["Keep the landing stable"],
        schema_version="skatelab.inference.v1",
        processed_frames=2,
        valid_frames=2,
        timings={"total_wall_time_s": 1.25},
        stages={"pose_2d": True, "pose_3d": False},
        warnings=["3D disabled: TCPFormer model not found"],
        annotations={"coordinate_space": "normalized", "poses": []},
    )

    assert response.schema_version == "skatelab.inference.v1"
    assert response.processed_frames == 2
    assert response.metrics == [{"name": "airtime", "value": 0.5}]
    assert response.phases == {"takeoff": 1}
    assert response.stages["pose_3d"] is False
    assert response.annotations["coordinate_space"] == "normalized"


def test_process_stats_keeps_sensor_payload_optional() -> None:
    video_only = ProcessStats(
        total_frames=120,
        valid_frames=118,
        fps=30.0,
        resolution="1920x1080",
    )

    assert video_only.imu_stats is None
    assert video_only.sensor_fusion is None


def test_metric_trend_and_diagnostics_shapes_match_frontend() -> None:
    metric = SessionMetricResponse(
        id="metric-1",
        metric_name="airtime",
        metric_value=0.5,
        is_pr=True,
        prev_best=0.4,
        reference_value=0.3,
        is_in_range=True,
    )
    trend = TrendResponse(
        metric_name="airtime",
        element_type="3A",
        data_points=[],
        trend="stable",
        current_pr=metric.metric_value,
        reference_range={"min": 0.3, "max": 0.7},
    )
    diagnostics = DiagnosticsResponse(
        user_id="user-1",
        findings=[
            {
                "severity": "warning",
                "element": "3A",
                "metric": "airtime",
                "message": "Needs work",
                "detail": "Review the takeoff",
            }
        ],
    )

    assert metric.metric_name == trend.metric_name
    assert diagnostics.findings[0].severity == "warning"


def test_score_response_emits_frontend_quality_field() -> None:
    score = SessionScoreResponse(
        id="score-1",
        session_id="session-1",
        subscores=[_subscore()],
        overall=8.0,
        skeleton_reliability="reliable",
        created_at="2026-08-30T10:00:00Z",
        updated_at="2026-08-30T10:00:00Z",
    )

    payload = score.model_dump()
    assert payload["data_quality"] == "good"
    assert payload["skeleton_reliability"] == "reliable"


def test_phase_response_matches_frontend_shape() -> None:
    phase = SessionPhaseResponse(
        id="phase-1",
        session_id="session-1",
        phases=[
            {
                "name": "takeoff",
                "start_frame": 10,
                "end_frame": 20,
                "start_time": 0.33,
                "end_time": 0.66,
                "confidence": 0.9,
                "detection_method": "tas_segment",
            }
        ],
        overall_confidence=0.9,
        element_type="3A",
        fallback_used=False,
        created_at="2026-08-30T10:00:00Z",
        updated_at="2026-08-30T10:00:00Z",
    )

    assert phase.phases[0].name == "takeoff"
    assert phase.fallback_used is False
