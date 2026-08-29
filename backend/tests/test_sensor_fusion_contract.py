from app.schemas import ProcessStats
from app.vastai.client import VastResult


def test_process_stats_preserves_sensor_fusion_payload() -> None:
    stats = ProcessStats.model_validate(
        {
            "total_frames": 120,
            "valid_frames": 118,
            "fps": 60.0,
            "resolution": "1920x1080",
            "imu_stats": {"left": {"samples": 12000}},
            "sensor_fusion": {"confidence": 0.91},
        }
    )

    assert stats.imu_stats == {"left": {"samples": 12000}}
    assert stats.sensor_fusion == {"confidence": 0.91}


def test_vast_result_exposes_sensor_fusion_fields() -> None:
    result = VastResult(
        poses_key="poses.npy",
        metrics_key="metrics.json",
        stats={},
        metrics=[],
        phases=None,
        recommendations=[],
        imu_stats={"left": {"samples": 10}},
        sensor_fusion={"confidence": 0.8},
    )

    assert result.sensor_fusion == {"confidence": 0.8}
