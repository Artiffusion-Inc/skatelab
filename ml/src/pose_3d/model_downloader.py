"""Download ONNX models from S3 on first use.

Provides a single resolve_model() function that searches local paths
and falls back to S3 download when the model file is missing.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Search locations (in order): local dev → Docker container
_LOCAL_PREFIXES: list[str] = [
    "",  # relative to CWD
    "/app",  # Docker container
]

# S3 model key → local relative path mapping
_MODEL_MAP: dict[str, str] = {
    "tcpformer": "data/models/tcpformer/TCPFormer_ap3d_81_fp16.onnx",
    "moganet": "data/models/moganet/moganet_b_ap2d_384x288_fp16.onnx",
    "rf_detr": "data/models/rf_detr_nano_fp16.onnx",
}

# Track which models we already tried to download (avoid retries)
_download_attempted: set[str] = set()


def resolve_model(name: str, device: str = "auto") -> Path | None:
    """Find or download an ONNX model file.

    Searches local filesystem first, then downloads from S3 if credentials
    are available. Returns None if the model cannot be found or downloaded.

    Args:
        name: Model key (e.g. "tcpformer", "moganet", "rf_detr").
        device: Device hint (unused, reserved for future per-model config).

    Returns:
        Path to the model file, or None if unavailable.
    """
    relative_path = _MODEL_MAP.get(name)
    if relative_path is None:
        logger.warning("Unknown model key: %s", name)
        return None

    # Already tried and failed — don't retry
    if name in _download_attempted:
        return None

    # Search local paths
    for prefix in _LOCAL_PREFIXES:
        candidate = Path(prefix) / relative_path
        if candidate.exists():
            logger.debug("Model %s found at %s", name, candidate)
            return candidate

    # Try S3 download
    downloaded = _download_from_s3(name, relative_path)
    if downloaded is not None:
        return downloaded

    # Mark as unavailable so we don't retry
    _download_attempted.add(name)
    logger.warning(
        "Model %s not found locally and S3 download failed — %s disabled. "
        "Upload model to S3 or place at %s",
        name,
        name,
        relative_path,
    )
    return None


def _download_from_s3(name: str, relative_path: str) -> Path | None:
    """Download a model from S3 to its local path.

    Returns the local path on success, None on failure.
    Requires S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY,
    S3_BUCKET env vars.
    """
    endpoint = os.environ.get("S3_ENDPOINT_URL", "")
    access_key = os.environ.get("S3_ACCESS_KEY_ID", "")
    secret = os.environ.get("S3_SECRET_ACCESS_KEY", "")
    bucket = os.environ.get("S3_BUCKET", "")

    if not all([endpoint, access_key, secret, bucket]):
        logger.debug("S3 credentials not configured — skipping download for %s", name)
        return None

    s3_key = relative_path.replace("data/models/", "models/")
    local_path = Path(relative_path)

    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret,
            region_name=os.environ.get("S3_REGION", "us-east-1"),
            config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

        local_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading model %s from S3 (%s → %s) ...", name, s3_key, local_path)
        s3.download_file(bucket, s3_key, str(local_path))
        logger.info("Model %s downloaded successfully", name)
        return local_path

    except Exception:
        logger.warning("Failed to download model %s from S3", name, exc_info=True)
        return None
