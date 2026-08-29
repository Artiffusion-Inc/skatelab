import json
import struct
from pathlib import Path

import pytest

from src.sensor_fusion import decode_imu_file

FIXTURES = Path(__file__).parent / "fixtures"


def _varint(value: int) -> bytes:
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _delimited(record: bytes) -> bytes:
    return _varint(len(record)) + record


def _sample(timestamp: int, gyro_z: float) -> bytes:
    body = bytearray()
    body += _varint((1 << 3) | 0) + _varint(timestamp)
    for field in range(2, 12):
        value = gyro_z if field == 7 else 0.0
        body += _varint((field << 3) | 5) + struct.pack("<f", value)
    return _delimited(_varint((1 << 3) | 2) + _varint(len(body)) + body)


def _sample_without_timestamp() -> bytes:
    body = _varint((7 << 3) | 5) + struct.pack("<f", 1.0)
    return _delimited(_varint((1 << 3) | 2) + _varint(len(body)) + body)


def _gap(last: int, first: int, sequence: int) -> bytes:
    body = (
        _varint((1 << 3) | 0)
        + _varint(last)
        + _varint((2 << 3) | 0)
        + _varint(first)
        + _varint((3 << 3) | 0)
        + _varint(sequence)
    )
    return _delimited(_varint((2 << 3) | 2) + _varint(len(body)) + body)


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


def test_decode_sparse_android_fixture_preserves_proto3_zero_defaults() -> None:
    stream = decode_imu_file(FIXTURES / "valid_left.binpb")

    assert stream.timestamps_ns == [1_000_000_000, 1_010_000_000, 1_020_000_000]
    assert stream.values[0][5] == 1.0
    assert stream.values[0][0:5] == (0.0, 0.0, 0.0, 0.0, 0.0)
    assert stream.values[0][6:] == (0.0, 0.0, 0.0, 0.0)
    assert stream.gaps == 0


def test_gap_fixture_keeps_gap_marker_out_of_sample_timestamps() -> None:
    stream = decode_imu_file(FIXTURES / "gap_left.binpb")

    assert stream.timestamps_ns == [1_000_000_000, 1_030_000_000]
    assert stream.gaps == 1


def test_drift_fixture_reports_measured_rate_separately_from_manifest_rate() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    stream = decode_imu_file(FIXTURES / "drift_left.binpb")

    assert manifest["imu"]["left"]["sample_rate_hz"] == 100
    assert stream.sample_rate_hz == pytest.approx(90.0, rel=0.001)


def test_manifest_anchor_aligns_peak_to_capture_time() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    stream = decode_imu_file(FIXTURES / "valid_left.binpb")

    assert stream.angular_velocity_summary(manifest["t0_ns"])["peak_offset_ms"] == 10.0


def test_manifest_anchor_is_optional_and_zero_delay_is_not_missing() -> None:
    manifest = json.loads((FIXTURES / "manifest_missing_anchor.json").read_text())
    stream = decode_imu_file(FIXTURES / "valid_left.binpb")

    assert "t0_ns" not in manifest
    assert manifest["imu"]["left"]["imu_start_delay_ms"] == 0
    assert stream.angular_velocity_summary(manifest.get("t0_ns", 0))["peak_offset_ms"] is None


def test_decode_rejects_sample_without_timestamp(tmp_path) -> None:
    path = tmp_path / "missing_timestamp.binpb"
    path.write_bytes(_sample_without_timestamp())

    with pytest.raises(ValueError, match="timestamp"):
        decode_imu_file(path)


def test_decode_rejects_empty_delimited_record(tmp_path) -> None:
    path = tmp_path / "empty_record.binpb"
    path.write_bytes(_delimited(b""))

    with pytest.raises(ValueError, match="sample or gap"):
        decode_imu_file(path)


def test_decode_rejects_truncated_delimited_record(tmp_path) -> None:
    path = tmp_path / "truncated.binpb"
    path.write_bytes(_varint(10) + b"short")

    with pytest.raises(ValueError, match="truncated IMURecord"):
        decode_imu_file(path)


def test_decode_rejects_truncated_fixture() -> None:
    with pytest.raises(ValueError, match="truncated IMURecord"):
        decode_imu_file(FIXTURES / "corrupt_truncated.binpb")


def test_decode_rejects_non_monotonic_timestamps(tmp_path) -> None:
    path = tmp_path / "non_monotonic.binpb"
    path.write_bytes(_sample(2_000_000_000, 1.0) + _sample(1_000_000_000, 1.0))

    with pytest.raises(ValueError, match="strictly monotonic"):
        decode_imu_file(path)
