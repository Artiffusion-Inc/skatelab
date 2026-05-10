#!/usr/bin/env python3
"""Export MogaNet-B checkpoint to ONNX on a remote GPU instance.

Uses the standalone MogaNet backbone from Westlake-AI/MogaNet (timm-based,
no mmcv dependency) + DeconvHead matching mmpose HeatmapHead.

Architecture (from state_dict analysis):
  - MogaNet-B: embed_dims=[64, 160, 320, 512], depths=[4, 6, 22, 3]
  - Backbone outputs 512 channels at stage 4 (out_indices=(3,))
  - DeconvHead: ConvT(512→256) → BN → ReLU → ConvT(256→256) → BN → ReLU
    → ConvT(256→256) → BN → ReLU → Conv2d(256→17, 1x1)
  - Input: (B, 3, 288, 384), Output: (B, 17, 72, 96) heatmaps

Usage:
    1. Clone https://github.com/Westlake-AI/MogaNet and copy models/moganet.py
       to /workspace/moganet_model.py on the remote instance.
    2. Copy this script and the .pth checkpoint to /workspace/ on the instance.
    3. Run: python3 /workspace/export_moganet_onnx_remote.py

Requires: torch, timm, onnx (available on PyTorch Docker images)
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from moganet_model import MogaNet as MogaNetBackbone


class DeconvHead(nn.Module):
    """Deconvolution head matching mmpose HeatmapHead (in_channels=512).

    deconv_out_channels=(256, 256, 256), deconv_kernel_sizes=(4, 4, 4)
    final_layer: Conv2d(256, 17, kernel_size=1)
    """

    def __init__(self, in_channels: int = 512, out_channels: int = 17):
        super().__init__()
        self.deconv_layers = nn.Sequential(
            nn.ConvTranspose2d(in_channels, 256, 4, 2, 1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(256, 256, 4, 2, 1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(256, 256, 4, 2, 1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
        )
        self.final_layer = nn.Conv2d(256, out_channels, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.deconv_layers(x)
        return self.final_layer(x)


class MogaNetPose(nn.Module):
    """MogaNet-B backbone + deconv head for keypoint estimation."""

    def __init__(self, backbone: nn.Module, keypoint_head: nn.Module):
        super().__init__()
        self.backbone = backbone
        self.keypoint_head = keypoint_head

    def forward(self, img: torch.Tensor) -> torch.Tensor:
        feat = self.backbone(img)
        if isinstance(feat, (list, tuple)):
            feat = feat[-1]
        return self.keypoint_head(feat)


def main() -> None:
    checkpoint_path = Path("/workspace/moganet_b_ap2d_384x288.pth")
    output_path = Path("/workspace/moganet/moganet_b_ap2d_384x288.onnx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading checkpoint: {checkpoint_path}")
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)  # noqa: no-cpu-inference — checkpoint deserialization, not inference
    state_dict = ckpt["state_dict"]
    print(f"  Total state_dict keys: {len(state_dict)}")

    backbone = MogaNetBackbone(
        arch="b",
        patch_sizes=[3, 3, 3, 3],
        in_channels=3,
        drop_rate=0.0,
        drop_path_rate=0.3,
        fork_feat=True,
        frozen_stages=-1,
    )

    head = DeconvHead(in_channels=512, out_channels=17)
    model = MogaNetPose(backbone, head)

    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    missing_non_bn = [k for k in missing if "num_batches_tracked" not in k]
    if missing_non_bn:
        print(f"  Missing keys ({len(missing_non_bn)}):")
        for k in missing_non_bn[:10]:
            print(f"    - {k}")
    if unexpected:
        print(f"  Unexpected keys ({len(unexpected)}):")
        for k in unexpected[:10]:
            print(f"    + {k}")

    model.eval()
    model.cpu()

    h, w = 288, 384
    dummy = torch.randn(1, 3, h, w)

    with torch.no_grad():
        test_out = model(dummy)
        assert test_out.shape == (1, 17, h // 4, w // 4), f"Unexpected: {test_out.shape}"
    print(f"  Forward pass OK: {test_out.shape}")

    print(f"\nExporting ONNX: {output_path}")
    print(f"  Input: (batch, 3, {h}, {w})")
    print(f"  Output: (batch, 17, {h // 4}, {w // 4})")

    torch.onnx.export(
        model,
        dummy,
        str(output_path),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        opset_version=14,
        do_constant_folding=True,
    )

    import onnx

    onnx_model = onnx.load(str(output_path))
    onnx.checker.check_model(onnx_model)

    size_mb = output_path.stat().st_size / 1e6
    print("\nONNX export verified!")
    print(f"  Path: {output_path}")
    print(f"  Size: {size_mb:.1f} MB")
    print("DONE")


if __name__ == "__main__":
    main()
