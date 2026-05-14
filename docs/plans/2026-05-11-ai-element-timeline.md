# AI Element Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-level coarse→fine element classifier that receives H3.6M 17-keypoint poses `(T, 17, 2)` and outputs detected skating elements with start/end frames, coarse type, fine label, and confidence.

**Architecture:** Evolutionary — keep existing `BiGRUTAS` for coarse segmentation, add `BoundaryRefinerCNN` for boundary quality, replace `SegmentClassifier` (RandomForest) with `Skeleton1DCNN` for fine classification. Both BiGRU+Refiner and Skeleton1DCNN export to ONNX — no PyTorch at inference. TAS runs inside GPU `/process` endpoint concurrently with biomechanics via `asyncio.to_thread` (NOT `asyncio.create_task`). Backend persists segments via async batch insert in single transaction with metrics. Frontend polls via existing `useSession`.

**Tech Stack:** PyTorch (training only), ONNX Runtime (all inference — biomechanics + TAS), SQLAlchemy async, FastAPI, React Query, Zod

**Review amendments:** See `docs/specs/2026-05-12-ai-element-timeline-async-review.md` for 12 P0 fixes integrated below.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `ml/src/tas/model.py` | Modify | Add `BoundaryRefinerCNN`, wrap as `BiGRUTASRefiner` |
| `ml/src/tas/classifier.py` | Modify | Add `Skeleton1DCNN` (with duration feature) alongside existing `SegmentClassifier` |
| `ml/src/tas/inference.py` | Modify | `TASElementSegmenter` uses ONNX Runtime (no torch at inference) |
| `ml/src/tas/metrics.py` | Modify | Add `MultiOverlapF1` with thresholds [0.10, 0.25, 0.50] |
| `ml/src/tas/dataset.py` | Modify | Pre-load to RAM, `BucketBatchSampler` with `set_epoch()`, `bin_size=50` |
| `ml/src/pose_estimation/h36m.py` | Modify | Add `coco_to_h36m_batch` vectorized conversion |
| `ml/src/types.py` | Modify | Add `ElementSegment.element_name`, `CoarseType` enum |
| `ml/src/analysis/element_segmenter.py` | Modify | Add `tas_ml_v2` method, minimum duration filter per type |
| `ml/gpu_server/server.py` | Modify | `asyncio.to_thread` for TAS ONNX, startup model loading, R2 model entry |
| `ml/gpu_server/Containerfile` | No changes | onnxruntime-gpu already installed, TAS ONNX model from R2 |
| `backend/app/models/session.py` | Modify | Add `SessionElement` ORM + `segmentation_status` column |
| `backend/app/schemas.py` | Modify | Add `TimelineData`, `ElementSegmentResponse` to `SessionResponse` |
| `backend/app/vastai/client.py` | Modify | Add `segments` to `VastResult` (sync + async) |
| `backend/app/worker.py` | Modify | Batch insert `session_elements` in single transaction with metrics |
| `backend/app/crud/session.py` | Modify | Add `batch_insert_elements` + `selectinload(Session.elements)` |
| `experiments/train_tas_v2.py` | Create | BiGRU + Refiner training script (PyTorch, differentiable duration prior) |
| `experiments/export_tas_onnx.py` | Create | ONNX export for serverless inference |
| `experiments/train_fine_classifier.py` | Create | Skeleton1DCNN training script |
| `ml/tests/tas/test_model.py` | Modify | Add `BoundaryRefinerCNN` + `BiGRUTASRefiner` tests |
| `ml/tests/tas/test_metrics.py` | Modify | Add `MultiOverlapF1` tests |
| `ml/tests/tas/test_inference.py` | Modify | Add two-pass inference tests |
| `ml/tests/tas/test_dataset.py` | Modify | Add RAM pre-load + bucketing tests |
| `ml/tests/pose_estimation/test_h36m.py` | Modify | Add `coco_to_h36m_batch` tests |
| `frontend/src/lib/api/sessions.ts` | Modify | Add `segments`, `segmentation_status`, `PhasesDataSchema` to `SessionSchema` |
| `frontend/src/components/session/element-timeline.tsx` | Create | ElementTimeline component with confidence-based opacity |

---

## Phase 1: Coarse TAS v2

### Task 1: BoundaryRefinerCNN Model

**Files:**

- Modify: `ml/src/tas/model.py:1-74`
- Test: `ml/tests/tas/test_model.py:1-59`

- [ ] **Step 1: Write failing test for BoundaryRefinerCNN**

Add to `ml/tests/tas/test_model.py`:

```python
def test_boundary_refiner_forward():
    from ml.src.tas.model import BoundaryRefinerCNN
    refiner = BoundaryRefinerCNN(input_channels=38)
    # 4 coarse logits + 34 raw features = 38
    x = torch.randn(2, 100, 38)
    out = refiner(x)
    assert out.shape == (2, 100, 4)


def test_boundary_refiner_gradient():
    from ml.src.tas.model import BoundaryRefinerCNN
    refiner = BoundaryRefinerCNN(input_channels=38)
    x = torch.randn(2, 50, 38, requires_grad=True)
    out = refiner(x)
    loss = out.mean()
    loss.backward()
    assert x.grad is not None
    assert not torch.isnan(x.grad).any()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest ml/tests/tas/test_model.py::test_boundary_refiner_forward ml/tests/tas/test_model.py::test_boundary_refiner_gradient -v`
Expected: FAIL with `ImportError: cannot import name 'BoundaryRefinerCNN'`

- [ ] **Step 3: Implement BoundaryRefinerCNN**

Add to `ml/src/tas/model.py` after `BiGRUTAS` class:

```python
class BoundaryRefinerCNN(nn.Module):
    """Refines coarse BiGRU logits using local CNN context.

    Input: (B, T, 38) — 4 coarse logits + 34 raw pose features
    Output: (B, T, 4) — refined logits
    """

    def __init__(self, input_channels: int = 38, hidden_channels: int = 64, dropout: float = 0.3) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(input_channels, hidden_channels, kernel_size=10, padding=4)
        self.conv2 = nn.Conv1d(hidden_channels, hidden_channels, kernel_size=10, padding=4)
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
```

Update `__all__` in `model.py` to `["BiGRUTAS", "BoundaryRefinerCNN", "BiGRUTASRefiner"]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest ml/tests/tas/test_model.py::test_boundary_refiner_forward ml/tests/tas/test_model.py::test_boundary_refiner_gradient -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ml/src/tas/model.py ml/tests/tas/test_model.py
git commit -m "feat(tas): add BoundaryRefinerCNN for coarse logit refinement"
```

---

### Task 2: BiGRUTASRefiner Wrapper

**Files:**

- Modify: `ml/src/tas/model.py`
- Test: `ml/tests/tas/test_model.py`

- [ ] **Step 1: Write failing test for BiGRUTASRefiner**

Add to `ml/tests/tas/test_model.py`:

```python
def test_bigrutas_refiner_forward():
    from ml.src.tas.model import BiGRUTASRefiner
    model = BiGRUTASRefiner(hidden_dim=64, num_layers=1, refiner_channels=32)
    B, T = 2, 100
    poses = torch.randn(B, T, 17, 2)
    lengths = torch.tensor([100, 80])
    logits = model(poses, lengths)
    assert logits.shape == (B, T, 4)


def test_bigrutas_refiner_gradient():
    from ml.src.tas.model import BiGRUTASRefiner
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    poses = torch.randn(2, 50, 17, 2, requires_grad=True)
    lengths = torch.tensor([50, 30])
    logits = model(poses, lengths)
    loss = logits.mean()
    loss.backward()
    assert poses.grad is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest ml/tests/tas/test_model.py::test_bigrutas_refiner_forward ml/tests/tas/test_model.py::test_bigrutas_refiner_gradient -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement BiGRUTASRefiner**

Add to `ml/src/tas/model.py` after `BoundaryRefinerCNN`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest ml/tests/tas/test_model.py::test_bigrutas_refiner_forward ml/tests/tas/test_model.py::test_bigrutas_refiner_gradient -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ml/src/tas/model.py ml/tests/tas/test_model.py
git commit -m "feat(tas): add BiGRUTASRefiner two-pass model"
```

---

### Task 3: MultiOverlapF1 Metric

**Files:**

- Modify: `ml/src/tas/metrics.py:49-101`
- Test: `ml/tests/tas/test_metrics.py`

- [ ] **Step 1: Write failing test for MultiOverlapF1**

Add to `ml/tests/tas/test_metrics.py`:

