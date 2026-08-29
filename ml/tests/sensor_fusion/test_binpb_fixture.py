import struct

import pytest

from src.sensor_fusion import decode_imu_file


def _varint(value: int) -> bytes:
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _sample(timestamp: int, gyro_z: float) -> bytes:
    body = bytearray()
    body += _varint((1 << 3) | 0) + _varint(timestamp)
    for field in range(2, 12):
        value = gyro_z if field == 7 else 0.0
        body += _varint((field << 3) | 5) + struct.pack("<f", value)
    return _varint((1 << 3) | 2) + _varint(len(body)) + body


def _gap(last: int, first: int, sequence: int) -> bytes:
    body = (
        _varint((1 << 3) | 0) + _varint(last)
        + _varint((2 << 3) | 0) + _varint(first)
        + _varint((3 << 3) | 0) + _varint(sequence)
    )
    return _varint((2 << 3) | 2) + _varint(len(body)) + body


def test_decode_android_delimited_binpb_fixture(tmp_path) -> None:
    payload = b"".join(
        (
            _sample(1_000_000_000, 2.0),
            _gap(1_000_000_000, 1_100_000_000, 1),
            _sample(1_100_000_000, 4.0),
        )
    )
    path = tmp_path / "left.binpb"
    path.write_bytes(payload)

    stream = decode_imu_file(path)

    assert stream.timestamps_ns == [1_000_000_000, 1_100_000_000]
    assert stream.values[0][5] == 2.0
    assert stream.values[1][5] == 4.0
    assert stream.gaps == 1
    assert stream.sample_rate_hz == 10.0


def test_decode_rejects_truncated_delimited_record(tmp_path) -> None:
    path = tmp_path / "truncated.binpb"
    path.write_bytes(_varint(10) + b"short")

    with pytest.raises(ValueError, match="truncated IMURecord"):
        decode_imu_file(path)
