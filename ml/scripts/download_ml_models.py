#!/usr/bin/env python3
"""Download ML model weights for optional pipeline features.

Usage:
    uv run python scripts/download_ml_models.py --all
    uv run python scripts/download_ml_models.py --model depth_anything
    uv run python scripts/download_ml_models.py --list
    uv run python scripts/download_ml_models.py --verify
    uv run python scripts/download_ml_models.py --generate-manifest

Uses huggingface_hub for HuggingFace models (auto-reads HF_TOKEN env var),
urllib for GitHub releases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

MODELS_DIR = Path("data/models")

MANIFEST_PATH = MODELS_DIR / "models.manifest.json"

MODELS: dict[str, dict] = {
    "moganet_b": {
        "source": "s3",
        "s3_key": "models/moganet/moganet_b_ap2d_384x288.onnx",
        "local_filename": "moganet/moganet_b_ap2d_384x288.onnx",
        "size_mb": "~181MB",
        "description": "MogaNet-B pose estimator (AthletePose3D fine-tuned, ONNX)",
    },
    "depth_anything": {
        "source": "hf",
        "repo_id": "onnx-community/depth-anything-v2-small",
        "filename": "onnx/model.onnx",
        "local_filename": "depth_anything_v2_small.onnx",
        "size_mb": "~99MB",
        "description": "Monocular depth estimation (Depth Anything V2 Small)",
    },
    "optical_flow": {
        "source": "url",
        "url": "https://github.com/ibaiGorordo/ONNX-NeuFlowV2-Optical-Flow/releases/download/0.1.0/neuflow_mixed.onnx",
        "local_filename": "neuflowv2_mixed.onnx",
        "size_mb": "~40MB",
        "description": "Dense optical flow (NeuFlowV2 mixed)",
    },
    "sam2_tiny": {
        "source": "hf_multi",
        "repo_id": "onnx-community/sam2.1-hiera-tiny-ONNX",
        "files": [
            ("onnx/vision_encoder.onnx", "sam2/vision_encoder.onnx"),
            ("onnx/vision_encoder.onnx_data", "sam2/vision_encoder.onnx_data"),
            ("onnx/prompt_encoder_mask_decoder.onnx", "sam2/prompt_encoder_mask_decoder.onnx"),
            (
                "onnx/prompt_encoder_mask_decoder.onnx_data",
                "sam2/prompt_encoder_mask_decoder.onnx_data",
            ),
        ],
        "local_filename": "sam2/vision_encoder.onnx",
        "size_mb": "~155MB (4 files in sam2/)",
        "description": "Image segmentation (SAM 2.1 Tiny)",
    },
    "foot_tracker": {
        "source": "manual",
        "local_filename": "foot_tracker.onnx",
        "size_mb": "~10MB",
        "description": "Person and foot detection (FootTrackNet) — requires manual export",
    },
    "video_matting": {
        "source": "hf",
        "repo_id": "LPDoctor/video_matting",
        "filename": "rvm_mobilenetv3_fp32.onnx",
        "local_filename": "rvm_mobilenetv3.onnx",
        "size_mb": "~33MB",
        "description": "Video background removal (RobustVideoMatting MobileNetV3)",
    },
    "lama": {
        "source": "hf",
        "repo_id": "Carve/LaMa-ONNX",
        "filename": "lama_fp32.onnx",
        "local_filename": "lama_fp32.onnx",
        "size_mb": "~208MB",
        "description": "Image inpainting (LAMA Dilated)",
    },
}


def compute_sha256(path: Path) -> str:
    """Compute SHA256 hash of file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    """Load model manifest or return empty dict."""
    if not MANIFEST_PATH.exists():
        return {"version": "1", "models": {}}
    try:
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"version": "1", "models": {}}


def verify_checksum(model_id: str, path: Path, manifest: dict) -> bool:
    """Verify file SHA256 against manifest."""
    model_entry = manifest.get("models", {}).get(model_id)
    if not model_entry or not model_entry.get("sha256"):
        return True  # No hash stored yet
    expected = model_entry["sha256"]
    actual = compute_sha256(path)
    return expected == actual


