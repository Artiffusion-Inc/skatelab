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
