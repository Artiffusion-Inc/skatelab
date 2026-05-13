"""Tests for BiGRU TAS model."""

import numpy as np
import pytest
import torch

# Direct import to avoid __init__ chain
try:
    from ml.src.tas.model import BiGRUTAS
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from tas.model import BiGRUTAS


def test_bigru_forward():
    model = BiGRUTAS(input_dim=34, hidden_dim=64, num_layers=1)
    B, T, J, C = 2, 100, 17, 2
    poses = torch.randn(B, T, J, C)
    lengths = torch.tensor([100, 80])
    logits = model(poses, lengths)
    assert logits.shape == (B, T, 4)


def test_bigru_variable_length():
    model = BiGRUTAS(hidden_dim=64, num_layers=1)
    B, T = 2, 50
    poses = torch.randn(B, T, 17, 2)
    lengths = torch.tensor([50, 30])
    logits = model(poses, lengths)
    # Padded frames should not be NaN (pack_padded handles this)
    assert not torch.isnan(logits).any()
    # Check shape
    assert logits.shape == (B, T, 4)


def test_bigru_backward():
    """Verify gradients flow through the model."""
    model = BiGRUTAS(hidden_dim=32, num_layers=1)
    poses = torch.randn(2, 20, 17, 2, requires_grad=True)
    lengths = torch.tensor([20, 15])
    logits = model(poses, lengths)
    loss = logits.mean()
    loss.backward()
    assert poses.grad is not None
    assert not torch.isnan(poses.grad).any()


def test_boundary_refiner_forward():
    from src.tas.model import BoundaryRefinerCNN

    refiner = BoundaryRefinerCNN(input_channels=38)
    x = torch.randn(2, 100, 38)
    out = refiner(x)
    assert out.shape == (2, 100, 4)


def test_boundary_refiner_gradient():
    from src.tas.model import BoundaryRefinerCNN

    refiner = BoundaryRefinerCNN(input_channels=38)
    x = torch.randn(2, 50, 38, requires_grad=True)
    out = refiner(x)
    loss = out.mean()
    loss.backward()
    assert x.grad is not None
    assert not torch.isnan(x.grad).any()


if __name__ == "__main__":
    test_bigru_forward()
    print("✓ bigru_forward OK")
    test_bigru_variable_length()
    print("✓ bigru_variable_length OK")
    test_bigru_backward()
    print("✓ bigru_backward OK")
    print("ALL MODEL TESTS PASSED")
