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


__all__ = ["BiGRUTAS"]
