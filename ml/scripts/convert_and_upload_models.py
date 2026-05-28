#!/usr/bin/env python3
"""Convert ONNX models to FP16 and upload to RustFS (S3).

Converts all production pipeline ONNX models from FP32 to FP16 using
onnxconverter-common. FP16 halves VRAM with <1mm MPJPE increase.
Input/output tensors remain FP32 for onnxruntime compatibility.

After conversion, uploads FP16 models to S3 so the Containerfile can
download them via pre-signed URL at build time.

Usage:
    # Convert all models to FP16 (requires local FP32 models)
    uv run python scripts/convert_and_upload_models.py --convert

    # Upload FP16 models to S3
    uv run python scripts/convert_and_upload_models.py --upload

    # Convert + upload
    uv run python scripts/convert_and_upload_models.py --convert --upload

    # Convert a single model
    uv run python scripts/convert_and_upload_models.py --convert --model moganet_b

    # List models and status
    uv run python scripts/convert_and_upload_models.py --list

Requires: onnxconverter-common (pip install onnxconverter-common)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MODELS_DIR = Path("data/models")

# Production pipeline models that run on GPU worker.
# These are the ones loaded in gpu_server/server.py and Containerfile.
PIPELINE_MODELS: dict[str, dict] = {
    "moganet_b": {
        "fp32_path": "moganet/moganet_b_ap2d_384x288.onnx",
        "fp16_path": "moganet/moganet_b_ap2d_384x288_fp16.onnx",
        "s3_key": "models/moganet/moganet_b_ap2d_384x288_fp16.onnx",
        "size_mb_fp32": "~181MB",
        "size_mb_fp16": "~90MB",
        "description": "MogaNet-B pose estimator (AthletePose3D fine-tuned)",
    },
    "rf_detr_nano": {
        "fp32_path": "rf_detr_nano.onnx",
        "fp16_path": "rf_detr_nano_fp16.onnx",
        "s3_key": "models/rf_detr_nano_fp16.onnx",
        "size_mb_fp32": "~120MB",
        "size_mb_fp16": "~60MB",
        "description": "RF-DETR-Nano person detector (384x384)",
    },
    "tcpformer": {
        "fp32_path": "tcpformer/TCPFormer_ap3d_81.onnx",
        "fp16_path": "tcpformer/TCPFormer_ap3d_81_fp16.onnx",
        "s3_key": "models/tcpformer/TCPFormer_ap3d_81_fp16.onnx",
        "size_mb_fp32": "~210MB",
        "size_mb_fp16": "~105MB",
        "description": "TCPFormer 3D pose lifter (81-frame window)",
    },
}


def convert_to_fp16(input_path: Path, output_path: Path) -> bool:
    """Convert ONNX FP32 model to FP16 (keep IO in FP32).

    Args:
        input_path: Path to source FP32 ONNX model.
        output_path: Path to write FP16 ONNX model.

    Returns:
        True if conversion succeeded.
    """
    try:
        import onnx
        from onnxconverter_common import float16
    except ImportError as exc:
        msg = (
            f"{exc}\n\n"
            "onnxconverter-common is required for FP16 conversion.\n"
            "Install with: pip install onnxconverter-common"
        )
        raise SystemExit(msg) from exc

    if not input_path.exists():
        print(f"  [SKIP] FP32 model not found: {input_path}")
        return False

    if output_path.exists():
        print(f"  [EXISTS] FP16 model already exists: {output_path}")
        return True

    print(f"  Converting: {input_path} -> {output_path}")
    model = onnx.load(str(input_path))
    model_fp16 = float16.convert_float_to_float16(model, keep_io_types=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model_fp16, str(output_path))

    orig_size = input_path.stat().st_size
    new_size = output_path.stat().st_size
    ratio = new_size / orig_size * 100
    print(f"  Size: {orig_size / 1e6:.1f} MB -> {new_size / 1e6:.1f} MB ({ratio:.0f}%)")
    return True


def upload_to_s3(local_path: Path, s3_key: str) -> bool:
    """Upload a file to RustFS (S3).

    Uses environment variables for S3 credentials:
    S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_BUCKET, S3_REGION

    Args:
        local_path: Local file to upload.
        s3_key: S3 object key.

    Returns:
        True if upload succeeded.
    """
    import boto3
    from botocore.config import Config as BotoConfig

    s3_endpoint = os.environ.get("S3_ENDPOINT_URL", "")
    s3_key_id = os.environ.get("S3_ACCESS_KEY_ID", "")
    s3_secret = os.environ.get("S3_SECRET_ACCESS_KEY", "")
    s3_bucket = os.environ.get("S3_BUCKET", "")
    s3_region = os.environ.get("S3_REGION", "us-east-1")

    if not all([s3_endpoint, s3_key_id, s3_secret, s3_bucket]):
        print(
            "  [SKIP] S3 credentials not set. "
            "Set S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_BUCKET"
        )
        return False

    if not local_path.exists():
        print(f"  [SKIP] File not found: {local_path}")
        return False

    client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=s3_key_id,
        aws_secret_access_key=s3_secret,
        region_name=s3_region,
        config=BotoConfig(s3={"addressing_style": "path"}),
    )

    print(f"  Uploading: {local_path} -> s3://{s3_bucket}/{s3_key}")
    client.upload_file(str(local_path), s3_bucket, s3_key)
    print("  [OK] Uploaded")
    return True


def list_models() -> None:
    """Print model status table."""
    print(f"{'Model':<15} {'FP32':>10} {'FP16':>10} {'FP32 exists':>12} {'FP16 exists':>12}")
    print("-" * 65)
    for name, info in PIPELINE_MODELS.items():
        fp32_path = MODELS_DIR / info["fp32_path"]
        fp16_path = MODELS_DIR / info["fp16_path"]
        fp32_size = f"{fp32_path.stat().st_size / 1e6:.0f}MB" if fp32_path.exists() else "-"
        fp16_size = f"{fp16_path.stat().st_size / 1e6:.0f}MB" if fp16_path.exists() else "-"
        fp32_ok = "YES" if fp32_path.exists() else "NO"
        fp16_ok = "YES" if fp16_path.exists() else "NO"
        print(f"{name:<15} {fp32_size:>10} {fp16_size:>10} {fp32_ok:>12} {fp16_ok:>12}")
    print()
    total_fp16 = sum(
        (MODELS_DIR / m["fp16_path"]).stat().st_size
        for m in PIPELINE_MODELS.values()
        if (MODELS_DIR / m["fp16_path"]).exists()
    )
    print(f"Total FP16 VRAM estimate: {total_fp16 / 1e6:.0f}MB")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert ONNX models to FP16 and upload to RustFS (S3)"
    )
    parser.add_argument("--convert", action="store_true", help="Convert FP32 models to FP16")
    parser.add_argument("--upload", action="store_true", help="Upload FP16 models to S3")
    parser.add_argument(
        "--model",
        type=str,
        choices=list(PIPELINE_MODELS.keys()),
        help="Operate on a single model (default: all)",
    )
    parser.add_argument("--list", action="store_true", help="List models and status")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if args.list:
        list_models()
        return

    if not args.convert and not args.upload:
        parser.print_help()
        return

    models = {args.model: PIPELINE_MODELS[args.model]} if args.model else PIPELINE_MODELS

    for name, info in models.items():
        print(f"\n{'=' * 50}")
        print(f"Model: {name} — {info['description']}")
        print(f"{'=' * 50}")

        fp32_path = MODELS_DIR / info["fp32_path"]
        fp16_path = MODELS_DIR / info["fp16_path"]

        if args.convert:
            convert_to_fp16(fp32_path, fp16_path)

        if args.upload:
            upload_to_s3(fp16_path, info["s3_key"])

    print("\nDone!")


if __name__ == "__main__":
    main()
