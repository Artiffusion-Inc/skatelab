"""Export TAS models to ONNX for serverless inference.

Usage:
    uv run python experiments/export_tas_onnx.py --checkpoint experiments/checkpoints/tas_v2/fold_0_best.pt
    uv run python experiments/export_tas_onnx.py --checkpoint ... --fine-classifier experiments/checkpoints/fine_classifier/pretrain_jump_best.pt
"""

import argparse
from pathlib import Path

import torch

from ml.src.tas.classifier import Skeleton1DCNN
from ml.src.tas.model import BiGRUTASRefiner


def export_coarse_model(checkpoint_path: Path, output_path: Path) -> None:
    """Export BiGRUTASRefiner to ONNX."""
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    config = ckpt.get("config", {})
    model = BiGRUTASRefiner(
        input_dim=config.get("input_dim", 34),
        hidden_dim=config.get("hidden_dim", 128),
        num_layers=config.get("num_layers", 2),
        num_classes=config.get("num_classes", 4),
        dropout=0.0,  # No dropout at inference
        refiner_channels=config.get("refiner_channels", 64),
    )
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    dummy_poses = torch.randn(1, 300, 17, 2)
    dummy_lengths = torch.tensor([300], dtype=torch.long)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        (dummy_poses, dummy_lengths),
        str(output_path),
        input_names=["poses", "lengths"],
        output_names=["logits"],
        dynamic_axes={
            "poses": {0: "batch", 1: "time"},
            "lengths": {0: "batch"},
            "logits": {0: "batch", 1: "time"},
        },
        opset_version=17,
        dynamo=False,  # pack_padded_sequence requires legacy exporter
    )
    print(f"Coarse model exported: {output_path}")
    print(f"  Size: {output_path.stat().st_size / 1024:.1f} KB")


def export_fine_classifier(checkpoint_path: Path, output_path: Path) -> None:
    """Export Skeleton1DCNN to ONNX.

    Note: Skeleton1DCNN outputs (B, num_classes) — one prediction per
    sequence, not per frame. The duration feature is concatenated after
    pooling so AdaptiveMaxPool does not lose temporal information.
    """
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    num_classes = ckpt.get("num_classes", 15)
    model = Skeleton1DCNN(
        input_dim=34,
        num_classes=num_classes,
        dropout=0.0,
    )
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    dummy_x = torch.randn(1, 120, 34)
    dummy_lengths = torch.tensor([120], dtype=torch.long)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        (dummy_x, dummy_lengths),
        str(output_path),
        input_names=["poses_flat", "lengths"],
        output_names=["logits"],
        dynamic_axes={
            "poses_flat": {0: "batch", 1: "time"},
            "lengths": {0: "batch"},
            "logits": {0: "batch"},
        },
        opset_version=17,
        dynamo=False,
    )
    print(f"Fine classifier exported: {output_path}")
    print(f"  Size: {output_path.stat().st_size / 1024:.1f} KB")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to BiGRUTASRefiner checkpoint")
    parser.add_argument("--output", type=Path, default=None, help="Output ONNX path (default: data/models/tas/bigr_refiner_best.onnx)")
    parser.add_argument("--fine-classifier", type=Path, default=None, help="Path to Skeleton1DCNN checkpoint (optional)")
    parser.add_argument("--fine-output", type=Path, default=None, help="Output path for fine classifier ONNX")
    args = parser.parse_args()

    output = args.output or Path("data/models/tas/bigr_refiner_best.onnx")
    export_coarse_model(args.checkpoint, output)

    if args.fine_classifier:
        fine_output = args.fine_output or Path("data/models/tas/skeleton1dcnn_best.onnx")
        export_fine_classifier(args.fine_classifier, fine_output)


if __name__ == "__main__":
    main()
