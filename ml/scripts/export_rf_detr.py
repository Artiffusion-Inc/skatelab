#!/usr/bin/env python3
"""Export RF-DETR PyTorch models to ONNX.

Requires: Python 3.12, rfdetr >=1.7.0
Usage:
    uv run python scripts/export_rf_detr.py --model nano
    uv run python scripts/export_rf_detr.py --model small
    uv run python scripts/export_rf_detr.py --model medium
    uv run python scripts/export_rf_detr.py --all
"""

import argparse
from pathlib import Path

MODELS = {
    "nano": {"hub_id": "roboflow/rf-detr-nano", "size": 384},
    "small": {"hub_id": "roboflow/rf-detr-small", "size": 512},
    "medium": {"hub_id": "roboflow/rf-detr-medium", "size": 576},
}

OUTPUT_DIR = Path("data/models")


def export_model(name: str, config: dict) -> Path:
    """Export a single RF-DETR model to ONNX."""
    from rfdetr import RFDETRBase

    print(f"Loading {name} ({config['hub_id']})...")
    model = RFDETRBase.from_pretrained(config["hub_id"])

    out_path = OUTPUT_DIR / f"rf_detr_{name}.onnx"
    print(f"Exporting to {out_path}...")

    model.to_onnx(
        str(out_path),
        opset=17,
        dynamic_batch=False,
    )

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Done: {out_path} ({size_mb:.1f} MB)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export RF-DETR to ONNX")
    parser.add_argument(
        "--model",
        choices=[*list(MODELS.keys()), "all"],
        default="all",
        help="Model variant to export",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.model == "all":
        for name, config in MODELS.items():
            export_model(name, config)
    else:
        export_model(args.model, MODELS[args.model])


if __name__ == "__main__":
    main()