def download_model(model_id: str) -> None:
    """Download a single model."""
    info = MODELS[model_id]
    source = info["source"]
    manifest = load_manifest()

    if source == "manual":
        print(f"  [MANUAL] {info['description']}")
        print("    Export from: pip install 'qai-hub-models[foot-track-net]'")
        print(
            '    Then: python -c "from qai_hub_models.models.foot_track_net import FootTrackNet; \\'
        )
        print("      m = FootTrackNet.from_pretrained(); m.eval(); \\")
        print(
            '      import torch; torch.onnx.export(m, torch.randn(1,3,480,640), \\"data/models/foot_tracker.onnx\\")"'
        )
        return

    if source == "s3":
        import os

        import boto3
        from botocore.config import Config as BotoConfig

        dest = MODELS_DIR / info["local_filename"]
        if dest.exists():
            print(f"  Already exists: {dest}")
        else:
            s3_endpoint = os.environ.get("S3_ENDPOINT_URL", "")
            s3_key_id = os.environ.get("S3_ACCESS_KEY_ID", "")
            s3_secret = os.environ.get("S3_SECRET_ACCESS_KEY", "")
            s3_bucket = os.environ.get("S3_BUCKET", "")
            s3_region = os.environ.get("S3_REGION", "us-east-1")

            if not all([s3_endpoint, s3_key_id, s3_secret, s3_bucket]):
                print(
                    f"  [SKIP] {info['description']} — set S3 credentials (S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_BUCKET)"
                )
                return

            print(f"  Downloading {info['description']} ({info['size_mb']}) from S3...")
            dest.parent.mkdir(parents=True, exist_ok=True)
            client = boto3.client(
                "s3",
                endpoint_url=s3_endpoint,
                aws_access_key_id=s3_key_id,
                aws_secret_access_key=s3_secret,
                region_name=s3_region,
                config=BotoConfig(s3={"addressing_style": "path"}),
            )
            client.download_file(s3_bucket, info["s3_key"], str(dest))
            print(f"  Saved: {dest}")
        ok = verify_checksum(model_id, dest, manifest)
        if ok:
            print("  [OK] SHA256 verified")
        else:
            expected = manifest.get("models", {}).get(model_id, {}).get("sha256")
            actual = compute_sha256(dest)
            print(f"  [FAIL] SHA256 mismatch! Expected {expected}, got {actual}")
        return

    if source == "hf":
        from huggingface_hub import hf_hub_download

        dest = MODELS_DIR / info["local_filename"]
        if dest.exists():
            print(f"  Already exists: {dest}")
        else:
            print(f"  Downloading {info['description']} ({info['size_mb']})...")
            path = hf_hub_download(
                repo_id=info["repo_id"],
                filename=info["filename"],
                local_dir=MODELS_DIR,
            )
            downloaded = Path(path)
            if downloaded != dest and downloaded.exists():
                downloaded.rename(dest)
            print(f"  Saved: {dest}")
        ok = verify_checksum(model_id, dest, manifest)
        if ok:
            print("  [OK] SHA256 verified")
        else:
            expected = manifest.get("models", {}).get(model_id, {}).get("sha256")
            actual = compute_sha256(dest)
            print(f"  [FAIL] SHA256 mismatch! Expected {expected}, got {actual}")

    elif source == "hf_multi":
        from huggingface_hub import hf_hub_download

        all_exist = all((MODELS_DIR / local).exists() for _, local in info["files"])
        if all_exist:
            print(f"  Already exists: {[MODELS_DIR / loc for _, loc in info['files']]}")
        else:
            print(f"  Downloading {info['description']} ({info['size_mb']})...")
        for hf_file, local_name in info["files"]:
            dest = MODELS_DIR / local_name
            if not dest.exists():
                path = hf_hub_download(
                    repo_id=info["repo_id"],
                    filename=hf_file,
                    local_dir=MODELS_DIR,
                )
                downloaded = Path(path)
                if downloaded != dest and downloaded.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    downloaded.rename(dest)
                print(f"    Saved: {dest}")
            # Verify checksum for each file if manifest has entry for it
            file_entry = manifest.get("models", {}).get(model_id, {})
            file_hashes = file_entry.get("file_hashes", {})
            if file_hashes and local_name in file_hashes:
                expected = file_hashes[local_name]
                actual = compute_sha256(dest)
                if expected == actual:
                    print(f"    [OK] {local_name} SHA256 verified")
                else:
                    print(
                        f"    [FAIL] {local_name} SHA256 mismatch! Expected {expected}, got {actual}"
                    )
        print(f"  Done: {len(info['files'])} files")

    elif source == "url":
        dest = MODELS_DIR / info["local_filename"]
        if dest.exists():
            print(f"  Already exists: {dest}")
        else:
            print(f"  Downloading {info['description']} ({info['size_mb']})...")
            req = urllib.request.Request(info["url"])
            with urllib.request.urlopen(req) as resp:
                data = resp.read()
            dest.write_bytes(data)
            print(f"  Saved: {dest} ({len(data) / 1024 / 1024:.1f}MB)")
        ok = verify_checksum(model_id, dest, manifest)
        if ok:
            print("  [OK] SHA256 verified")
        else:
            expected = manifest.get("models", {}).get(model_id, {}).get("sha256")
            actual = compute_sha256(dest)
            print(f"  [FAIL] SHA256 mismatch! Expected {expected}, got {actual}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download ML model weights")
    parser.add_argument("--all", action="store_true", help="Download all models")
    parser.add_argument(
        "--model",
        type=str,
        choices=list(MODELS.keys()),
        help="Download specific model",
    )
    parser.add_argument("--list", action="store_true", help="List available models")
    parser.add_argument(
        "--verify", action="store_true", help="Verify SHA256 of all existing models"
    )
    parser.add_argument(
        "--generate-manifest", action="store_true", help="Generate manifest from existing models"
    )
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    args = parser.parse_args()

    if args.list:
        print("Available models:")
        for mid, info in MODELS.items():
            src = info["source"]
            tag = {
                "hf": "[HuggingFace]",
                "hf_multi": "[HuggingFace, multi-file]",
                "url": "[GitHub Release]",
                "s3": "[S3]",
                "manual": "[Manual export required]",
            }[src]
            print(f"  {mid}: {info['description']} ({info['size_mb']}) {tag}")
        return

    if args.verify:
        manifest = load_manifest()
        all_ok = True
        for model_id, entry in manifest.get("models", {}).items():
            path = MODELS_DIR / entry["local_filename"]
            if not path.exists():
                print(f"  MISSING: {model_id} ({path})")
                all_ok = False
                continue
            if not entry.get("sha256"):
                print(f"  NO_HASH: {model_id} (run download to compute)")
                continue
            ok = verify_checksum(model_id, path, manifest)
            if ok:
                print(f"  [OK] {model_id}")
            else:
                print(f"  [FAIL] {model_id} — SHA256 mismatch!")
                all_ok = False
        return

    if args.generate_manifest:
        manifest = {
            "version": "1",
            "generated_at": datetime.now(UTC).isoformat(),
            "models": {},
        }
        for model_id, info in MODELS.items():
            path = MODELS_DIR / info["local_filename"]
            if path.exists():
                manifest["models"][model_id] = {
                    "version": "1.0.0",
                    "sha256": compute_sha256(path),
                    "local_filename": info["local_filename"],
                    "size_bytes": path.stat().st_size,
                    "source": info["source"],
                }
                if info["source"] == "hf":
                    manifest["models"][model_id]["repo_id"] = info["repo_id"]
                    manifest["models"][model_id]["filename"] = info["filename"]
                elif info["source"] == "url":
                    manifest["models"][model_id]["url"] = info["url"]
                elif info["source"] == "hf_multi":
                    manifest["models"][model_id]["repo_id"] = info["repo_id"]
                    file_hashes = {}
                    for hf_file, local_name in info["files"]:
                        file_path = MODELS_DIR / local_name
                        if file_path.exists():
                            file_hashes[local_name] = compute_sha256(file_path)
                    manifest["models"][model_id]["file_hashes"] = file_hashes
            else:
                manifest["models"][model_id] = {
                    "version": "1.0.0",
                    "sha256": None,
                    "local_filename": info["local_filename"],
                    "size_bytes": None,
                    "source": info["source"],
                }
                if info["source"] == "hf":
                    manifest["models"][model_id]["repo_id"] = info["repo_id"]
                    manifest["models"][model_id]["filename"] = info["filename"]
                elif info["source"] == "url":
                    manifest["models"][model_id]["url"] = info["url"]
                elif info["source"] == "hf_multi":
                    manifest["models"][model_id]["repo_id"] = info["repo_id"]
        with open(MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"Manifest written to {MANIFEST_PATH}")
        return

    if args.all:
        print("Downloading all models...")
        for model_id in MODELS:
            download_model(model_id)
        print("Done!")
    elif args.model:
        download_model(args.model)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
