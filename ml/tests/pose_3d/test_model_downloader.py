"""Tests for model_downloader module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.pose_3d.model_downloader import _download_attempted, resolve_model


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear download cache between tests."""
    _download_attempted.clear()
    yield
    _download_attempted.clear()


class TestResolveModel:
    def test_unknown_model_key_returns_none(self):
        """Should return None for unknown model key."""
        result = resolve_model("nonexistent_model")
        assert result is None

    def test_finds_model_at_cwd_path(self, tmp_path, monkeypatch):
        """Should find model at CWD-relative path."""
        model_dir = tmp_path / "data" / "models" / "tcpformer"
        model_dir.mkdir(parents=True)
        model_file = model_dir / "TCPFormer_ap3d_81_fp16.onnx"
        model_file.write_bytes(b"fake onnx")

        monkeypatch.chdir(tmp_path)
        result = resolve_model("tcpformer")
        assert result is not None
        assert result.name == "TCPFormer_ap3d_81_fp16.onnx"

    def test_finds_model_at_app_path(self, tmp_path, monkeypatch):
        """Should find model at /app/ path."""
        model_dir = tmp_path / "app" / "data" / "models" / "tcpformer"
        model_dir.mkdir(parents=True)
        model_file = model_dir / "TCPFormer_ap3d_81_fp16.onnx"
        model_file.write_bytes(b"fake onnx")

        monkeypatch.setattr(
            "src.pose_3d.model_downloader._LOCAL_PREFIXES",
            [str(tmp_path / "app")],
        )
        result = resolve_model("tcpformer")
        assert result is not None
        assert result.name == "TCPFormer_ap3d_81_fp16.onnx"

    def test_returns_none_when_not_found_no_s3(self, monkeypatch):
        """Should return None when model missing and no S3 credentials."""
        monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
        monkeypatch.delenv("S3_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("S3_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("S3_BUCKET", raising=False)

        monkeypatch.setattr(
            "src.pose_3d.model_downloader._LOCAL_PREFIXES",
            ["/nonexistent/path"],
        )
        result = resolve_model("tcpformer")
        assert result is None

    def test_does_not_retry_after_failure(self, monkeypatch):
        """Should not retry resolve_model after first failure."""
        monkeypatch.setattr(
            "src.pose_3d.model_downloader._LOCAL_PREFIXES",
            ["/nonexistent/path"],
        )

        result1 = resolve_model("tcpformer")
        assert result1 is None

        # Second call should return None immediately (no retry)
        result2 = resolve_model("tcpformer")
        assert result2 is None

    def test_s3_download_success(self, tmp_path, monkeypatch):
        """Should download model from S3 when credentials available."""
        model_dir = tmp_path / "data" / "models" / "tcpformer"
        model_dir.mkdir(parents=True)
        model_file = model_dir / "TCPFormer_ap3d_81_fp16.onnx"

        def fake_download(name, relative_path):
            model_file.write_bytes(b"fake onnx from s3")
            return model_file

        monkeypatch.setattr(
            "src.pose_3d.model_downloader._download_from_s3",
            fake_download,
        )
        monkeypatch.setattr(
            "src.pose_3d.model_downloader._LOCAL_PREFIXES",
            ["/nonexistent/path"],  # Force S3 path
        )

        result = resolve_model("tcpformer")
        assert result is not None
        assert result.name == "TCPFormer_ap3d_81_fp16.onnx"

    def test_s3_download_failure_returns_none(self, monkeypatch):
        """Should return None when S3 download fails."""
        monkeypatch.setattr(
            "src.pose_3d.model_downloader._LOCAL_PREFIXES",
            ["/nonexistent/path"],
        )
        monkeypatch.setattr(
            "src.pose_3d.model_downloader._download_from_s3",
            lambda name, path: None,
        )

        result = resolve_model("tcpformer")
        assert result is None

    def test_moganet_key(self, tmp_path, monkeypatch):
        """Should resolve moganet model key."""
        model_dir = tmp_path / "data" / "models" / "moganet"
        model_dir.mkdir(parents=True)
        model_file = model_dir / "moganet_b_ap2d_384x288_fp16.onnx"
        model_file.write_bytes(b"fake onnx")

        monkeypatch.setattr(
            "src.pose_3d.model_downloader._LOCAL_PREFIXES",
            [str(tmp_path)],
        )
        result = resolve_model("moganet")
        assert result is not None
        assert "moganet" in str(result)

    def test_rf_detr_key(self, tmp_path, monkeypatch):
        """Should resolve rf_detr model key."""
        model_dir = tmp_path / "data" / "models"
        model_dir.mkdir(parents=True)
        model_file = model_dir / "rf_detr_nano_fp16.onnx"
        model_file.write_bytes(b"fake onnx")

        monkeypatch.setattr(
            "src.pose_3d.model_downloader._LOCAL_PREFIXES",
            [str(tmp_path)],
        )
        result = resolve_model("rf_detr")
        assert result is not None
        assert "rf_detr" in str(result)
