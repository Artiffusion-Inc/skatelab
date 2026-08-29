from app.metrics_registry import METRIC_REGISTRY, JUMP_ELEMENTS


def test_sensor_fusion_metrics_are_registered_for_jumps() -> None:
    expected = {
        "sensor_confidence": ("ratio", "higher", (0.6, 1.0)),
        "rotation_symmetry": ("ratio", "higher", (0.75, 1.0)),
        "imu_peak_delta": ("ms", "lower", (0.0, 80.0)),
        "landing_stability": ("ratio", "higher", (0.75, 1.0)),
        "imu_offset_error": ("ms", "lower", (0.0, 40.0)),
        "imu_rate_error": ("Hz", "lower", (0.0, 5.0)),
    }

    for name, (unit, direction, ideal_range) in expected.items():
        definition = METRIC_REGISTRY[name]
        assert definition.unit == unit
        assert definition.direction == direction
        assert definition.ideal_range == ideal_range
        assert set(JUMP_ELEMENTS).issubset(definition.element_types)
