"""Decoder for the Android IMURecord length-delimited protobuf stream.

Kept dependency-free so the GPU image does not need protoc or generated Python
classes. The field numbers mirror ``mobile/proto/imu.proto``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


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


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7
        if shift >= 64:
            raise ValueError("protobuf varint is too long")
    raise ValueError("truncated protobuf varint")


def _fields(data: bytes):
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        field, wire = tag >> 3, tag & 7
        if wire == 0:
            value, pos = _varint(data, pos)
        elif wire == 1:
            value, pos = data[pos : pos + 8], pos + 8
        elif wire == 2:
            size, pos = _varint(data, pos)
            value, pos = data[pos : pos + size], pos + size
        elif wire == 5:
            value, pos = data[pos : pos + 4], pos + 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        yield field, wire, value


def _sample(data: bytes) -> tuple[int, tuple[float, ...]] | None:
    fields: dict[int, object] = {}
    for field, wire, value in _fields(data):
        if wire == 5 and isinstance(value, bytes) and len(value) == 4:
            fields[field] = struct.unpack("<f", value)[0]
        elif wire == 0:
            fields[field] = value
    timestamp = int(fields.get(1, 0))
    if not timestamp:
        return None
    values = tuple(float(fields.get(i, 0.0)) for i in range(2, 12))
    return timestamp, values


def decode_imu_file(path: str | Path) -> ImuStream:
    data = Path(path).read_bytes()
    timestamps: list[int] = []
    values: list[tuple[float, ...]] = []
    gaps = 0
    pos = 0
    while pos < len(data):
        size, pos = _varint(data, pos)
        record = data[pos : pos + size]
        pos += size
        for field, wire, value in _fields(record):
            if wire != 2 or not isinstance(value, bytes):
                continue
            if field == 1:
                parsed = _sample(value)
                if parsed:
                    timestamp, sample_values = parsed
                    timestamps.append(timestamp)
                    values.append(sample_values)
            elif field == 2:
                gaps += 1
    if len(timestamps) != len(values):
        raise ValueError("IMU stream sample/value length mismatch")
    return ImuStream(timestamps, values, gaps)