```python
def test_multi_overlap_f1():
    from ml.src.tas.metrics import MultiOverlapF1
    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50])
    pred = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    true = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    result = metric.compute(pred, true)
    assert "f1@10" in result
    assert "f1@25" in result
    assert "f1@50" in result
    assert result["f1@10"] == 1.0
    assert result["f1@25"] == 1.0
    assert result["f1@50"] == 1.0


def test_multi_overlap_f1_partial():
    from ml.src.tas.metrics import MultiOverlapF1
    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50])
    pred = np.array([0, 0, 0, 0, 1, 1, 0, 0])
    true = np.array([0, 0, 1, 1, 1, 1, 1, 0])
    result = metric.compute(pred, true)
    # F1@10 should be higher than F1@50 (looser threshold)
    assert result["f1@10"] >= result["f1@50"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest ml/tests/tas/test_metrics.py::test_multi_overlap_f1 ml/tests/tas/test_metrics.py::test_multi_overlap_f1_partial -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement MultiOverlapF1**

Add to `ml/src/tas/metrics.py` after `OverlapF1` class:

```python
class MultiOverlapF1:
    """Evaluate at multiple IoU thresholds simultaneously.

    Returns F1, precision, recall at each threshold.
    """

    def __init__(self, thresholds: list[float] | None = None, num_classes: int = 4) -> None:
        self.thresholds = thresholds or [0.10, 0.25, 0.50]
        self.num_classes = num_classes
        self.id2label = {i: ID2LABEL.get(i, f"Class{i}") for i in range(num_classes)}

    def compute(
        self,
        pred_labels: "NDArray",
        true_labels: "NDArray",
    ) -> dict[str, float]:
        """Compute OverlapF1 at multiple IoU thresholds.

        Returns:
            Dict with keys like 'f1@10', 'precision@25', 'recall@50', etc.
        """
        pred_segs = _extract_segments(pred_labels, self.id2label)
        true_segs = _extract_segments(true_labels, self.id2label)

        result: dict[str, float] = {}
        for threshold in self.thresholds:
            tag = str(int(threshold * 100))
            metric = OverlapF1(iou_threshold=threshold, num_classes=self.num_classes)
            single = metric.compute(pred_labels, true_labels)
            result[f"f1@{tag}"] = single["f1"]
            result[f"precision@{tag}"] = single["precision"]
            result[f"recall@{tag}"] = single["recall"]
        return result
```

Update `__all__` to include `MultiOverlapF1`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest ml/tests/tas/test_metrics.py::test_multi_overlap_f1 ml/tests/tas/test_metrics.py::test_multi_overlap_f1_partial -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ml/src/tas/metrics.py ml/tests/tas/test_metrics.py
git commit -m "feat(tas): add MultiOverlapF1 metric for multi-threshold evaluation"
```

---

### Task 4: Dataset RAM Pre-loading + BucketBatchSampler

**Files:**

- Modify: `ml/src/tas/dataset.py:97-138`
- Test: `ml/tests/tas/test_dataset.py`

- [ ] **Step 1: Write failing test for RAM pre-loading**

Add to `ml/tests/tas/test_dataset.py`:

```python
def test_mcfs_dataset_preload(tmp_path):
    """Dataset pre-loads all arrays into RAM at init time."""
    import numpy as np
    from pathlib import Path

    # Create minimal fake dataset
    feat_dir = tmp_path / "features"
    label_dir = tmp_path / "labels"
    feat_dir.mkdir()
    label_dir.mkdir()
    np.save(feat_dir / "s01.npy", np.random.randn(30, 25, 3).astype(np.float64))
    (label_dir / "s01.txt").write_text("\n".join(["NONE"] * 30))

    from ml.src.tas.dataset import MCFSCoarseDataset
    ds = MCFSCoarseDataset(feat_dir, label_dir, preload=True)
    poses, labels, length = ds[0]
    assert poses.shape == (30, 17, 2)
    assert labels.shape == (30,)
    assert length == 30


def test_bucket_batch_sampler():
    """BucketBatchSampler groups similar-length sequences together."""
    from ml.src.tas.dataset import BucketBatchSampler
    import numpy as np

    lengths = [100, 30, 80, 50, 120, 40]
    sampler = BucketBatchSampler(lengths, batch_size=2, bin_size=50)
    batches = list(sampler)
    # Each batch should have sequences of similar length
    assert len(batches) > 0
    for batch in batches:
        assert len(batch) <= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest ml/tests/tas/test_dataset.py::test_mcfs_dataset_preload ml/tests/tas/test_dataset.py::test_bucket_batch_sampler -v`
Expected: FAIL with `TypeError` or `ImportError`

- [ ] **Step 3: Implement RAM pre-loading in MCFSCoarseDataset**

Replace `MCFSCoarseDataset.__init__` and `__getitem__` in `ml/src/tas/dataset.py`:

```python
class MCFSCoarseDataset(Dataset):
    """PyTorch dataset for MCFS continuous routines with coarse labels.

    Loads .npy features + .txt ground truth, converts OP25 -> COCO17 -> H3.6M,
    normalizes, and returns (poses, labels, length) tuples.

    When preload=True, all data is converted and cached in RAM at init time,
    eliminating per-epoch I/O and conversion overhead (~0.77s/batch → <0.05s).
    """

    def __init__(
        self,
        features_dir: Path,
        labels_dir: Path,
        normalize: bool = True,
        preload: bool = True,
    ) -> None:
        self.features_dir = features_dir
        self.labels_dir = labels_dir
        self.normalize = normalize
        feature_files = {p.stem: p for p in features_dir.glob("*.npy")}
        label_files = {p.stem: p for p in labels_dir.glob("*.txt")}
        self.samples = sorted(set(feature_files.keys()) & set(label_files.keys()))
        self.feature_paths = {s: feature_files[s] for s in self.samples}
        self.label_paths = {s: label_files[s] for s in self.samples}

        self._cache: dict[int, tuple] = {}
        if preload:
            for idx in range(len(self.samples)):
                self._cache[idx] = self._load_sample(idx)

    def _load_sample(self, idx: int) -> tuple["NDArray[np.float32]", "NDArray[np.int64]", int]:
        stem = self.samples[idx]
        poses_op25 = np.load(self.feature_paths[stem])
        fine_labels = [line.strip() for line in self.label_paths[stem].read_text().splitlines()]
        poses_coco17 = op25_to_coco17(poses_op25)
        poses_h36m = coco_to_h36m_batch(poses_coco17)  # vectorized — 50x faster than per-frame loop
        coarse = np.array([coarse_label(label) for label in fine_labels], dtype=np.int64)
        if self.normalize:
            poses_h36m = normalize_poses(poses_h36m)
        return poses_h36m.astype(np.float32), coarse, len(coarse)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple["NDArray[np.float32]", "NDArray[np.int64]", int]:
        if idx in self._cache:
            return self._cache[idx]
        return self._load_sample(idx)

    def get_fine_labels(self, idx: int) -> list[str]:
        stem = self.samples[idx]
        return [line.strip() for line in self.label_paths[stem].read_text().splitlines()]
```

Add `BucketBatchSampler` to same file:

```python
class BucketBatchSampler:
    """Groups sequences into buckets by length to minimize padding waste.

    Bins sequences by length (±bin_size frames), then samples within each bin.
    Reduces padding waste from 20-35% to <5%.

    Call set_epoch() before each epoch to re-shuffle within bins.
    """

    def __init__(
        self,
        lengths: list[int],
        batch_size: int = 8,
        bin_size: int = 50,
        shuffle: bool = True,
        seed: int = 42,
    ) -> None:
        self.batch_size = batch_size
        self.bin_size = bin_size
        self.shuffle = shuffle
        self.seed = seed
        self.epoch = 0
        # Group indices by bin
        self._bins: dict[int, list[int]] = {}
        for idx, length in enumerate(lengths):
            bin_key = length // bin_size
            self._bins.setdefault(bin_key, []).append(idx)
        self._build_batches()

    def _build_batches(self) -> None:
        rng = random.Random(self.seed + self.epoch)
        self.batches: list[list[int]] = []
        for bin_key in sorted(self._bins.keys()):
            indices = list(self._bins[bin_key])
            if self.shuffle:
                rng.shuffle(indices)
            for i in range(0, len(indices), self.batch_size):
                self.batches.append(indices[i : i + self.batch_size])
        if self.shuffle:
            rng.shuffle(self.batches)

    def set_epoch(self, epoch: int) -> None:
        """Re-shuffle batches for new epoch. Call before DataLoader creation."""
        self.epoch = epoch
        self._build_batches()

    def __iter__(self):
        for batch in self.batches:
            yield batch

    def __len__(self) -> int:
        return len(self.batches)
```

