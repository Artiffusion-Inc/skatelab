#!/usr/bin/env python3
"""Generate pre-signed S3 URLs for ONNX models.

Used at Docker build time to embed models into the image.
URLs expire after 1 hour — generate immediately before build.

Usage:
    uv run python scripts/generate_model_presigned_urls.py --output /tmp/model_urls.json

Requires env vars: S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_BUCKET
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import boto3


MODELS = {
    "moganet": "models/moganet/moganet_b_ap2d_384x288.onnx",
    "yolo": "models/yolov8n.onnx",
}

DEFAULT_EXPIRES = 3600  # 1 hour


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate pre-signed S3 URLs for model download")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument(
        "--expires", type=int, default=DEFAULT_EXPIRES, help="URL expiry in seconds"
    )
    args = parser.parse_args()

    endpoint = os.environ.get("S3_ENDPOINT_URL", "")
    access_key = os.environ.get("S3_ACCESS_KEY_ID", "")
    secret = os.environ.get("S3_SECRET_ACCESS_KEY", "")
    bucket = os.environ.get("S3_BUCKET", "")
    region = os.environ.get("S3_REGION", "us-east-1")

    missing = [
        k
        for k, v in {
            "S3_ENDPOINT_URL": endpoint,
            "S3_ACCESS_KEY_ID": access_key,
            "S3_SECRET_ACCESS_KEY": secret,
            "S3_BUCKET": bucket,
        }.items()
        if not v
    ]

    if missing:
        print(f"Missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret,
        region_name=region,
        config={"s3": {"addressing_style": "path"}},
    )

    urls: dict[str, str] = {}
    for name, key in MODELS.items():
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=args.expires,
        )
        urls[name] = url
        print(f"  {name}: {key} → URL generated (expires in {args.expires}s)")

    with open(args.output, "w") as f:
        json.dump(urls, f, indent=2)
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
