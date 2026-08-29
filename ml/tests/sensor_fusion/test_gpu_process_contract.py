"""GPU process contract tests using deterministic S3 and pose fakes."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from gpu_server import server


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _sample(timestamp_ns: int, gyro_z: float) -> bytes:
    body = bytearray(_varint(8) + _varint(timestamp_ns))
    for field in range(2, 12):
        body.extend(_varint((field << 3) | 5))
        body.extend(struct.pack("<f", gyro_z if field == 7 else 0.0))
    record = _varint(10) + _varint(len(body)) + body
    return _varint(len(record)) + record


def _imu_stream(first_timestamp_ns: int) -> bytes:
    return _sample(first_timestamp_ns, 2.0) + _sample(first_timestamp_ns + 10_000_000, 4.0)


class _S3Context:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_process_decodes_both_uploaded_streams_and_returns_provenance(tmp_path: Path) -> None:
    request = server.ProcessRequest(
        video_s3_key="uploads/session/video.mp4",
        person_click={"x": 1, "y": 2},
        imu_left_s3_key="uploads/session/left.binpb",
        imu_right_s3_key="uploads/session/right.binpb",
        manifest_s3_key="uploads/session/manifest.json",
        s3_bucket="test-bucket",
    )
    prepared = SimpleNamespace(
        poses_norm=np.zeros((2, 17, 2), dtype=np.float32),
        n_valid=2,
        meta=SimpleNamespace(num_frames=2, fps=100.0, width=640, height=480),
    )
    downloaded_keys: list[str] = []

    async def download(_s3, _bucket: str, key: str, path: str) -> None:
        downloaded_keys.append(key)
        output = Path(path)
        if key == request.video_s3_key:
            output.write_bytes(b"video")
        elif key == request.manifest_s3_key:
            output.write_text(
                json.dumps(
                    {
                        "t0_ns": 1_000_000_000,
                        "imu_rate_hz": 100,
                        "imu": {
                            "left": {"start_offset_ms": 0},
                            "right": {"start_offset_ms": 10},
                        },
                    }
                )
            )
        elif key == request.imu_left_s3_key:
            output.write_bytes(_imu_stream(1_000_000_000))
        elif key == request.imu_right_s3_key:
            output.write_bytes(_imu_stream(1_010_000_000))

    with (
        patch.object(server, "_models_ready", True),
        patch.object(server, "_tcpformer_extractor", None, create=True),
        patch.object(server, "_s3", return_value=_S3Context()),
        patch.object(server, "_s3_download", side_effect=download),
        patch.object(server, "_s3_upload", new_callable=AsyncMock),
        patch("src.pose_preparation.prepare_poses", return_value=prepared),
    ):
        result = await server.process(request)

    assert downloaded_keys == [
        request.video_s3_key,
        request.manifest_s3_key,
        request.imu_left_s3_key,
        request.imu_right_s3_key,
    ]
    assert result.sensor_fusion is not None
    assert result.sensor_fusion["status"] == "available"
    assert result.sensor_fusion["provenance"] == "android_binpb"
    assert result.sensor_fusion["validation"] == "unvalidated"
    assert result.sensor_fusion["left"]["samples"] == 2
    assert result.sensor_fusion["right"]["samples"] == 2
    assert result.sensor_fusion["pair"]["peak_delta_ms"] == 10.0


@pytest.mark.asyncio
async def test_process_rejects_corrupt_uploaded_stream(tmp_path: Path) -> None:
    request = server.ProcessRequest(
        video_s3_key="uploads/session/video.mp4",
        imu_left_s3_key="uploads/session/left.binpb",
        s3_bucket="test-bucket",
    )

    async def download(_s3, _bucket: str, key: str, path: str) -> None:
        Path(path).write_bytes(b"not-a-delimited-protobuf" if key.endswith(".binpb") else b"video")

    with (
        patch.object(server, "_models_ready", True),
        patch.object(server, "_s3", return_value=_S3Context()),
        patch.object(server, "_s3_download", side_effect=download),
    ):
        with pytest.raises(ValueError, match=r"protobuf|IMU"):
            await server.process(request)


@pytest.mark.asyncio
async def test_process_without_imu_returns_null_sensor_fusion(tmp_path: Path) -> None:
    request = server.ProcessRequest(
        video_s3_key="uploads/session/video.mp4", s3_bucket="test-bucket"
    )
    prepared = SimpleNamespace(
        poses_norm=np.zeros((1, 17, 2), dtype=np.float32),
        n_valid=1,
        meta=SimpleNamespace(num_frames=1, fps=30.0, width=640, height=480),
    )

    async def download(_s3, _bucket: str, _key: str, path: str) -> None:
        Path(path).write_bytes(b"video")

    with (
        patch.object(server, "_models_ready", True),
        patch.object(server, "_tcpformer_extractor", None, create=True),
        patch.object(server, "_s3", return_value=_S3Context()),
        patch.object(server, "_s3_download", side_effect=download),
        patch.object(server, "_s3_upload", new_callable=AsyncMock),
        patch("src.pose_preparation.prepare_poses", return_value=prepared),
    ):
        result = await server.process(request)

    assert result.sensor_fusion is None
