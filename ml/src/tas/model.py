"""BiGRU model for frame-wise coarse temporal action segmentation.

Input: (B, T, 17, 2) normalized H3.6M poses
Output: (B, T, 4) logits for [None, Jump, Spin, Step]
"""

import torch
from torch import nn


class BiGRUTAS(nn.Module):
    """BiGRU for frame-wise coarse temporal action segmentation."""

    def __init__(
        self,
        input_dim: int = 34,  # 17 joints × 2 coords
        hidden_dim: int = 128,
        num_layers: int = 2,
        num_classes: int = 4,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim

        # Flatten (17, 2) → 34 per frame
        self.proj = nn.Linear(input_dim, hidden_dim)

        self.gru = nn.GRU(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        # BiGRU output: 2 × hidden_dim
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, num_classes),
        )

    def forward(
        self,
        poses: torch.Tensor,
        lengths: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            poses: (B, T, 17, 2)
            lengths: (B,) original sequence lengths
        Returns:
            logits: (B, T, 4)
        """
        B, T, J, C = poses.shape
        # Flatten joints
        x = poses.reshape(B, T, J * C)  # (B, T, 34)
        x = self.proj(x)  # (B, T, hidden_dim)

        # Pack for RNN
        packed = nn.utils.rnn.pack_padded_sequence(
            x, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        packed_out, _ = self.gru(packed)
        out, _ = nn.utils.rnn.pad_packed_sequence(packed_out, batch_first=True)

        logits = self.classifier(out)  # (B, T, 4)
        return logits


class BoundaryRefinerCNN(nn.Module):
    """Refines coarse BiGRU logits using local CNN context.

    Input: (B, T, 38) — 4 coarse logits + 34 raw pose features
    Output: (B, T, 4) — refined logits
    """

    def __init__(
        self,
        input_channels: int = 38,
        hidden_channels: int = 64,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(input_channels, hidden_channels, kernel_size=9, padding="same")
        self.conv2 = nn.Conv1d(hidden_channels, hidden_channels, kernel_size=9, padding="same")
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_channels, 4)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Args: x: (B, T, 38) — coarse logits + raw features concatenated."""
        x = x.permute(0, 2, 1)  # (B, 38, T)
        x = torch.relu(self.conv1(x))
        x = self.dropout(x)
        x = torch.relu(self.conv2(x))
        x = x.permute(0, 2, 1)  # (B, T, 64)
        return self.classifier(x)


class BiGRUTASRefiner(nn.Module):
    """BiGRU coarse + BoundaryRefinerCNN two-pass model.

    First pass: BiGRU produces coarse logits.
    Second pass: RefinerCNN refines boundaries using logits + raw features.
    """

    def __init__(
        self,
        input_dim: int = 34,
        hidden_dim: int = 128,
        num_layers: int = 2,
        num_classes: int = 4,
        dropout: float = 0.3,
        refiner_channels: int = 64,
    ) -> None:
        super().__init__()
        self.bigru = BiGRUTAS(
            input_dim=input_dim,
            hidden_dim=hidden_dim,
            num_layers=num_layers,
            num_classes=num_classes,
            dropout=dropout,
        )
        self.refiner = BoundaryRefinerCNN(
            input_channels=num_classes + input_dim,
            hidden_channels=refiner_channels,
            dropout=dropout,
        )

    def forward(self, poses: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        """Two-pass: BiGRU coarse → RefinerCNN refined.

        Args:
            poses: (B, T, 17, 2)
            lengths: (B,)

        Returns:
            logits: (B, T, 4) — refined
        """
        B, T, J, C = poses.shape
        coarse_logits = self.bigru(poses, lengths)  # (B, T, 4)
        raw_features = poses.reshape(B, T, J * C)  # (B, T, 34)
        refiner_input = torch.cat([coarse_logits, raw_features], dim=-1)  # (B, T, 38)
        refined_logits = self.refiner(refiner_input)  # (B, T, 4)
        return refined_logits


__all__ = ["BiGRUTAS", "BiGRUTASRefiner", "BoundaryRefinerCNN"]
