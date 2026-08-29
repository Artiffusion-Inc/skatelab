"""Decoder for the Android IMURecord length-delimited protobuf stream.

Kept dependency-free so the GPU image does not need protoc or generated Python
classes. The field numbers mirror ``mobile/proto/imu.proto``.
"""

from __future__ import annotations

import itertools
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True)
class ImuStream:
    timestamps_ns: list[int]
    values: list[tuple[float, ...]]
    gaps: int

    @property
    def sample_rate_hz(self) -> float:
        if len(self.timestamps_ns) < 2:
            return 0.0
        elapsed = self.timestamps_ns[-1] - self.timestamps_ns[0]
        return (len(self.timestamps_ns) - 1) * 1e9 / elapsed if elapsed > 0 else 0.0

    def angular_velocity_summary(self, t0_ns: int = 0) -> dict[str, float | int | None]:
        """Return a robust first feature for alignment with video phases.

        Values are gyro x/y/z in the order written by the Android producer.
        The peak timestamp is expressed in milliseconds from the capture anchor.
        """
        if not self.values:
            return {"samples": 0, "peak_rad_s": None, "peak_offset_ms": None}
        magnitudes = [
            sum(component * component for component in row[3:6]) ** 0.5 for row in self.values
        ]
        peak_index = max(range(len(magnitudes)), key=magnitudes.__getitem__)
        peak_ns = self.timestamps_ns[peak_index]
        return {
            "samples": len(self.values),
            "peak_rad_s": round(magnitudes[peak_index], 5),
            "peak_offset_ms": round((peak_ns - t0_ns) / 1e6, 3) if t0_ns else None,
        }


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        if shift == 63 and byte > 1:
            raise ValueError("protobuf varint is too long")
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7
        if shift >= 64:
            raise ValueError("protobuf varint is too long")
    raise ValueError("truncated protobuf varint")


def _fields(data: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        field, wire = tag >> 3, tag & 7
        if field == 0:
            raise ValueError("protobuf field number must be positive")
        if wire == 0:
            value, pos = _varint(data, pos)
        elif wire == 1:
            if pos + 8 > len(data):
                raise ValueError("truncated protobuf fixed64 field")
            value, pos = data[pos : pos + 8], pos + 8
        elif wire == 2:
            size, pos = _varint(data, pos)
            if pos + size > len(data):
                raise ValueError("truncated protobuf length-delimited field")
            value, pos = data[pos : pos + size], pos + size
        elif wire == 5:
            if pos + 4 > len(data):
                raise ValueError("truncated protobuf fixed32 field")
            value, pos = data[pos : pos + 4], pos + 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        yield field, wire, value


def _sample(data: bytes) -> tuple[int, tuple[float, ...]]:
    fields: dict[int, float | int] = {}
    for field, wire, value in _fields(data):
        if field == 1:
            if wire != 0 or not isinstance(value, int):
                raise ValueError("IMUSample timestamp has the wrong wire type")
            fields[field] = value
        elif 2 <= field <= 11:
            if wire != 5 or not isinstance(value, bytes) or len(value) != 4:
                raise ValueError(f"IMUSample field {field} has the wrong wire type")
            fields[field] = struct.unpack("<f", value)[0]
    if 1 not in fields:
        raise ValueError("IMUSample timestamp is missing")
    timestamp = int(fields[1])
    values = tuple(float(fields.get(i, 0.0)) for i in range(2, 12))
    return timestamp, values


def _record(data: bytes) -> tuple[int, bytes] | None:
    selected: tuple[int, bytes] | None = None
    for field, wire, value in _fields(data):
        if field not in (1, 2):
            continue
        if wire != 2 or not isinstance(value, bytes):
            raise ValueError(f"IMURecord field {field} has the wrong wire type")
        # Protobuf oneof semantics keep the last member when both are present.
        selected = field, value
    return selected


def _validate_gap(data: bytes) -> None:
    for field, wire, _ in _fields(data):
        if field <= 3 and wire != 0:
            raise ValueError(f"IMUGap field {field} has the wrong wire type")


def decode_imu_file(path: str | Path) -> ImuStream:
    data = Path(path).read_bytes()
    timestamps: list[int] = []
    values: list[tuple[float, ...]] = []
    gaps = 0
    pos = 0
    while pos < len(data):
        size, pos = _varint(data, pos)
        if pos + size > len(data):
            raise ValueError("truncated IMURecord payload")
        record = data[pos : pos + size]
        pos += size
        selected = _record(record)
        if selected is None:
            raise ValueError("IMURecord must contain a sample or gap")
        record_type, payload = selected
        if record_type == 1:
            timestamp, sample_values = _sample(payload)
            timestamps.append(timestamp)
            values.append(sample_values)
        else:
            _validate_gap(payload)
            gaps += 1
    if len(timestamps) != len(values):
        raise ValueError("IMU stream sample/value length mismatch")
    if any(current <= previous for previous, current in itertools.pairwise(timestamps)):
        raise ValueError("IMU timestamps are not strictly monotonic")
    return ImuStream(timestamps, values, gaps)
