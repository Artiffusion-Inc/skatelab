"""RED repro for Bug #185 / issue #818.

BoundaryRefinerCNN used even kernel (k=10) with padding='same', which yields
asymmetric padding (left=4, right=5) and a half-frame temporal shift per layer.
Two stacked layers compound to ~1 frame cumulative shift, misaligning refined
boundary logits from the input frames. The fix is an ODD kernel so that
padding='same' is symmetric (pad = (k-1)//2 each side).
"""

import inspect

import pytest
import torch

try:
    from ml.src.tas.model import BoundaryRefinerCNN
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from tas.model import BoundaryRefinerCNN  # type: ignore[no-redef]


def test_conv1_kernel_is_odd() -> None:
    """conv1 must use an ODD kernel (9 or 11), not the buggy even k=10."""
    refiner = BoundaryRefinerCNN(input_channels=38, hidden_channels=16)
    k1 = refiner.conv1.kernel_size[0]
    assert k1 % 2 == 1, f"conv1 kernel_size must be odd, got {k1}"
    assert k1 != 10, f"conv1 kernel_size must not be 10 (bug #818), got {k1}"


def test_conv2_kernel_is_odd() -> None:
    """conv2 must use an ODD kernel (9 or 11), not the buggy even k=10."""
    refiner = BoundaryRefinerCNN(input_channels=38, hidden_channels=16)
    k2 = refiner.conv2.kernel_size[0]
    assert k2 % 2 == 1, f"conv2 kernel_size must be odd, got {k2}"
    assert k2 != 10, f"conv2 kernel_size must not be 10 (bug #818), got {k2}"


def test_forward_preserves_length() -> None:
    """Forward output temporal length must equal input length (no shift, no shrink)."""
    torch.manual_seed(0)
    refiner = BoundaryRefinerCNN(input_channels=38, hidden_channels=16)
    for T in (17, 50, 100):
        x = torch.randn(2, T, 38)
        out = refiner(x)
        # out is (B, T, 4) — temporal dim is dim 1, not dim -1 (channels=4).
        assert out.shape[1] == T, f"T={T}: out len {out.shape[1]} != input len {T}"
        assert out.shape == (2, T, 4)


def test_impulse_response_centered() -> None:
    """An impulse at the center frame should peak at the same index (no shift).

    With symmetric (odd-kernel) padding the conv1 response to a centered
    impulse is symmetric about the impulse index. With the buggy even k=10 the
    response peak shifts by ~1 frame. We assert the response energy is
    symmetric about the impulse index, which only holds for odd kernels.
    """
    refiner = BoundaryRefinerCNN(input_channels=38, hidden_channels=16)
    # Replace conv1 with a constant moving-sum filter (all ones, zero bias) so
    # the conv becomes a deterministic sum over the kernel window. The response
    # to an impulse is a plateau spanning the receptive field; its center of
    # mass is exactly at the impulse index iff padding is symmetric. Even
    # kernels with padding='same' shift the center of mass by half a frame.
    with torch.no_grad():
        refiner.conv1.weight.fill_(1.0)
        refiner.conv1.bias.zero_()
    T = 101
    center = T // 2  # 50
    x = torch.zeros(1, T, 38)
    x[0, center, :] = 1.0
    # Capture conv1 output by bypassing the rest of forward.
    h = x.permute(0, 2, 1)  # (1, 38, T)
    h = torch.relu(refiner.conv1(h))  # (1, hidden, T)
    # Sum over channels → per-frame response magnitude (moving sum).
    resp = h.sum(dim=1).squeeze(0).detach()  # (T,)
    # Center of mass of the response — must coincide with the impulse index.
    indices = torch.arange(T, dtype=torch.float32)
    com = float((resp * indices).sum().item() / resp.sum().item())
    assert abs(com - center) < 0.5, (
        f"impulse at {center}, response center-of-mass at {com:.3f} — "
        f"shifted by {abs(com - center):.3f} frames (asymmetric padding)"
    )
    # Stronger: response must be left/right symmetric about the center.
    left = resp[:center].flip(0)
    right = resp[center + 1 :]
    n = min(left.numel(), right.numel())
    if n > 0:
        asym = (left[:n] - right[:n]).abs().max().item()
        assert asym < 1e-5, f"response not symmetric about impulse center (max asym {asym:.2e})"


def test_source_uses_odd_kernel() -> None:
    """Source of BoundaryRefinerCNN must not contain kernel_size=10."""
    src = inspect.getsource(BoundaryRefinerCNN)
    # The buggy line had kernel_size=10; the fix must remove all of them.
    assert "kernel_size=10" not in src, (
        "BoundaryRefinerCNN source still contains kernel_size=10 (bug #818)"
    )
    # And every Conv1d in the class must declare an odd kernel_size.
    for line in src.splitlines():
        if "nn.Conv1d(" in line and "kernel_size=" in line:
            # extract the kernel_size=N literal
            marker = "kernel_size="
            idx = line.find(marker) + len(marker)
            rest = line[idx:]
            num = ""
            for ch in rest:
                if ch.isdigit():
                    num += ch
                else:
                    break
            assert num, f"could not parse kernel_size in line: {line.strip()}"
            assert int(num) % 2 == 1, f"Conv1d kernel_size={num} is even in: {line.strip()}"


if __name__ == "__main__":
    pytest.main([__file__, "-q", "-p", "no:cacheprovider", "--no-cov"])
