"""Experiment: TAS BiGRU+Refiner v2 with differentiable duration prior loss.

Hypothesis: BiGRUTASRefiner (two-pass coarse+refine) with duration prior loss
achieves >0.75 OverlapF1@50 on MCFS 4-class segmentation, improving over the
BiGRU-only baseline (~0.70) by enforcing minimum segment durations via
soft probability penalties.

Status: PENDING

Usage:
    uv run python experiments/train_tas_v2.py
"""

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.model_selection import KFold
from torch import nn
from torch.utils.data import DataLoader, Subset

from ml.src.tas.dataset import BucketBatchSampler, MCFSCoarseDataset, pad_collate
from ml.src.tas.metrics import MultiOverlapF1
from ml.src.tas.model import BiGRUTASRefiner

BASE = Path("data/datasets/mcfs")
CHECKPOINT_DIR = Path("experiments/checkpoints/tas_v2")
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

# Training hyperparameters
HIDDEN_DIM = 128
NUM_LAYERS = 2
REFINER_CHANNELS = 64
DROPOUT = 0.3
LR = 1e-3
EPOCHS = 80
BATCH_SIZE = 12
DURATION_WEIGHT = 0.1
NUM_CLASSES = 4
MIN_FRAMES = 15


def _duration_prior_loss(
    logits: torch.Tensor,
    lengths: torch.Tensor,
    device: torch.device,
    min_frames: int = MIN_FRAMES,
) -> torch.Tensor:
    """Penalize short predicted segments using soft probabilities (differentiable).

    Uses softmax over logits to get per-frame class probabilities, then
    computes 1 - P(None) as the "element presence" signal. A 1D convolution
    smooths this signal, and short high-probability bursts are penalized
    via (smoothed * (1 - smoothed)).mean — maximized at 0.5 (uncertain)
    and minimized at 0 or 1 (confident), so it penalizes segments that
    are confident only in short bursts.

    Args:
        logits: (B, T, C) raw model outputs.
        lengths: (B,) actual sequence lengths.
        device: torch device.
        min_frames: Minimum expected segment length (conv kernel size).

    Returns:
        Scalar loss (averaged over batch).
    """
    probs = F.softmax(logits, dim=-1)  # (B, T, C)
    non_none_prob = 1.0 - probs[:, :, 0]  # (B, T)
    loss = torch.tensor(0.0, device=device)
    for b in range(logits.shape[0]):
        le = lengths[b].item()
        p = non_none_prob[b, :le]
        kernel = torch.ones(min_frames, device=device) / min_frames
        smoothed = F.conv1d(
            p.unsqueeze(0).unsqueeze(0),
            kernel.unsqueeze(0).unsqueeze(0),
            padding=min_frames // 2,
        ).squeeze()
        short_penalty = (smoothed * (1 - smoothed)).mean()
        loss = loss + short_penalty
    return loss / logits.shape[0]


def train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
    duration_weight: float = DURATION_WEIGHT,
) -> float:
    """Train one epoch with CE + duration prior loss."""
    model.train()
    total_loss = 0.0
    for poses, labels, lengths in loader:
        poses, labels, lengths = poses.to(device), labels.to(device), lengths.to(device)
        optimizer.zero_grad()
        logits = model(poses, lengths)  # (B, T, 4)
        ce_loss = criterion(logits.view(-1, NUM_CLASSES), labels.view(-1))
        dur_loss = _duration_prior_loss(logits, lengths, device)
        loss = ce_loss + duration_weight * dur_loss
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    return total_loss / len(loader)


