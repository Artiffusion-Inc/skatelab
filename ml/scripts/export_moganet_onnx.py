"""Export MogaNet-B .pth checkpoint to ONNX format.

Usage:
    python scripts/export_moganet_onnx.py [--checkpoint PATH] [--output PATH]

Requires: mmcv-full, mmseg, torch, onnx
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch


def build_moganet_b():
    """Build MogaNet-B backbone + SimCC head from mmseg/mmpose configs."""
    from mmseg.models import MogaNet
    from mmpose.models import HEADS, PoseEstimator

    # MogaNet-B config (from AthletePose3D fine-tune)
    backbone = MogaNet(
        arch="b",
        patch_sizes=3,
        in_channels=3,
        embed_dims=64,
        drop_rate=0.0,
        drop_path_rate=0.3,
        out_indices=(3,),
        frozen_stages=-1,
    )

    @HEADS.register_module()
    class SimpleHead(torch.nn.Module):
        """Deconv + 1x1 conv head for 17 keypoints."""

        def __init__(self, in_channels=256, out_channels=17, deconv_layers=3):
            super().__init__()
            layers = []
            ch = in_channels
            for _ in range(deconv_layers):
                layers.append(
                    torch.nn.Sequential(
                        torch.nn.ConvTranspose2d(
                            ch, ch, kernel_size=4, stride=2, padding=1, bias=False
                        ),
                        torch.nn.BatchNorm2d(ch),
                        torch.nn.ReLU(inplace=True),
                    )
                )
            self.deconv_layers = torch.nn.Sequential(*layers)
            self.final_layer = torch.nn.Conv2d(ch, out_channels, kernel_size=1)

        def forward(self, x):
            x = self.deconv_layers(x)
            return self.final_layer(x)

    head = SimpleHead(in_channels=256, out_channels=17)

    class MogaNetPose(torch.nn.Module):
        def __init__(self, backbone, head):
            super().__init__()
            self.backbone = backbone
            self.keypoint_head = head

        def forward(self, img):
            feat = self.backbone(img)[0]
            out = self.keypoint_head(feat)
            return out

    model = MogaNetPose(backbone, head)
    return model


def export_onnx(checkpoint_path: str, output_path: str, input_size: tuple = (288, 384)):
    """Load .pth checkpoint and export to ONNX."""
    checkpoint_path = Path(checkpoint_path)
    output_path = Path(output_path)

    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    print(f"Loading checkpoint: {checkpoint_path}")
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state_dict = ckpt["state_dict"]

    print(f"State dict keys: {len(state_dict)}")

    # Try mmcv-based build first
    try:
        from mmcv import Config  # pyright: ignore[reportMissingImports]

        model = build_moganet_b()
    except ImportError:
        print("mmcv not available, building model from state_dict structure...")
        model = build_from_state_dict(state_dict)

    # Load weights
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    if missing:
        print(f"Missing keys ({len(missing)}): {missing[:5]}...")
    if unexpected:
        print(f"Unexpected keys ({len(unexpected)}): {unexpected[:5]}...")

    model.eval()

    # Export
    h, w = input_size
    dummy_input = torch.randn(1, 3, h, w)

    print(f"Exporting to ONNX: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        dummy_input,
        str(output_path),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch"},
            "output": {0: "batch"},
        },
        opset_version=14,
        do_constant_folding=True,
    )

    # Verify
    import onnx  # pyright: ignore[reportMissingImports]

    onnx_model = onnx.load(str(output_path))
    onnx.checker.check_model(onnx_model)
    print(f"ONNX export verified: {output_path}")
    print(f"  Input: (batch, 3, {h}, {w})")
    print(f"  Output: (batch, 17, {h // 4}, {w // 4})")
    print(f"  Size: {output_path.stat().st_size / 1e6:.1f} MB")


def build_from_state_dict(state_dict: dict) -> torch.nn.Module:
    """Build MogaNet-B + deconv head from state_dict structure analysis.

    This is a fallback when mmcv/mmseg are not available.
    Reconstructs the model architecture by analyzing key naming patterns.
    """
    from torch import nn

    # Analyze backbone structure
    backbone_keys = [k for k in state_dict if k.startswith("backbone.")]
    head_keys = [k for k in state_dict if k.startswith("keypoint_head.")]

    print(f"Backbone keys: {len(backbone_keys)}")
    print(f"Head keys: {len(head_keys)}")

    # Count stages
    stages = set()
    for k in backbone_keys:
        parts = k[len("backbone.") :].split(".")
        if parts[0].startswith("blocks"):
            stages.add(int(parts[0][6:]))  # blocks1, blocks2, etc.
    print(f"Detected stages: {sorted(stages)}")

    # This approach is too complex to reconstruct correctly.
    # mmcv/mmseg is required for proper model building.
    raise ImportError(
        "Cannot build MogaNet-B model without mmcv/mmseg. "
        "Install with: pip install mmcv-full==1.3.17 mmseg"
    )


def main():
    parser = argparse.ArgumentParser(description="Export MogaNet-B to ONNX")
    parser.add_argument(
        "--checkpoint",
        default="data/models/moganet_b_ap2d_384x288.pth",
        help="Path to .pth checkpoint",
    )
    parser.add_argument(
        "--output",
        default="data/models/moganet/moganet_b_ap2d_384x288.onnx",
        help="Output ONNX path",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=288,
        help="Input height",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=384,
        help="Input width",
    )
    args = parser.parse_args()
    export_onnx(args.checkpoint, args.output, input_size=(args.height, args.width))


if __name__ == "__main__":
    main()
