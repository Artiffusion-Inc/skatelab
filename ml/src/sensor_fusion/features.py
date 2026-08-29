"""Deterministic features joining two boot IMUs and video phase timing."""

from __future__ import annotations

import math

from .imu_decoder import ImuStream


def _peak(stream: ImuStream) -> tuple[int, float] | None:
    if not stream.values:
        return None
    magnitudes = [math.sqrt(sum(v * v for v in row[3:6])) for row in stream.values]
    index = max(range(len(magnitudes)), key=magnitudes.__getitem__)
    return stream.timestamps_ns[index], magnitudes[index]


def summarize_pair(left: ImuStream, right: ImuStream) -> dict[str, float | int | None]:
    """Compare peak rotation timing/magnitude across both skates."""
    left_peak = _peak(left)
    right_peak = _peak(right)
    if left_peak is None or right_peak is None:
        return {"peak_delta_ms": None, "peak_magnitude_ratio": None, "overlap_ms": 0.0}

    overlap_start = max(left.timestamps_ns[0], right.timestamps_ns[0])
    overlap_end = min(left.timestamps_ns[-1], right.timestamps_ns[-1])
    overlap_ms = max(0, overlap_end - overlap_start) / 1e6
    larger = max(left_peak[1], right_peak[1])
    ratio = min(left_peak[1], right_peak[1]) / larger if larger > 0 else None
    return {
        "peak_delta_ms": round(abs(left_peak[0] - right_peak[0]) / 1e6, 3),
        "peak_magnitude_ratio": round(ratio, 5) if ratio is not None else None,
        "overlap_ms": round(overlap_ms, 3),
    }


def annotate_video_phase(
    side_summary: dict[str, float | int | None],
    *,
    fps: float,
    takeoff: int,
    landing: int,
) -> dict[str, float | int | str | None]:
    """Map an IMU peak offset to a video frame and jump phase."""
    offset_ms = side_summary.get("peak_offset_ms")
    if offset_ms is None or fps <= 0:
        return {**side_summary, "peak_frame": None, "video_phase": None}
    frame = max(0, round(float(offset_ms) * fps / 1000.0))
    phase = "preparation" if frame < takeoff else "flight" if frame <= landing else "landing"
    return {**side_summary, "peak_frame": frame, "video_phase": phase}


def fused_confidence(
    left: dict[str, float | int | str | None],
    right: dict[str, float | int | str | None],
    pair: dict[str, float | int | None],
    offset_error_ms: float = 0.0,
) -> float:
    """Score data quality (not skating quality) on a deterministic 0..1 scale."""
    samples = min(int(left.get("samples", 0) or 0), int(right.get("samples", 0) or 0))
    sample_score = min(1.0, samples / 120.0)
    ratio = float(pair.get("peak_magnitude_ratio") or 0.0)
    symmetry_score = min(1.0, ratio)
    delta = float(pair.get("peak_delta_ms") or 1_000.0)
    timing_score = max(0.0, 1.0 - delta / 250.0)
    phase_score = 1.0 if left.get("video_phase") == "flight" and right.get("video_phase") == "flight" else 0.5
    offset_score = max(0.0, 1.0 - abs(offset_error_ms) / 100.0)
    return round(
        0.2 * sample_score
        + 0.2 * symmetry_score
        + 0.2 * timing_score
        + 0.2 * phase_score
        + 0.2 * offset_score,
        4,
    )


def landing_stability(
    stream: ImuStream,
    *,
    t0_ns: int,
    fps: float,
    landing_frame: int,
) -> dict[str, float | int | None]:
    """Measure post-landing motion in a 150 ms window."""
    if not stream.timestamps_ns or t0_ns <= 0 or fps <= 0:
        return {"samples": 0, "gyro_mean_rad_s": None, "gyro_std_rad_s": None}
    landing_ns = t0_ns + int(landing_frame / fps * 1e9)
    window = [
        math.sqrt(sum(v * v for v in row[3:6]))
        for timestamp, row in zip(stream.timestamps_ns, stream.values)
        if landing_ns <= timestamp <= landing_ns + 150_000_000
    ]
    if not window:
        return {"samples": 0, "gyro_mean_rad_s": None, "gyro_std_rad_s": None}
    mean = sum(window) / len(window)
    variance = sum((value - mean) ** 2 for value in window) / len(window)
    return {
        "samples": len(window),
        "gyro_mean_rad_s": round(mean, 5),
        "gyro_std_rad_s": round(math.sqrt(variance), 5),
    }


def landing_pair_summary(
    left: dict[str, float | int | None],
    right: dict[str, float | int | None],
) -> dict[str, float | None]:
    """Compare residual rotation after landing between both skates."""
    left_mean = left.get("gyro_mean_rad_s")
    right_mean = right.get("gyro_mean_rad_s")
    if left_mean is None or right_mean is None:
        return {"mean_delta_rad_s": None, "stability_ratio": None}
    left_value, right_value = float(left_mean), float(right_mean)
    larger = max(left_value, right_value)
    ratio = min(left_value, right_value) / larger if larger > 0 else 1.0
    return {
        "mean_delta_rad_s": round(abs(left_value - right_value), 5),
        "stability_ratio": round(ratio, 5),
    }
