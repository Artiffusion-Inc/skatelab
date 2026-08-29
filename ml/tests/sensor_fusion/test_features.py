from src.sensor_fusion import (
    ImuStream,
    annotate_video_phase,
    fused_confidence,
    landing_pair_summary,
    landing_stability,
    summarize_pair,
)


def _stream(timestamps: list[int], gyro: list[float]) -> ImuStream:
    values = [(0.0, 0.0, 0.0, value, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0) for value in gyro]
    return ImuStream(timestamps, values, gaps=0)


def test_pair_summary_compares_rotation_peaks() -> None:
    left = _stream([1_000_000_000, 1_010_000_000], [1.0, 4.0])
    right = _stream([1_000_000_000, 1_015_000_000], [3.0, 1.0])

    result = summarize_pair(left, right)

    assert result["peak_delta_ms"] == 10.0
    assert result["peak_magnitude_ratio"] == 0.75
    assert result["overlap_ms"] == 10.0


def test_peak_is_mapped_to_flight_frame() -> None:
    result = annotate_video_phase(
        {"peak_offset_ms": 500.0},
        fps=60.0,
        takeoff=20,
        landing=40,
    )

    assert result["peak_frame"] == 30
    assert result["video_phase"] == "flight"


def test_fused_confidence_rewards_symmetric_flight_signal() -> None:
    side = {"samples": 240, "video_phase": "flight"}
    pair = {"peak_magnitude_ratio": 1.0, "peak_delta_ms": 0.0}
    assert fused_confidence(side, side, pair) == 1.0
    assert fused_confidence(side, side, pair, offset_error_ms=100.0) == 0.8
    assert fused_confidence(side, side, pair, rate_error_hz=10.0) == 0.85


def test_fused_confidence_requires_samples_from_both_sensors() -> None:
    populated = {"samples": 240, "video_phase": "flight"}
    missing_right = {"samples": 0, "video_phase": "flight"}
    pair = {"peak_magnitude_ratio": 1.0, "peak_delta_ms": 0.0}

    assert fused_confidence(populated, missing_right, pair) == 0.0
    assert fused_confidence(populated, populated, {}) == 0.0


def test_pair_summary_treats_two_zero_rotation_signals_as_symmetric() -> None:
    left = _stream([1_000_000_000, 1_010_000_000], [0.0, 0.0])
    right = _stream([1_000_000_000, 1_010_000_000], [0.0, 0.0])

    assert summarize_pair(left, right) == {
        "peak_delta_ms": 0.0,
        "peak_magnitude_ratio": 1.0,
        "overlap_ms": 10.0,
    }


def test_pair_summary_marks_asymmetric_empty_sensor_unavailable() -> None:
    populated = _stream([1_000_000_000, 1_010_000_000], [0.0, 2.0])
    missing = _stream([], [])

    assert summarize_pair(populated, missing) == {
        "peak_delta_ms": None,
        "peak_magnitude_ratio": None,
        "overlap_ms": 0.0,
    }


def test_landing_stability_uses_post_landing_window() -> None:
    stream = _stream(
        [1_000_000_000, 1_100_000_000, 1_200_000_000],
        [1.0, 2.0, 3.0],
    )
    result = landing_stability(stream, t0_ns=1_000_000_000, fps=10.0, landing_frame=1)
    assert result["samples"] == 2
    assert result["gyro_mean_rad_s"] == 2.5


def test_landing_pair_summary_reports_asymmetry() -> None:
    result = landing_pair_summary(
        {"gyro_mean_rad_s": 2.0},
        {"gyro_mean_rad_s": 4.0},
    )
    assert result == {"mean_delta_rad_s": 2.0, "stability_ratio": 0.5}


def test_fused_pipeline_smoke() -> None:
    left = _stream([1_000_000_000, 1_010_000_000, 1_020_000_000], [1.0, 5.0, 2.0])
    right = _stream([1_000_000_000, 1_010_000_000, 1_020_000_000], [1.0, 4.5, 2.0])
    left_peak = annotate_video_phase(
        left.angular_velocity_summary(1_000_000_000), fps=60, takeoff=20, landing=40
    )
    right_peak = annotate_video_phase(
        right.angular_velocity_summary(1_000_000_000), fps=60, takeoff=20, landing=40
    )
    pair = summarize_pair(left, right)

    assert left_peak["video_phase"] == "preparation"
    assert right_peak["peak_frame"] == 1
    assert fused_confidence(left_peak, right_peak, pair) > 0.5