def eval_fold(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
) -> dict:
    """Evaluate model on a fold using MultiOverlapF1 at multiple IoU thresholds."""
    model.eval()
    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50])
    all_results: list[dict[str, float]] = []
    with torch.no_grad():
        for poses, labels, lengths in loader:
            poses = poses.to(device)
            logits = model(poses, lengths)
            preds = logits.argmax(dim=-1).cpu().numpy()
            for i, le in enumerate(lengths):
                result = metric.compute(preds[i, :le], labels[i, :le].numpy())
                all_results.append(result)

    # Average metrics across samples
    keys = all_results[0].keys()
    avg = {k: float(np.mean([r[k] for r in all_results])) for k in keys}
    return avg


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    ds = MCFSCoarseDataset(BASE / "features", BASE / "groundTruth")
    print(f"Dataset size: {len(ds)}")

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    fold_results: list[dict[str, float]] = []

    for fold, (train_idx, val_idx) in enumerate(kf.split(range(len(ds)))):
        print(f"\n--- Fold {fold + 1}/5 ---")
        train_ds = Subset(ds, train_idx.tolist())
        val_ds = Subset(ds, val_idx.tolist())

        # BucketBatchSampler for efficient padding
        train_lengths = [ds[i][2] for i in train_idx.tolist()]
        train_sampler = BucketBatchSampler(
            lengths=train_lengths,
            batch_size=BATCH_SIZE,
            bin_size=50,
            shuffle=True,
            seed=42,
        )

        # Conditional DataLoader kwargs
        is_cuda = device.type == "cuda"
        loader_kwargs: dict = {}
        if is_cuda:
            loader_kwargs["pin_memory"] = True
        num_workers = 0  # Pre-loaded in RAM, no workers needed
        loader_kwargs["num_workers"] = num_workers
        if num_workers > 0:
            loader_kwargs["persistent_workers"] = True

        train_sampler.set_epoch(0)  # Initial epoch
        train_loader = DataLoader(
            train_ds,
            batch_sampler=train_sampler,
            collate_fn=pad_collate,
            **loader_kwargs,
        )
        val_loader = DataLoader(
            val_ds,
            batch_size=BATCH_SIZE,
            shuffle=False,
            collate_fn=pad_collate,
            **loader_kwargs,
        )

        model = BiGRUTASRefiner(
            hidden_dim=HIDDEN_DIM,
            num_layers=NUM_LAYERS,
            dropout=DROPOUT,
            refiner_channels=REFINER_CHANNELS,
        ).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=LR)
        criterion = nn.CrossEntropyLoss(ignore_index=-1)

        best_f1 = 0.0
        for epoch in range(EPOCHS):
            # Reshuffle bucket sampler each epoch
            train_sampler.set_epoch(epoch)
            train_loader = DataLoader(
                train_ds,
                batch_sampler=train_sampler,
                collate_fn=pad_collate,
                **loader_kwargs,
            )

            train_loss = train_epoch(model, train_loader, optimizer, criterion, device)
            val_result = eval_fold(model, val_loader, device)
            f1_50 = val_result["f1@50"]
            print(
                f"  Epoch {epoch + 1}: loss={train_loss:.4f}, "
                f"f1@10={val_result['f1@10']:.4f}, "
                f"f1@25={val_result['f1@25']:.4f}, "
                f"f1@50={f1_50:.4f}"
            )
            if f1_50 > best_f1:
                best_f1 = f1_50
                torch.save(
                    {
                        "fold": fold,
                        "epoch": epoch,
                        "model_state_dict": model.state_dict(),
                        "optimizer_state_dict": optimizer.state_dict(),
                        "best_f1": best_f1,
                        "config": {
                            "hidden_dim": HIDDEN_DIM,
                            "num_layers": NUM_LAYERS,
                            "refiner_channels": REFINER_CHANNELS,
                            "dropout": DROPOUT,
                            "use_refiner": True,
                            "duration_weight": DURATION_WEIGHT,
                        },
                    },
                    CHECKPOINT_DIR / f"fold_{fold}_best.pt",
                )

        fold_results.append(val_result)
        print(f"  Fold {fold + 1} best F1@50: {best_f1:.4f}")

    # Aggregate results
    print("\n=== 5-Fold CV Results ===")
    for threshold in [10, 25, 50]:
        key = f"f1@{threshold}"
        values = [r[key] for r in fold_results]
        print(f"F1@{threshold}: {np.mean(values):.4f} (+/- {np.std(values):.4f})")

    # Save summary
    summary = {
        "fold_results": fold_results,
        "mean_f1@10": float(np.mean([r["f1@10"] for r in fold_results])),
        "mean_f1@25": float(np.mean([r["f1@25"] for r in fold_results])),
        "mean_f1@50": float(np.mean([r["f1@50"] for r in fold_results])),
        "config": {
            "hidden_dim": HIDDEN_DIM,
            "num_layers": NUM_LAYERS,
            "refiner_channels": REFINER_CHANNELS,
            "dropout": DROPOUT,
            "lr": LR,
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "duration_weight": DURATION_WEIGHT,
            "use_refiner": True,
        },
    }
    with open(CHECKPOINT_DIR / "cv_results.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Results saved to {CHECKPOINT_DIR / 'cv_results.json'}")


if __name__ == "__main__":
    main()