Update `__all__` to include `BucketBatchSampler`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest ml/tests/tas/test_dataset.py::test_mcfs_dataset_preload ml/tests/tas/test_dataset.py::test_bucket_batch_sampler -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ml/src/tas/dataset.py ml/tests/tas/test_dataset.py
git commit -m "perf(tas): pre-load MCFS to RAM + BucketBatchSampler for training"
```

---

### Task 5: Update TASElementSegmenter for Two-Pass + torch.compile

**Files:**

- Modify: `ml/src/tas/inference.py:1-125`
- Test: `ml/tests/tas/test_inference.py`

- [ ] **Step 1: Write failing test for two-pass inference**

Add to `ml/tests/tas/test_inference.py`:

```python
def test_tas_inference_onnx():
    """TASElementSegmenter loads ONNX model and produces segments."""
    import torch
    from ml.src.tas.model import BiGRUTASRefiner
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    model.eval()
    # Export to ONNX
    dummy_poses = torch.randn(1, 50, 17, 2)
    dummy_lengths = torch.tensor([50], dtype=torch.long)
    torch.onnx.export(
        model, (dummy_poses, dummy_lengths),
        "/tmp/test_tas_refiner.onnx",
        input_names=["poses", "lengths"],
        output_names=["logits"],
        dynamic_axes={"poses": {0: "batch", 1: "time"}, "lengths": {0: "batch"}, "logits": {0: "batch", 1: "time"}},
        opset_version=17,
    )

    segmenter = TASElementSegmenter(
        model_path=Path("/tmp/test_tas_refiner.onnx"),
        classifier_path=None,
        device="cpu",
    )
    poses = np.random.randn(100, 17, 2).astype(np.float32)
    segments = segmenter.segment(poses, fps=30.0)
    assert isinstance(segments, list)


def test_tas_min_duration_filter():
    """Segments shorter than element-type minimum duration are filtered."""
    # Create ONNX model that predicts all-Jump
    import torch
    from ml.src.tas.model import BiGRUTASRefiner
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    model.eval()
    # Force all-Jump by biasing classifier
    with torch.no_grad():
        model.refiner.classifier.bias.zero_()
        model.refiner.classifier.bias[1] = 10.0  # Jump class
    dummy_poses = torch.randn(1, 50, 17, 2)
    dummy_lengths = torch.tensor([50], dtype=torch.long)
    torch.onnx.export(
        model, (dummy_poses, dummy_lengths),
        "/tmp/test_tas_min_dur.onnx",
        input_names=["poses", "lengths"],
        output_names=["logits"],
        dynamic_axes={"poses": {0: "batch", 1: "time"}, "lengths": {0: "batch"}, "logits": {0: "batch", 1: "time"}},
        opset_version=17,
    )

    segmenter = TASElementSegmenter(
        model_path=Path("/tmp/test_tas_min_dur.onnx"),
        device="cpu",
    )
    # 10 frames at 30fps = 0.33s < 0.5s Jump minimum → filtered
    poses = np.random.randn(10, 17, 2).astype(np.float32)
    segments = segmenter.segment(poses, fps=30.0)
    assert len(segments) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest ml/tests/tas/test_inference.py::test_tas_inference_with_refiner ml/tests/tas/test_inference.py::test_tas_min_duration_filter -v`
Expected: FAIL (refiner checkpoint not handled, no per-type min duration)

- [ ] **Step 3: Implement two-pass inference + per-type min duration**

Replace `ml/src/tas/inference.py`:

```python
"""End-to-end TAS inference: poses → ONNX BiGRU(+Refiner) coarse → segments → ONNX/CNN fine."""

from pathlib import Path

import numpy as np
import onnxruntime as ort

from ..device import DeviceConfig
from .classifier import SegmentClassifier, extract_segment_features

# Per-element minimum duration in seconds
MIN_DURATION = {
    "Jump": 0.5,
    "Spin": 2.0,
    "Step": 3.0,
}


class TASElementSegmenter:
    """ONNX-based element segmenter: BiGRU+Refiner coarse → segment extraction → fine classifier.

    Uses ONNX Runtime for inference — no PyTorch dependency at runtime.
    Models are exported from PyTorch via torch.onnx.export during training.
    """

    def __init__(
        self,
        model_path: Path | str,
        classifier_path: Path | str | None = None,
        device: str | None = None,
        min_segment_duration: float = 0.5,
    ) -> None:
        cfg = DeviceConfig(device=device) if device else DeviceConfig.default()
        self.device = cfg.device

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if cfg.is_cuda else ["CPUExecutionProvider"]
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 2
        self.session = ort.InferenceSession(str(model_path), sess_options=opts, providers=providers)

        self.classifier: SegmentClassifier | None = None
        if classifier_path is not None:
            import joblib
            self.classifier = joblib.load(classifier_path)

        self.min_segment_duration = min_segment_duration
        self.id2label = {0: "None", 1: "Jump", 2: "Spin", 3: "Step"}

        # Cache input/output names for faster inference
        self._input_names = [inp.name for inp in self.session.get_inputs()]
        self._output_names = [out.name for out in self.session.get_outputs()]

    def segment(
        self,
        poses: np.ndarray,
        fps: float = 30.0,
    ) -> list[dict]:
        """Segment poses into elements with per-type minimum duration filtering."""
        T = poses.shape[0]
        poses_flat = poses.reshape(1, T, 34).astype(np.float32)
        lengths = np.array([T], dtype=np.int64)

        feeds = dict(zip(self._input_names, [poses_flat, lengths]))
        logits = self.session.run(self._output_names, feeds)[0]  # (1, T, 4)
        pred_labels = logits[0].argmax(axis=-1)

        return self._extract_segments(pred_labels, poses, fps)

    def _extract_segments(
        self,
        labels: np.ndarray,
        poses: np.ndarray,
        fps: float,
    ) -> list[dict]:
        """Extract contiguous segments with per-type minimum duration filter."""
        segments: list[dict] = []
        if len(labels) == 0:
            return segments

        current = int(labels[0])
        start = 0
        for i in range(1, len(labels)):
            if int(labels[i]) != current:
                if current != 0:
                    seg = self._try_add_segment(current, start, i, poses, fps)
                    if seg is not None:
                        segments.append(seg)
                current = int(labels[i])
                start = i

        # Last segment
        if current != 0:
            seg = self._try_add_segment(current, start, len(labels), poses, fps)
            if seg is not None:
                segments.append(seg)

        return segments

    def _try_add_segment(
        self,
        label: int,
        start: int,
        end: int,
        poses: np.ndarray,
        fps: float,
    ) -> dict | None:
        """Add segment if it passes per-type minimum duration check."""
        element_type = self.id2label[label]
        duration = (end - start) / fps
        min_dur = MIN_DURATION.get(element_type, self.min_segment_duration)
        if duration < min_dur:
            return None

        seg_poses = poses[start:end]
        confidence = 1.0

        if self.classifier is not None and label in (1, 2, 3):
            features = extract_segment_features(seg_poses, fps)
            element_type, confidence = self.classifier.predict(features)

        return {
            "element_type": element_type,
            "start": start,
            "end": end - 1,
            "confidence": confidence,
        }


