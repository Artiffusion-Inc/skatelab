"""Experiment: Fine Classifier — Skeleton1DCNN pre-train + fine-tune.

Hypothesis: Skeleton1DCNN achieves H-Element > 65% on jump 7-class
Status: PENDING

Usage:
    uv run python experiments/train_fine_classifier.py --phase pretrain
    uv run python experiments/train_fine_classifier.py --phase finetune
"""

import argparse
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from ml.src.tas.classifier import Skeleton1DCNN

CHECKPOINT_DIR = Path("experiments/checkpoints/fine_classifier")
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

# Jump family classes
JUMP_CLASSES = ["Axel", "Salchow", "Toeloop", "Loop", "Flip", "Lutz", "Euler"]
# Spin family classes
SPIN_CLASSES = ["Camel", "Sit", "Upright", "Layback", "Combo"]
# Step family classes
STEP_CLASSES = ["StepSequence", "ChoreoSequence", "Turns"]


class SegmentDataset(Dataset):
    """Loads pre-extracted segments with fine labels for Skeleton1DCNN training."""

    def __init__(self, data_dir: Path, family: str = "jump") -> None:
        self.segments = []
        self.labels = []
        self.label_names = []

        if family == "jump":
            classes = JUMP_CLASSES
        elif family == "spin":
            classes = SPIN_CLASSES
        else:
            classes = STEP_CLASSES

        label2idx = {name: idx for idx, name in enumerate(classes)}
        for cls_name in classes:
            cls_dir = data_dir / cls_name
            if not cls_dir.exists():
                continue
            for npy_file in cls_dir.glob("*.npy"):
                poses = np.load(npy_file)  # (T, 17, 2)
                flat = poses.reshape(poses.shape[0], -1)  # (T, 34)
                self.segments.append(flat.astype(np.float32))
                self.labels.append(label2idx[cls_name])

        self.label_names = classes

    def __len__(self) -> int:
        return len(self.segments)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int, int]:
        seg = self.segments[idx]
        label = self.labels[idx]
        return torch.from_numpy(seg), label, len(seg)


def collate_segments(batch):
    max_len = max(item[2] for item in batch)
    B = len(batch)
    padded = torch.zeros(B, max_len, 34)
    labels = torch.zeros(B, dtype=torch.long)
    lengths = torch.zeros(B, dtype=torch.long)
    for i, (seg, label, le) in enumerate(batch):
        padded[i, :le] = seg
        labels[i] = label
        lengths[i] = le
    return padded, labels, lengths


def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0
    for x, y, lengths in loader:
        x, y = x.to(device), y.to(device)
        optimizer.zero_grad()
        logits = model(x, lengths)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        preds = logits.argmax(dim=-1)
        correct += (preds == y).sum().item()
        total += y.shape[0]
    return total_loss / len(loader), correct / total if total > 0 else 0.0


@torch.no_grad()
def eval_epoch(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    for x, y, lengths in loader:
        x, y = x.to(device), y.to(device)
        logits = model(x, lengths)
        loss = criterion(logits, y)
        total_loss += loss.item()
        preds = logits.argmax(dim=-1)
        correct += (preds == y).sum().item()
        total += y.shape[0]
    return total_loss / len(loader), correct / total if total > 0 else 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["pretrain", "finetune"], default="pretrain")
    parser.add_argument("--family", choices=["jump", "spin", "step"], default="jump")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=1e-3)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if args.phase == "pretrain":
        data_dir = Path("data/datasets/fsc64/segments")
    else:
        data_dir = Path("data/datasets/mcfs/segments")

    ds = SegmentDataset(data_dir, family=args.family)
    print(f"Dataset: {len(ds)} segments, {len(ds.label_names)} classes")

    if len(ds) < 10:
        print("Not enough data. Skipping.")
        return

    # 80/20 split
    train_size = int(0.8 * len(ds))
    val_size = len(ds) - train_size
    train_ds, val_ds = torch.utils.data.random_split(ds, [train_size, val_size])

    train_loader = DataLoader(
        train_ds, batch_size=16, shuffle=True, collate_fn=collate_segments, num_workers=2
    )
    val_loader = DataLoader(val_ds, batch_size=16, shuffle=False, collate_fn=collate_segments)

    num_classes = len(ds.label_names)
    model = Skeleton1DCNN(num_classes=num_classes).to(device)

    if args.phase == "finetune":
        ckpt_path = CHECKPOINT_DIR / "pretrain_best.pt"
        if ckpt_path.exists():
            model.load_state_dict(torch.load(ckpt_path, map_location=device)["model_state_dict"])
            # Replace final layer for new num_classes
            model.fc[-1] = nn.Linear(256, num_classes)
            model.fc[-1] = model.fc[-1].to(device)
            print(f"Loaded pretrain checkpoint, replaced classifier for {num_classes} classes")

    # Weighted loss for class imbalance
    class_counts = np.bincount(ds.labels, minlength=num_classes).astype(float)
    sample_weights = class_counts.sum() / (num_classes * class_counts + 1e-6)
    criterion = nn.CrossEntropyLoss(
        weight=torch.tensor(sample_weights, dtype=torch.float32).to(device)
    )

    optimizer = torch.optim.Adam(
        model.parameters(), lr=args.lr if args.phase == "pretrain" else args.lr * 0.1
    )

    best_acc = 0.0
    for epoch in range(args.epochs):
        train_loss, train_acc = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc = eval_epoch(model, val_loader, criterion, device)
        print(
            f"Epoch {epoch + 1}: train_loss={train_loss:.4f}, train_acc={train_acc:.4f}, val_acc={val_acc:.4f}"
        )
        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "num_classes": num_classes,
                    "label_names": ds.label_names,
                    "best_acc": best_acc,
                    "family": args.family,
                },
                CHECKPOINT_DIR / f"{args.phase}_{args.family}_best.pt",
            )

    print(f"Best val accuracy: {best_acc:.4f}")


if __name__ == "__main__":
    main()
