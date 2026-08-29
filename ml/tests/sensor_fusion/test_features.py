from src.sensor_fusion import ImuStream, annotate_video_phase, summarize_pair


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