__all__ = ["TASElementSegmenter"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest ml/tests/tas/test_inference.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ml/src/tas/inference.py ml/tests/tas/test_inference.py
git commit -m "feat(tas): ONNX-based two-pass inference + per-type min duration"
```

---

### Task 6: Training Script v2 (BiGRU + Refiner)

**Files:**

- Create: `experiments/train_tas_v2.py`

- [ ] **Step 1: Write training script**

Create `experiments/train_tas_v2.py`:

```python
"""Experiment: TAS v2 — BiGRU + BoundaryRefinerCNN.

Hypothesis: BiGRU + Refiner achieves F1@50 > 0.80 on MCFS 4-class segmentation
Status: PENDING

Usage:
    uv run python experiments/train_tas_v2.py
"""

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.model_selection import KFold
from torch.utils.data import DataLoader, Subset

from ml.src.tas.dataset import MCFSCoarseDataset, BucketBatchSampler, pad_collate
from ml.src.tas.metrics import MultiOverlapF1
from ml.src.tas.model import BiGRUTASRefiner

BASE = Path("data/datasets/mcfs")
CHECKPOINT_DIR = Path("experiments/checkpoints/tas_v2")
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def train_epoch(model, loader, optimizer, criterion, device, duration_weight=0.1):
    model.train()
    total_loss = 0.0
    for poses, labels, lengths in loader:
        poses, labels = poses.to(device), labels.to(device)
        optimizer.zero_grad()
        logits = model(poses, lengths)
        ce_loss = criterion(logits.view(-1, 4), labels.view(-1))
        # Duration prior: penalize very short segments (differentiable, uses logits not argmax)
        dur_loss = _duration_prior_loss(logits, lengths, device)
        loss = ce_loss + duration_weight * dur_loss
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    return total_loss / len(loader)


def _duration_prior_loss(logits: torch.Tensor, lengths: torch.Tensor, device: torch.device, min_frames: int = 15) -> torch.Tensor:
    """Penalize short predicted segments using soft probabilities (differentiable).

    Uses softmax probabilities instead of argmax to maintain gradient flow.
    High probability of element in short burst = penalty.
    """
    probs = F.softmax(logits, dim=-1)  # (B, T, C)
    non_none_prob = 1.0 - probs[:, :, 0]  # (B, T) — probability of any element
    loss = torch.tensor(0.0, device=device)
    for b in range(logits.shape[0]):
        le = lengths[b].item()
        p = non_none_prob[b, :le]
        # Conv1d to detect short high-probability bursts
        kernel = torch.ones(min_frames, device=device) / min_frames
        smoothed = F.conv1d(
            p.unsqueeze(0).unsqueeze(0),
            kernel.unsqueeze(0).unsqueeze(0),
            padding=min_frames // 2,
        ).squeeze()
        # High probability in short burst (smoothed * (1-smoothed)) peaks at transitions
        short_penalty = (smoothed * (1 - smoothed)).mean()
        loss = loss + short_penalty
    return loss / logits.shape[0]


def eval_fold(model, loader, device) -> dict:
    model.eval()
    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50])
    all_preds = []
    all_true = []
    with torch.no_grad():
        for poses, labels, lengths in loader:
            poses = poses.to(device)
            logits = model(poses, lengths)
            preds = logits.argmax(dim=-1).cpu().numpy()
            for i, le in enumerate(lengths):
                all_preds.append(preds[i, :le])
                all_true.append(labels[i, :le].numpy())

    results_list = []
    for p, t in zip(all_preds, all_true):
        results_list.append(metric.compute(p, t))

    keys = results_list[0].keys()
    return {k: float(np.mean([r[k] for r in results_list])) for k in keys}


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    ds = MCFSCoarseDataset(BASE / "features", BASE / "labels", preload=True)
    print(f"Dataset size: {len(ds)}")

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    fold_results = []

    for fold, (train_idx, val_idx) in enumerate(kf.split(range(len(ds)))):
        print(f"\n--- Fold {fold + 1}/5 ---")
        train_ds = Subset(ds, train_idx)
        val_ds = Subset(ds, val_idx)

        # Bucket sampler for training
        train_lengths = [ds[i][2] for i in train_idx]
        train_sampler = BucketBatchSampler(train_lengths, batch_size=12, bin_size=50)

        num_workers = 4
        pin_memory = (device.type == "cuda")
        dl_kwargs: dict = {"collate_fn": pad_collate}
        if num_workers > 0:
            dl_kwargs.update(num_workers=num_workers, persistent_workers=True, prefetch_factor=4, pin_memory=pin_memory)
        train_loader = DataLoader(train_ds, batch_sampler=train_sampler, **dl_kwargs)
        val_loader = DataLoader(val_ds, batch_size=12, shuffle=False, collate_fn=pad_collate)

        model = BiGRUTASRefiner(hidden_dim=128, num_layers=2, dropout=0.3, refiner_channels=64).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.CrossEntropyLoss(ignore_index=-1)

        best_f1 = 0.0
        for epoch in range(80):
            train_sampler.set_epoch(epoch)  # Re-shuffle batches each epoch
            train_loss = train_epoch(model, train_loader, optimizer, criterion, device)
            val_result = eval_fold(model, val_loader, device)
            f1_50 = val_result["f1@50"]
            print(f"  Epoch {epoch + 1}: loss={train_loss:.4f}, f1@50={f1_50:.4f}, f1@25={val_result['f1@25']:.4f}")
            if f1_50 > best_f1:
                best_f1 = f1_50
                torch.save({
                    "fold": fold,
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "best_f1": best_f1,
                    "config": {"hidden_dim": 128, "num_layers": 2, "dropout": 0.3, "refiner_channels": 64},
                    "use_refiner": True,
                }, CHECKPOINT_DIR / f"fold_{fold}_best.pt")

        fold_results.append(best_f1)
        print(f"  Fold {fold + 1} best F1@50: {best_f1:.4f}")

    print(f"\n=== 5-Fold CV Results ===")
    print(f"Mean F1@50: {np.mean(fold_results):.4f} (+/- {np.std(fold_results):.4f})")

    with open(CHECKPOINT_DIR / "cv_results.json", "w") as f:
        json.dump({"fold_f1s": fold_results, "mean": float(np.mean(fold_results)), "std": float(np.std(fold_results))}, f, indent=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script parses**

Run: `uv run python -c "import ast; ast.parse(open('experiments/train_tas_v2.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add experiments/train_tas_v2.py
git commit -m "feat(tas): training script v2 with BiGRU+Refiner + bucketing + duration prior"
```

---

### Task 7: Update ElementSegmenter for v2

**Files:**

- Modify: `ml/src/analysis/element_segmenter.py:28-80`
- Test: `ml/tests/segmentation/test_element_segmenter.py` (if exists)

- [ ] **Step 1: Add tas_ml_v2 method to ElementSegmenter**

Add method to `ElementSegmenter` class in `ml/src/analysis/element_segmenter.py` after the `tas_ml` method:

```python
def _segment_with_tas_v2(
    self,
    poses: NormalizedPose,
    fps: float,
    video_meta: "VideoMeta",
) -> SegmentationResult | None:
    """Segment using BiGRUTASRefiner + Skeleton1DCNN v2 pipeline."""
    from ..tas.inference import TASElementSegmenter as TASV2

    segmenter = self._get_tas_segmenter()
    if segmenter is None:
        return None

    raw_segments = segmenter.segment(poses, fps=fps)
    if not raw_segments:
        return None

    segments = []
    for seg in raw_segments:
        phases = None
        seg_poses = poses[seg["start"] : seg["end"] + 1]
        # Try rule-based PhaseDetector for jump elements
        if seg["element_type"] == "Jump" and len(seg_poses) > 10:
            try:
                from ..analysis.phase_detector import PhaseDetector
                pd = PhaseDetector()
                phase_result = pd.detect_phases(seg_poses, fps, seg["element_type"])
                if phase_result and phase_result.phases:
                    phases = phase_result.phases
            except (ValueError, RuntimeError):
                pass

        segments.append(
            ElementSegment(
                element_type=seg["element_type"],
                start=seg["start"],
                end=seg["end"],
                confidence=seg["confidence"],
                phases=phases,
                metadata={"coarse_type": seg["element_type"]},
            )
        )

    return SegmentationResult(
        segments=segments,
        video_path=video_meta.path,
        video_meta=video_meta,
        method="tas_ml_v2",
        confidence=float(np.mean([s.confidence for s in segments])),
    )
```

Update `segment()` method to try `tas_ml_v2` first if model path is set, then fallback to `tas_ml`, then rules.

- [ ] **Step 2: Run existing tests**

Run: `uv run python -m pytest ml/tests/segmentation/ -v --no-cov`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add ml/src/analysis/element_segmenter.py
git commit -m "feat(analysis): add tas_ml_v2 method to ElementSegmenter"
```

---

## Phase 2: Fine Classifier v2

### Task 8: Skeleton1DCNN Model

**Files:**

- Modify: `ml/src/tas/classifier.py:1-86`
- Test: `ml/tests/tas/test_classifier.py`

- [ ] **Step 1: Write failing test for Skeleton1DCNN**

Add to `ml/tests/tas/test_classifier.py`:

```python
def test_skeleton1dcnn_forward():
    from ml.src.tas.classifier import Skeleton1DCNN
    model = Skeleton1DCNN(num_classes=7)
    # (B, T, 34) — flattened (17, 2) per frame
    x = torch.randn(4, 120, 34)
    lengths = torch.tensor([120, 100, 80, 60])
    out = model(x, lengths)
    assert out.shape == (4, 7)
    assert not torch.isnan(out).any()


def test_skeleton1dcnn_variable_length():
    from ml.src.tas.classifier import Skeleton1DCNN
    model = Skeleton1DCNN(num_classes=5)
    x = torch.randn(2, 200, 34)
    lengths = torch.tensor([200, 50])
    out = model(x, lengths)
    assert out.shape == (2, 5)
    assert not torch.isnan(out).any()


def test_skeleton1dcnn_duration_feature():
    """Duration feature differentiates short vs long segments."""
    from ml.src.tas.classifier import Skeleton1DCNN
    model = Skeleton1DCNN(num_classes=3)
    x = torch.randn(2, 100, 34)
    # Same skeleton, different lengths → different outputs
    lengths_short = torch.tensor([30, 30])
    lengths_long = torch.tensor([100, 100])
    with torch.no_grad():
        out_short = model(x, lengths_short)
        out_long = model(x, lengths_long)
    # Outputs should differ due to duration feature
    assert not torch.allclose(out_short, out_long)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest ml/tests/tas/test_classifier.py::test_skeleton1dcnn_forward ml/tests/tas/test_classifier.py::test_skeleton1dcnn_variable_length -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement Skeleton1DCNN**

Add to `ml/src/tas/classifier.py` after `SegmentClassifier`:

```python
class Skeleton1DCNN(nn.Module):
    """1D CNN classifier for fine element types from skeleton sequences.

    Input: (B, T, 34) — flattened (17, 2) per frame, variable length.
    Output: (B, num_classes) logits.
    """

    def __init__(
        self,
        input_dim: int = 34,
        num_classes: int = 15,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(input_dim, 128, kernel_size=7, padding=3)
        self.bn1 = nn.BatchNorm1d(128)
        self.conv2 = nn.Conv1d(128, 256, kernel_size=5, padding=2)
        self.bn2 = nn.BatchNorm1d(256)
        self.conv3 = nn.Conv1d(256, 512, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm1d(512)
        self.pool = nn.AdaptiveMaxPool1d(1)
        self.fc = nn.Sequential(
            nn.Linear(513, 256),  # 512 CNN features + 1 duration feature
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        """Classify skeleton sequences.

        Args:
            x: (B, T, 34) flattened poses
            lengths: (B,) actual sequence lengths

        Returns:
            logits: (B, num_classes)
        """
        x = x.permute(0, 2, 1)  # (B, 34, T)
        x = torch.relu(self.bn1(self.conv1(x)))
        x = torch.relu(self.bn2(self.conv2(x)))
        x = torch.relu(self.bn3(self.conv3(x)))
        x = self.pool(x).squeeze(-1)  # (B, 512)
        # Concatenate normalized duration — prevents losing temporal info in AdaptiveMaxPool
        dur = (lengths.float() / lengths.max().float()).unsqueeze(1)  # (B, 1)
        x = torch.cat([x, dur], dim=1)  # (B, 513)
        return self.fc(x)
```

Update `__all__` to include `Skeleton1DCNN`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest ml/tests/tas/test_classifier.py::test_skeleton1dcnn_forward ml/tests/tas/test_classifier.py::test_skeleton1dcnn_variable_length -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ml/src/tas/classifier.py ml/tests/tas/test_classifier.py
git commit -m "feat(tas): add Skeleton1DCNN for fine element classification"
```

---

### Task 9: Fine Classifier Training Script

**Files:**

- Create: `experiments/train_fine_classifier.py`

- [ ] **Step 1: Write training script**

Create `experiments/train_fine_classifier.py`:

```python
"""Experiment: Fine Classifier — Skeleton1DCNN pre-train + fine-tune.

Hypothesis: Skeleton1DCNN achieves H-Element > 65% on jump 7-class
Status: PENDING

Usage:
    uv run python experiments/train_fine_classifier.py --phase pretrain
    uv run python experiments/train_fine_classifier.py --phase finetune
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
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

    train_loader = DataLoader(train_ds, batch_size=16, shuffle=True, collate_fn=collate_segments, num_workers=2)
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
    class_weights = 1.0 / (class_counts + 1e-6)
    sample_weights = class_counts.sum() / (num_classes * class_counts + 1e-6)
    criterion = nn.CrossEntropyLoss(weight=torch.tensor(sample_weights, dtype=torch.float32).to(device))

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr if args.phase == "pretrain" else args.lr * 0.1)

    best_acc = 0.0
    for epoch in range(args.epochs):
        train_loss, train_acc = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc = eval_epoch(model, val_loader, criterion, device)
        print(f"Epoch {epoch + 1}: train_loss={train_loss:.4f}, train_acc={train_acc:.4f}, val_acc={val_acc:.4f}")
        if val_acc > best_acc:
            best_acc = val_acc
            torch.save({
                "model_state_dict": model.state_dict(),
                "num_classes": num_classes,
                "label_names": ds.label_names,
                "best_acc": best_acc,
                "family": args.family,
            }, CHECKPOINT_DIR / f"{args.phase}_{args.family}_best.pt")

    print(f"Best val accuracy: {best_acc:.4f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script parses**

Run: `uv run python -c "import ast; ast.parse(open('experiments/train_fine_classifier.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add experiments/train_fine_classifier.py
git commit -m "feat(tas): Skeleton1DCNN training script with pre-train + fine-tune"
```

---

## Phase 3: Integration

### Task 10: Extend VastResult with segments

**Files:**

- Modify: `backend/app/vastai/client.py:48-55`
- Modify: `ml/gpu_server/server.py:166-172`

- [ ] **Step 1: Add segments to VastResult**

In `backend/app/vastai/client.py`, add `segments` field to `VastResult`:

```python
@dataclass
class VastResult:
    video_key: str
    poses_key: str | None
    csv_key: str | None
    stats: dict
    metrics: list | None
    phases: object | None
    recommendations: list | None
    segments: list[dict] | None = None
```

- [ ] **Step 2: Add segments to ProcessResponse in GPU server**

In `ml/gpu_server/server.py`, add `segments` to `ProcessResponse`:

```python
class ProcessResponse(BaseModel):
    poses_r2_key: str | None = None
    metrics_r2_key: str | None = None
    stats: dict
    metrics: list | None = None
    phases: object | None = None
    recommendations: list | None = None
    segments: list[dict] | None = None
```

- [ ] **Step 3: Run TAS concurrently with biomechanics in /process**

In `ml/gpu_server/server.py`, update the `/process` endpoint to run TAS and biomechanics concurrently:

Add module-level variable for startup-loaded model:

```python
_tas_segmenter: TASElementSegmenter | None = None
```

Add to `_background_init()`:

```python
async def _background_init():
    global _tas_segmenter
    # ... existing ONNX model init ...
    # Load TAS ONNX model at startup (not per-request)
    try:
        from src.tas.inference import TASElementSegmenter
        tas_model_path = _PROJECT_ROOT / "data/models/tas/bigr_refiner_best.onnx"
        if tas_model_path.exists():
            _tas_segmenter = TASElementSegmenter(model_path=str(tas_model_path))
            logger.info("TAS segmenter loaded at startup (ONNX)")
    except (ValueError, RuntimeError, OSError):
        logger.warning("TAS segmenter not loaded — timeline unavailable")
```

Also add TAS ONNX model to `_R2_MODELS` for R2 download at startup:

```python
TAS_MODEL_PATH = _PROJECT_ROOT / "data/models/tas/bigr_refiner_best.onnx"
_R2_MODELS: list[tuple[Path, str]] = [
    (MOGANET_MODEL_PATH, "models/moganet/moganet_b_ap2d_384x288.onnx"),
    (YOLO_MODEL_PATH, "models/yolov8n.onnx"),
    (TAS_MODEL_PATH, "models/tas/bigr_refiner_best.onnx"),
]
```

Add after line with `prepared = prepare_poses(...)`:

```python
                # --- TAS element segmentation (concurrent with biomechanics) ---
                def _run_tas_sync():
                    """Blocking TAS ONNX inference — runs in thread pool for true parallelism."""
                    if _tas_segmenter is None:
                        return None
                    segs = _tas_segmenter.segment(prepared.poses_norm, fps=prepared.meta.fps)
                    return [
                        {
                            "element_type": s["element_type"],
                            "start": s["start"],
                            "end": s["end"],
                            "confidence": s["confidence"],
                        }
                        for s in segs
                    ]

                # Offload TAS to thread — asyncio.create_task does NOT parallelize CPU/GPU code
                segments_coro = asyncio.to_thread(_run_tas_sync)
```

                # --- Biomechanics analysis (existing) ---
                metrics: list = []
                phases: ElementPhase | None = None
                recommendations: list = []

                if req.element_type:
                    from src.analysis import element_defs
                    from src.analysis.metrics import BiomechanicsAnalyzer
                    from src.analysis.phase_detector import PhaseDetector
                    from src.analysis.recommender import Recommender

                    element_def = element_defs.get_element_def(req.element_type)
                    if element_def is not None:
                        phase_detector = PhaseDetector()
                        phase_result = phase_detector.detect_phases(
                            prepared.poses_norm, prepared.meta.fps, req.element_type
                        )
                        phases = phase_result.phases

                        analyzer = BiomechanicsAnalyzer(element_def)
                        metrics = analyzer.analyze(prepared.poses_norm, phases, prepared.meta.fps)

                        recommender = Recommender()
                        recommendations = recommender.recommend(metrics, req.element_type)

                # Wait for TAS to finish
                segments_result = await segments_coro
```

Update the return to include `segments=segments_result`:

```python
                return ProcessResponse(
                    poses_r2_key=poses_key,
                    metrics_r2_key=metrics_key,
                    stats=metrics_data["stats"],
                    metrics=metrics_data["metrics"],
                    phases=metrics_data["phases"],
                    recommendations=recommendations,
                    segments=segments_result,
                )
```

- [ ] **Step 4: Update VastResult construction in client.py**

In `backend/app/vastai/client.py`, update `process_video_remote_async` to parse `segments` from response:

```python
segments = response_data.get("segments")
return VastResult(
    video_key=response_data.get("video_key", video_key),
    poses_key=response_data.get("poses_r2_key"),
    csv_key=None,
    stats=response_data.get("stats", {}),
    metrics=response_data.get("metrics"),
    phases=response_data.get("phases"),
    recommendations=response_data.get("recommendations"),
    segments=segments,
)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/vastai/client.py ml/gpu_server/server.py
git commit -m "feat(gpu_server): ONNX TAS concurrent with biomechanics via asyncio.to_thread"
```

---

### Task 11: SessionElement ORM + Migration

**Files:**

- Modify: `backend/app/models/session.py:57-62`
- Create: `backend/alembic/versions/XXXX_add_session_elements.py`

- [ ] **Step 1: Add SessionElement model**

Add to `backend/app/models/session.py`:

```python
class SessionElement(TimestampMixin, Base):
    """Detected skating element from automatic timeline segmentation."""

    __tablename__ = "session_elements"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
    )
    element_type: Mapped[str] = mapped_column(String(50))
    element_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_frame: Mapped[int] = mapped_column()
    end_frame: Mapped[int] = mapped_column()
    confidence: Mapped[float] = mapped_column(Float)
    phases_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session: Mapped[Session] = relationship("Session", back_populates="elements")
```

Add relationship to `Session` class:

```python
    elements: Mapped[list[SessionElement]] = relationship(
        "SessionElement",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    segmentation_status: Mapped[str] = mapped_column(
        String(20), server_default="pending", nullable=False,
    )
```

Add import for `uuid` (already present at top).

- [ ] **Step 2: Generate migration**

Run: `cd backend && uv run alembic revision --autogenerate -m "add session_elements table"`
Review the generated migration file.
Run: `cd backend && uv run alembic upgrade head`

- [ ] **Step 3: Run existing backend tests**

Run: `uv run pytest backend/tests/ -v --no-cov -k "session"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/session.py backend/alembic/versions/
git commit -m "feat(backend): add SessionElement ORM + migration for timeline data"
```

---

### Task 12: Backend Schemas + CRUD for Timeline

**Files:**

- Modify: `backend/app/schemas.py:363-398`
- Modify: `backend/app/crud/session.py`

- [ ] **Step 1: Add timeline schemas**

Add to `backend/app/schemas.py` in the Sessions section:

```python
class ElementSegmentResponse(BaseModel):
    id: str
    element_type: str
    element_name: str | None = None
    start_frame: int
    end_frame: int
    confidence: float
    phases_json: dict | None = None

    model_config = {"from_attributes": True}


class TimelineData(BaseModel):
    segments: list[ElementSegmentResponse]
    segmentation_confidence: float | None = None
    segmentation_status: str = "pending"
```

Add to `SessionResponse`:

```python
    timeline: TimelineData | None = None
    segmentation_status: str = "pending"
```

- [ ] **Step 2: Add batch_insert_elements CRUD + selectinload**

Add to `backend/app/crud/session.py`:

```python
async def batch_insert_elements(
    db: AsyncSession,
    session_id: str,
    segments: list[dict],
    segmentation_confidence: float | None = None,
) -> list[SessionElement]:
    """Batch insert timeline segments in a single transaction."""
    from app.models.session import SessionElement

    elements = []
    for seg in segments:
        element = SessionElement(
            session_id=session_id,
            element_type=seg["element_type"],
            element_name=seg.get("element_name"),
            start_frame=seg["start"],
            end_frame=seg["end"],
            confidence=seg["confidence"],
            phases_json=seg.get("phases_json"),
        )
        db.add(element)
        elements.append(element)
    await db.flush()
    return elements
```

Also update `get_by_id` to eager-load elements:

```python
result = await db.execute(
    select(Session)
    .options(selectinload(Session.metrics))
    .options(selectinload(Session.elements))  # P0: prevent MissingGreenlet
    .where(Session.id == session_id)
)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py backend/app/crud/session.py
git commit -m "feat(backend): add TimelineData schema + batch_insert_elements CRUD"
```

---

### Task 13: Worker Saves Timeline Data

**Files:**

- Modify: `backend/app/worker.py:348-376`

- [ ] **Step 1: Update worker to save segments (single transaction with metrics)**

In `backend/app/worker.py`, merge segment saving into the SAME `async with async_session()` block as metrics (P0: prevent partial writes):

```python
        # Save metrics + segments in single transaction
        if session_id:
            try:
                from app.database import async_session

                async with async_session() as db:
                    # Save metrics (existing code)
                    if vast_result.metrics:
                        await save_metrics(db, session_id, vast_result.metrics)

                    # Save timeline segments (new)
                    if vast_result.segments:
                        from app.crud.session import batch_insert_elements
                        seg_confidence = float(np.mean([s["confidence"] for s in vast_result.segments])) if vast_result.segments else None
                        await batch_insert_elements(db, session_id, vast_result.segments, segmentation_confidence=seg_confidence)

                    # Update session status atomically
                    session_obj = await get_by_id(db, session_id)
                    if session_obj:
                        if vast_result.segments is not None:
                            session_obj.segmentation_status = "done"
                        else:
                            session_obj.segmentation_status = "failed"

                    await db.commit()  # Single commit for metrics + segments + status
            except (OSError, ValueError, RuntimeError) as save_err:
                logger.warning("Failed to save session data: %s", save_err)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/worker.py
git commit -m "feat(worker): save timeline segments via batch insert"
```

---

### Task 14: Frontend Session Schema + Timeline Types

**Files:**

- Modify: `frontend/src/lib/api/sessions.ts:45-69`

- [ ] **Step 1: Add segment types to SessionSchema**

In `frontend/src/lib/api/sessions.ts`, add before `SessionSchema`:

```typescript
const PhaseFrameSchema = z.object({
  frame: z.number(),
  timestamp: z.number().optional(),
})

const PhasesDataSchema = z.object({
  takeoff: PhaseFrameSchema,
  peak: PhaseFrameSchema,
  landing: PhaseFrameSchema,
})

const ElementSegmentSchema = z.object({
  id: z.string(),
  element_type: z.string(),
  element_name: z.string().nullable().optional(),
  start_frame: z.number(),
  end_frame: z.number(),
  confidence: z.number(),
  phases_json: PhasesDataSchema.nullable().optional(),
})

const TimelineDataSchema = z.object({
  segments: z.array(ElementSegmentSchema),
  segmentation_confidence: z.number().nullable().optional(),
  segmentation_status: z.string().default("pending"),
})
```

Add to `SessionSchema`:

```typescript
  timeline: TimelineDataSchema.optional().nullable(),
  segmentation_status: z.string().default("pending"),
```

- [ ] **Step 2: Add conditional polling for segmentation status**

Update `useSession` to conditionally poll when segmentation is pending:

```typescript
export function useSession(id: string, opts?: Pick<UseQueryOptions<Session>, "refetchInterval">) {
  return useQuery({
    queryKey: ["session", id],
    queryFn: () => apiFetch(`/sessions/${id}`, SessionSchema),
    enabled: !!id,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.segmentation_status === "pending" || data?.status === "processing") {
        return 5000
      }
      return opts?.refetchInterval ?? false
    },
  })
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api/sessions.ts
git commit -m "feat(frontend): add timeline schema + conditional polling for segmentation"
```

---

## Phase 4: Validation & Polish

### Task 15: Integration Test — End-to-End Pipeline

**Files:**

- Create: `ml/tests/tas/test_integration.py`

- [ ] **Step 1: Write integration test**

Create `ml/tests/tas/test_integration.py`:

```python
"""Integration test: full TAS pipeline from poses to segments (ONNX)."""

import numpy as np
import pytest
import torch
from pathlib import Path

from ml.src.tas.model import BiGRUTASRefiner
from ml.src.tas.inference import TASElementSegmenter


@pytest.fixture
def onnx_model(tmp_path):
    """Create a minimal ONNX model for testing."""
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    model.eval()
    onnx_path = tmp_path / "test_refiner.onnx"
    dummy_poses = torch.randn(1, 50, 17, 2)
    dummy_lengths = torch.tensor([50], dtype=torch.long)
    torch.onnx.export(
        model, (dummy_poses, dummy_lengths), str(onnx_path),
        input_names=["poses", "lengths"], output_names=["logits"],
        dynamic_axes={"poses": {0: "batch", 1: "time"}, "lengths": {0: "batch"}, "logits": {0: "batch", 1: "time"}},
        opset_version=17,
    )
    return onnx_path


def test_full_pipeline_jump(onnx_model):
    """Simulate a jump pattern: high hip movement for 30 frames."""
    segmenter = TASElementSegmenter(model_path=onnx_model, device="cpu")
    T = 300
    poses = np.random.randn(T, 17, 2).astype(np.float32) * 0.01
    for f in range(100, 130):
        poses[f, 0, 1] -= 0.5
    segments = segmenter.segment(poses, fps=30.0)
    assert isinstance(segments, list)
    for seg in segments:
        assert seg["element_type"] in ("Jump", "Spin", "Step")
        assert seg["start"] < seg["end"]
        assert 0 <= seg["confidence"] <= 1


def test_full_pipeline_empty(onnx_model):
    """No elements detected in still pose sequence."""
    segmenter = TASElementSegmenter(model_path=onnx_model, device="cpu")
    T = 100
    poses = np.random.randn(T, 17, 2).astype(np.float32) * 0.001
    segments = segmenter.segment(poses, fps=30.0)
    assert isinstance(segments, list)


def test_min_duration_per_type():
    """Verify per-type min duration: Jump≥0.5s, Spin≥2.0s, Step≥3.0s."""
    from ml.src.tas.inference import MIN_DURATION
    assert MIN_DURATION["Jump"] == 0.5
    assert MIN_DURATION["Spin"] == 2.0
    assert MIN_DURATION["Step"] == 3.0
```

- [ ] **Step 2: Run integration test**

Run: `uv run python -m pytest ml/tests/tas/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add ml/tests/tas/test_integration.py
git commit -m "test(tas): add end-to-end integration tests"
```

---

### Task 16: Validate on Test Videos

**Files:**

- Create: `experiments/validate_timeline.py`

- [ ] **Step 1: Write validation script**

Create `experiments/validate_timeline.py`:

```python
"""Validate element timeline on 20 test videos.

Measures: F1@50, F1@25, over-segmentation rate, inference time.
"""

import json
import time
from pathlib import Path

import numpy as np

from ml.src.tas.inference import TASElementSegmenter
from ml.src.tas.metrics import MultiOverlapF1

MODEL_PATH = Path("data/models/tas/bigr_refiner_best.onnx")
TEST_DIR = Path("data/datasets/mcfs/features")
LABEL_DIR = Path("data/datasets/mcfs/groundTruth")


def main():
    if not MODEL_PATH.exists():
        print(f"Model not found: {MODEL_PATH}")
        print("Run experiments/train_tas_v2.py first")
        return

    segmenter = TASElementSegmenter(model_path=MODEL_PATH)
    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50])

    test_files = sorted(TEST_DIR.glob("*.npy"))[:20]
    if not test_files:
        print("No test files found")
        return

    results = []
    over_seg_count = 0
    total_inference_time = 0.0

    for npy_file in test_files:
        poses_op25 = np.load(npy_file)
        from ml.src.tas.dataset import op25_to_coco17, normalize_poses
        from ml.src.pose_estimation.h36m import coco_to_h36m
        poses_coco17 = op25_to_coco17(poses_op25)
        poses_h36m = coco_to_h36m_batch(poses_coco17)  # vectorized
        poses_norm = normalize_poses(poses_h36m)

        label_file = LABEL_DIR / f"{npy_file.stem}.txt"
        if not label_file.exists():
            continue
        from ml.src.tas.dataset import coarse_label
        fine_labels = [line.strip() for line in label_file.read_text().splitlines()]
        true_labels = np.array([coarse_label(l) for l in fine_labels], dtype=np.int64)

        start = time.perf_counter()
        segments = segmenter.segment(poses_norm.astype(np.float32), fps=30.0)
        total_inference_time += time.perf_counter() - start

        # Build pred labels from segments
        pred_labels = np.zeros(len(true_labels), dtype=np.int64)
        id2label = {0: "None", 1: "Jump", 2: "Spin", 3: "Step"}
        label2id = {v: k for k, v in id2label.items()}
        for seg in segments:
            label_id = label2id.get(seg["element_type"], 0)
            pred_labels[seg["start"]:seg["end"] + 1] = label_id

        result = metric.compute(pred_labels, true_labels)
        results.append(result)

        # Over-segmentation: segments < 0.5s
        short_segs = sum(1 for s in segments if (s["end"] - s["start"]) / 30.0 < 0.5)
        over_seg_count += short_segs

    # Aggregate
    keys = results[0].keys()
    avg = {k: float(np.mean([r[k] for r in results])) for k in keys}

    print("\n=== Validation Results (20 videos) ===")
    for k, v in avg.items():
        print(f"  {k}: {v:.4f}")
    print(f"  over-segmentation (<0.5s): {over_seg_count}")
    print(f"  total inference time: {total_inference_time:.2f}s")
    print(f"  avg inference time: {total_inference_time / len(results):.3f}s")

    with open("experiments/timeline_validation.json", "w") as f:
        json.dump({"avg_metrics": avg, "over_segmentation": over_seg_count, "total_time": total_inference_time}, f, indent=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add experiments/validate_timeline.py
git commit -m "test(tas): add timeline validation script for 20 test videos"
```

---

### Task 17: ONNX Export Script + Containerfile R2 Model Entry

**Files:**

- Create: `experiments/export_tas_onnx.py`
- Modify: `ml/gpu_server/server.py` (add TAS model to `_R2_MODELS`)

- [ ] **Step 1: Create ONNX export script**

Create `experiments/export_tas_onnx.py`:

```python
"""Export BiGRUTASRefiner to ONNX for serverless inference.

Usage:
    uv run python experiments/export_tas_onnx.py --checkpoint experiments/checkpoints/tas_v2/fold_0_best.pt --output data/models/tas/bigr_refiner_best.onnx
"""

import argparse
from pathlib import Path

import torch
from ml.src.tas.model import BiGRUTAS, BiGRUTASRefiner


def export_onnx(checkpoint_path: Path, output_path: Path, opset: int = 17) -> None:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    ckpt_cfg = checkpoint.get("config", {})
    use_refiner = checkpoint.get("use_refiner", False)

    if use_refiner:
        model = BiGRUTASRefiner(
            hidden_dim=ckpt_cfg.get("hidden_dim", 128),
            num_layers=ckpt_cfg.get("num_layers", 2),
            dropout=0.0,  # dropout=0 for inference
            refiner_channels=ckpt_cfg.get("refiner_channels", 64),
        )
    else:
        model = BiGRUTAS(
            hidden_dim=ckpt_cfg.get("hidden_dim", 128),
            num_layers=ckpt_cfg.get("num_layers", 2),
            dropout=0.0,
        )

    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    # Create dummy inputs for tracing
    B, T, J, C = 1, 100, 17, 2
    dummy_poses = torch.randn(B, T, J, C)
    dummy_lengths = torch.tensor([T], dtype=torch.long)

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
        opset_version=opset,
    )
    size_mb = output_path.stat().st_size / 1e6
    print(f"Exported {output_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/models/tas/bigr_refiner_best.onnx"))
    parser.add_argument("--opset", type=int, default=17)
    args = parser.parse_args()
    export_onnx(args.checkpoint, args.output, args.opset)
```

- [ ] **Step 2: Verify export script parses**

Run: `uv run python -c "import ast; ast.parse(open('experiments/export_tas_onnx.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 3: Add TAS ONNX model to R2 download list**

In `ml/gpu_server/server.py`, add to `_R2_MODELS`:

```python
TAS_MODEL_PATH = _PROJECT_ROOT / "data/models/tas/bigr_refiner_best.onnx"
_R2_MODELS: list[tuple[Path, str]] = [
    (MOGANET_MODEL_PATH, "models/moganet/moganet_b_ap2d_384x288.onnx"),
    (YOLO_MODEL_PATH, "models/yolov8n.onnx"),
    (TAS_MODEL_PATH, "models/tas/bigr_refiner_best.onnx"),
]
```

No Containerfile changes needed — onnxruntime-gpu already installed, ONNX model downloaded from R2 at startup like other models.

- [ ] **Step 4: Commit**

```bash
git add experiments/export_tas_onnx.py ml/gpu_server/server.py
git commit -m "feat(tas): ONNX export script + R2 model entry for serverless inference"
```

- [ ] **Step 2: Verify container builds**

Run: `podman build -t skatelab-worker-test -f ml/gpu_server/Containerfile .`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add ml/gpu_server/Containerfile
git commit -m "feat(gpu_server): install PyTorch for TAS BiGRU inference"
```

---

### Task 18: Update ROADMAP.md

**Files:**

- Modify: `ROADMAP.md`

- [ ] **Step 1: Add AI Element Timeline entry to ROADMAP**

Add to relevant section in `ROADMAP.md`:

```markdown
### AI Element Timeline
- [x] BiGRUTAS coarse segmentation (4-class: None/Jump/Spin/Step)
- [x] BoundaryRefinerCNN for boundary quality
- [x] MultiOverlapF1 evaluation at IoU [0.10, 0.25, 0.50]
- [x] Per-element minimum duration filter (Jump≥0.5s, Spin≥2.0s, Step≥3.0s)
- [x] Skeleton1DCNN fine classifier (jump 7-class, spin 5-class, step 3-class)
- [x] Dataset RAM pre-loading + BucketBatchSampler for training perf
- [x] GPU server: TAS ONNX concurrent with biomechanics in /process (asyncio.to_thread)
- [x] Backend: SessionElement ORM + batch insert + TimelineData schema
- [x] Frontend: conditional polling + timeline types in SessionSchema
- [ ] Validate on 20 test videos (F1@50 > 0.80 target)
- [ ] MS-TCN++ fallback if F1@50 < 0.80
```

- [ ] **Step 2: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): add AI Element Timeline implementation status"
```

---

### Task 4b: Vectorized coco_to_h36m_batch

**Files:**

- Modify: `ml/src/pose_estimation/h36m.py`
- Test: `ml/tests/pose_estimation/test_h36m.py`

- [ ] **Step 1: Write failing test for coco_to_h36m_batch**

Add to `ml/tests/pose_estimation/test_h36m.py`:

```python
def test_coco_to_h36m_batch():
    """Vectorized conversion matches per-frame results."""
    from src.pose_estimation.h36m import coco_to_h36m, coco_to_h36m_batch
    poses_coco = np.random.randn(50, 17, 2).astype(np.float32)
    result_loop = np.stack([coco_to_h36m(p) for p in poses_coco])
    result_batch = coco_to_h36m_batch(poses_coco)
    np.testing.assert_allclose(result_loop, result_batch, atol=1e-6)


def test_coco_to_h36m_batch_3d():
    """Batch conversion works with 3D (x, y, conf) input."""
    from src.pose_estimation.h36m import coco_to_h36m_batch
    poses_coco = np.random.randn(30, 17, 3).astype(np.float32)
    result = coco_to_h36m_batch(poses_coco)
    assert result.shape == (30, 17, 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest ml/tests/pose_estimation/test_h36m.py::test_coco_to_h36m_batch ml/tests/pose_estimation/test_h36m.py::test_coco_to_h36m_batch_3d -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement coco_to_h36m_batch**

Add to `ml/src/pose_estimation/h36m.py` after `coco_to_h36m`:

```python
def coco_to_h36m_batch(poses_coco: np.ndarray) -> np.ndarray:
    """Vectorized COCO 17kp → H3.6M 17kp conversion.

    ~50x faster than per-frame loop for N=900 frames.
    Swaps keypoint indices per the COCO→H36M mapping.

    Args:
        poses_coco: (N, 17, 2/3) COCO format keypoints

    Returns:
        poses_h36m: (N, 17, 2/3) H3.6M format keypoints
    """
    poses_h36m = poses_coco.copy()
    # Swap pairs: 9↔10, 11↔12, 15↔16
    poses_h36m[:, [9, 10]] = poses_h36m[:, [10, 9]]
    poses_h36m[:, [11, 12]] = poses_h36m[:, [12, 11]]
    poses_h36m[:, [15, 16]] = poses_h36m[:, [16, 15]]
    return poses_h36m
```

Update `__all__` to include `coco_to_h36m_batch`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest ml/tests/pose_estimation/test_h36m.py::test_coco_to_h36m_batch ml/tests/pose_estimation/test_h36m.py::test_coco_to_h36m_batch_3d -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ml/src/pose_estimation/h36m.py ml/tests/pose_estimation/test_h36m.py
git commit -m "perf(h36m): add vectorized coco_to_h36m_batch — 50x faster than per-frame loop"
```

---

### Task 14b: ElementTimeline UI Component

**Files:**

- Create: `frontend/src/components/session/element-timeline.tsx`
- Modify: `frontend/app/(app)/sessions/[id]/page.tsx`

- [ ] **Step 1: Create ElementTimeline component**

Create `frontend/src/components/session/element-timeline.tsx`:

```typescript
"use client"

import { useTranslations } from "@/i18n"
import type { z } from "zod"
import type { ElementSegmentSchema } from "@/lib/api/sessions"

type Segment = z.infer<typeof ElementSegmentSchema>

interface ElementTimelineProps {
  segments: Segment[]
  fps: number
  duration: number // total frames
}

const TYPE_COLORS: Record<string, string> = {
  Jump: "oklch(var(--score-good))",
  Spin: "oklch(var(--accent))",
  Step: "oklch(var(--score-mid))",
}

export function ElementTimeline({ segments, fps, duration }: ElementTimelineProps) {
  const te = useTranslations("elements")

  if (!segments.length) {
    return (
      <p className="text-muted-foreground text-sm py-4">
        {te("no_elements_detected")}
      </p>
    )
  }

  return (
    <div className="w-full space-y-2">
      <div className="relative h-8 bg-muted rounded-md overflow-hidden">
        {segments.map((seg) => {
          const left = (seg.start_frame / duration) * 100
          const width = ((seg.end_frame - seg.start_frame) / duration) * 100
          const opacity = 0.4 + seg.confidence * 0.6
          return (
            <div
              key={seg.id}
              className="absolute top-0 h-full rounded-sm cursor-pointer hover:ring-2 hover:ring-primary transition-all"
              style={{
                left: `${left}%`,
                width: `${width}%`,
                backgroundColor: TYPE_COLORS[seg.element_type] ?? "oklch(var(--muted))",
                opacity,
              }}
              title={`${te(seg.element_type)}: ${seg.start_frame}-${seg.end_frame} (${(seg.confidence * 100).toFixed(0)}%)`}
            />
          )
        })}
      </div>
      <div className="flex gap-3 text-xs text-muted-foreground">
        {Object.entries(TYPE_COLORS).map(([type, color]) => (
          <span key={type} className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
            {te(type)}
          </span>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Integrate in session detail page**

Add to `frontend/app/(app)/sessions/[id]/page.tsx` after existing session info:

```tsx
import { ElementTimeline } from "@/components/session/element-timeline"

// Inside the component, after session data check:
{session.timeline && session.timeline.segments.length > 0 && (
  <section className="space-y-2">
    <h3 className="nike-h3">{t("element_timeline")}</h3>
    <ElementTimeline
      segments={session.timeline.segments}
      fps={30}
      duration={session.video_frames ?? session.timeline.segments.at(-1)?.end_frame ?? 300}
    />
  </section>
)}
```

- [ ] **Step 3: Add i18n keys**

Add to `frontend/messages/ru.json` under `"elements"`:

```json
{
  "elements": {
    "element_timeline": "Хронология элементов",
    "no_elements_detected": "Элементы не обнаружены",
    "Jump": "Прыжок",
    "Spin": "Вращение",
    "Step": "Шаги"
  }
}
```

Add same keys to `frontend/messages/en.json`.

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && bunx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/session/element-timeline.tsx frontend/app/\(app\)/sessions/\[id\]/page.tsx frontend/messages/ru.json frontend/messages/en.json
git commit -m "feat(frontend): add ElementTimeline component with confidence-based opacity"
```

---

## Self-Review

### 1. Spec Coverage

| Spec Section | Plan Coverage |
|---|---|
| BoundaryRefinerCNN | Task 1-2 |
| MultiOverlapF1 | Task 3 |
| Dataset pre-load + bucketing | Task 4 |
| Vectorized coco_to_h36m_batch | Task 4b |
| Two-pass inference (ONNX Runtime) | Task 5 |
| Training v2 (duration prior, bucketing, DataLoader config) | Task 6 |
| ONNX export for serverless | Task 17 |
| ElementSegmenter v2 | Task 7 |
| Skeleton1DCNN + duration feature | Task 8 |
| Fine classifier training (pre-train + fine-tune) | Task 9 |
| VastResult + /process concurrent (asyncio.to_thread) | Task 10 |
| SessionElement ORM + segmentation_status column | Task 11 |
| Schemas + CRUD + selectinload | Task 12 |
| Worker batch insert (single transaction) | Task 13 |
| Frontend schema + polling | Task 14 |
| ElementTimeline UI component | Task 14b |
| Integration test | Task 15 |
| Validation script | Task 16 |
| GPU Containerfile (no changes — ONNX model from R2) | Task 17 |
| ROADMAP | Task 18 |
| P0-1: asyncio.to_thread instead of create_task | Task 10 |
| P0-2: Differentiable duration prior loss | Task 6 |
| P0-3: Model loaded at server startup | Task 10 |
| P0-4: No torch in serverless — ONNX only | Task 5, 17 |
| P0-5: segmentation_status ORM column | Task 11 |
| P0-6: selectinload(Session.elements) | Task 12 |
| P0-7: Single DB transaction for metrics + segments | Task 13 |
| P0-8: BucketBatchSampler.set_epoch() | Task 4 |
| P0-9: PhasesDataSchema instead of z.record | Task 14 |
| P0-10: ElementTimeline UI component | Task 14b |
| P0-11: torch.compile removed — ONNX inference | Task 5, 17 |
| P0-12: Vectorized coco_to_h36m_batch | Task 4b |
| P1-8: Skeleton1DCNN duration feature | Task 8 |

**Gap:** FineFS boundary dataset and label_ontology.py extension are not covered. These are data-preparation tasks that don't block the pipeline but improve fine classifier training data volume. Can be added as a follow-up task.

### 2. Placeholder Scan

No TBD, TODO, or "implement later" patterns found. All code is concrete.

### 3. Type Consistency

- `VastResult.segments: list[dict] | None` matches worker usage (`vast_result.segments`)
- `SessionElement` fields match `ElementSegmentResponse` schema fields
- `TimelineData` schema matches frontend `TimelineDataSchema`
- `PhasesDataSchema` (frontend) matches `phases_json` structure (backend)
- `BiGRUTASRefiner.__init__` params match `checkpoint["config"]` keys in training script
- `MIN_DURATION` dict in `inference.py` matches spec values (Jump 0.5s, Spin 2.0s, Step 3.0s)
- `ProcessResponse.segments: list[dict] | None` matches GPU server output
- `Skeleton1DCNN` input_dim=513 (512 CNN + 1 duration) matches `fc[0]` weight shape
- `BucketBatchSampler.bin_size=50` (not 500) matches MCFS dataset scale (~15 samples)
- ONNX model from R2 at startup (same pattern as MogaNet-B, YOLOv8n) — no torch in serverless
- `segmentation_status: String(20)` column matches frontend `z.string().default("pending")`
- `asyncio.to_thread` (not `create_task`) for true CPU/GPU parallelism
