# AI Element Timeline — Async & Parallel Review Report

**Date:** 2026-05-12
**Reviewed:** `docs/plans/2026-05-11-ai-element-timeline.md` (18 tasks, 4 phases)
**Reviewers:** 5 specialized agents (Training & Data, GPU Server, Backend Integration, Frontend Renderer, Pipeline Architecture)

---

## Executive Summary

12 P0 (must-fix before implementation), 11 P1 (should-fix), 9 P2 (nice-to-have). The plan is solid in structure but has critical concurrency, data integrity, and gradient-flow bugs that would cause silent failures at runtime.

**Top 3 critical issues:**

1. **Async parallelism is broken** — `asyncio.create_task(_run_tas())` runs synchronous code on the event loop thread; no actual parallelism. TAS blocks biomechanics.
2. **Duration prior loss is non-differentiable** — `argmax` produces integer tensor with no gradient; training silently ignores the loss term.
3. **DB transactions split** — metrics and segments saved in separate `async with async_session()` blocks; partial writes on failure.

---

## P0 Issues (Must Fix)

### P0-1: asyncio.create_task does NOT parallelize CPU/GPU work

**Location:** Task 10, `ml/gpu_server/server.py` — `_run_tas()` inner function

**Problem:** Both TAS inference and biomechanics are synchronous CPU/GPU code. `asyncio.create_task(_run_tas())` schedules `_run_tas` as a coroutine on the same event loop thread. Since `_run_tas` calls `segmenter.segment()` (blocking CUDA), it blocks the event loop. No actual parallelism — TAS runs, then biomechanics runs sequentially.

**Fix:** Use `asyncio.to_thread()` to offload TAS to a thread:

```python
# Replace:
async def _run_tas():
    nonlocal segments_result
    try:
        segmenter = TASElementSegmenter(...)
        segs = segmenter.segment(prepared.poses_norm, fps=prepared.meta.fps)
        segments_result = [...]
    except (ValueError, RuntimeError, OSError):
        logger.exception("TAS segmentation failed")

tas_task = asyncio.create_task(_run_tas())

# With:
def _run_tas_sync():
    """Blocking TAS inference — runs in thread pool."""
    segmenter = _tas_segmenter  # module-level, loaded at startup
    segs = segmenter.segment(prepared.poses_norm, fps=prepared.meta.fps)
    return [{"element_type": s["element_type"], "start": s["start"], "end": s["end"], "confidence": s["confidence"]} for s in segs]

segments_coro = asyncio.to_thread(_run_tas_sync)
# Run biomechanics inline, await segments_coro after
segments_result = await segments_coro  # or use asyncio.gather with biomechanics in to_thread too
```

**Impact:** Without fix, TAS + biomechanics run sequentially, adding ~200-500ms latency per request. With fix, they run in parallel on separate threads (event loop thread + thread pool).

---

### P0-2: Duration prior loss is non-differentiable

**Location:** Task 6, `experiments/train_tas_v2.py` — `_duration_prior_loss()`

**Problem:** The function uses `logits.argmax(dim=-1)` which produces integer tensor with no gradient. The `dur_loss` is added to `ce_loss` but contributes zero gradient — the duration prior is silently ignored during backpropagation.

```python
# BROKEN — argmax has no gradient:
pred = logits.argmax(dim=-1)  # integer tensor, no grad
dur_loss = _duration_prior_loss(pred, lengths, device)  # always zero grad
loss = ce_loss + duration_weight * dur_loss  # dur_loss contributes nothing
```

**Fix:** Use soft probability-based penalty that operates on logits:

```python
def _duration_prior_loss(logits: torch.Tensor, lengths: torch.Tensor, device: torch.device, min_frames: int = 15) -> torch.Tensor:
    """Penalize short predicted segments using soft probabilities (differentiable)."""
    probs = F.softmax(logits, dim=-1)  # (B, T, C)
    non_none_prob = 1.0 - probs[:, :, 0]  # (B, T) — probability of any element
    loss = torch.tensor(0.0, device=device)
    for b in range(logits.shape[0]):
        le = lengths[b].item()
        p = non_none_prob[b, :le]
        # Penalize short high-probability segments using convolution
        kernel = torch.ones(min_frames, device=device) / min_frames
        smoothed = F.conv1d(p.unsqueeze(0).unsqueeze(0), kernel.unsqueeze(0).unsqueeze(0), padding=min_frames // 2)
        # High probability in short burst = short segment = penalty
        short_penalty = (smoothed.squeeze() * (1 - smoothed.squeeze())).mean()
        loss = loss + short_penalty
    return loss / logits.shape[0]
```

Or simpler: use Gumbel-softmax for differentiable argmax approximation.

**Impact:** Without fix, BiGRU+Refiner trains without duration regularization → over-segmentation (many tiny spurious segments).

---

### P0-3: Per-request model loading wastes 200-500ms

**Location:** Task 10, `ml/gpu_server/server.py` — `_run_tas()` inner function

**Problem:** `TASElementSegmenter` is instantiated inside the `/process` handler on every request. Loading PyTorch model + weights takes 200-500ms. This is pure overhead repeated on every video.

**Fix:** Load once at server startup in `_background_init()`, store in module-level variable:

```python
_tas_segmenter: TASElementSegmenter | None = None

async def _background_init():
    global _tas_segmenter
    # ... existing init code ...
    # Load TAS model
    try:
        from src.tas.inference import TASElementSegmenter
        tas_model_path = _PROJECT_ROOT / "data/models/tas/bigr_refiner_best.pt"
        if tas_model_path.exists():
            _tas_segmenter = TASElementSegmenter(model_path=str(tas_model_path), device="cuda")
            logger.info("TAS segmenter loaded at startup")
    except (ValueError, RuntimeError, OSError):
        logger.warning("TAS segmenter not loaded — timeline unavailable")
```

Then in `/process`: `segmenter = _tas_segmenter` (no per-request loading).

**Impact:** 200-500ms saved per request. First-request latency eliminated.

---

### P0-4: torch not needed in serverless — use ONNX export

**Location:** Task 17, `ml/gpu_server/Containerfile`, `ml/src/tas/inference.py`

**Problem:** Plan installed PyTorch (either CUDA ~2.5GB or CPU ~0.6GB) in the serverless container for BiGRU inference. onnxruntime-gpu is already installed for MogaNet-B and YOLOv8n. BiGRU is ~1MB model — ONNX Runtime is the natural inference runtime.

**Fix:** Export BiGRU+Refiner to ONNX via `torch.onnx.export` in training script. Download `.onnx` model from R2 at startup (same pattern as MogaNet-B, YOLOv8n). Use `onnxruntime.InferenceSession` in `TASElementSegmenter` — no torch import at inference.

**Impact:** Container image unchanged (no torch install needed). Cold start faster. Consistent with existing model loading pattern.

---

### P0-5: segmentation_status column missing from Session ORM

**Location:** Task 11-13, `backend/app/models/session.py`

**Problem:** Plan adds `segmentation_status` to Pydantic `SessionResponse` schema but NOT to the `Session` SQLAlchemy model. Without the ORM column, the value can't be persisted or queried.

**Fix:** Add column to Session model:

```python
class Session(TimestampMixin, Base):
    # ... existing fields ...
    segmentation_status: Mapped[str] = mapped_column(
        String(20), server_default="pending", nullable=False,
    )
```

Include in Alembic migration (Task 11).

**Impact:** Without fix, `segmentation_status` is always "pending" (default) — frontend polling never stops.

---

### P0-6: get_by_id doesn't load elements relationship

**Location:** Task 12, `backend/app/crud/session.py`

**Problem:** `get_by_id` only does `selectinload(Session.metrics)`. When `SessionResponse` accesses `session.elements`, it triggers lazy load in async context → `MissingGreenlet` error.

**Fix:** Add `selectinload(Session.elements)` to the query:

```python
result = await db.execute(
    select(Session)
    .options(selectinload(Session.metrics))
    .options(selectinload(Session.elements))
    .where(Session.id == session_id)
)
```

**Impact:** Runtime error (500) on every `GET /sessions/{id}` after elements are saved.

---

### P0-7: Separate DB transactions for metrics and segments

**Location:** Task 13, `backend/app/worker.py`

**Problem:** Plan saves metrics in one `async with async_session()` block and segments in a separate one. If segment save fails, metrics are already committed → inconsistent DB state (session has metrics but no segments, `segmentation_status` stuck at "pending").

**Fix:** Merge into single transaction:

```python
async with async_session() as db:
    # Save metrics (existing)
    if vast_result.metrics:
        await save_metrics(db, session_id, vast_result.metrics)
    # Save segments (new)
    if vast_result.segments:
        await batch_insert_elements(db, session_id, vast_result.segments, ...)
    # Update status atomically
    session_obj = await get_by_id(db, session_id)
    if session_obj:
        session_obj.segmentation_status = "done" if vast_result.segments else "skipped"
    await db.commit()  # Single commit for all changes
```

**Impact:** Without fix, partial writes on failure. Frontend shows stale "pending" status with no segments.

---

### P0-8: BucketBatchSampler has fixed batch order across epochs

**Location:** Task 4, `ml/src/tas/dataset.py`

**Problem:** `BucketBatchSampler.__init__` shuffles once with `random.Random(42).shuffle()`. This produces identical batch ordering every epoch. The model sees samples in the same order every time → reduced generalization.

**Fix:** Add `set_epoch()` method and call it before each epoch:

```python
class BucketBatchSampler:
    def __init__(self, lengths, batch_size=8, bin_size=500, shuffle=True, seed=42):
        self.batch_size = batch_size
        self.bin_size = bin_size
        self.shuffle = shuffle
        self.seed = seed
        self.epoch = 0
        # Group indices by bin
        bins: dict[int, list[int]] = {}
        for idx, length in enumerate(lengths):
            bin_key = length // bin_size
            bins.setdefault(bin_key, []).append(idx)
        self._bins = bins
        self._build_batches()

    def _build_batches(self):
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
        self.epoch = epoch
        self._build_batches()

    def __iter__(self):
        for batch in self.batches:
            yield batch

    def __len__(self) -> int:
        return len(self.batches)
```

Call in training loop: `train_sampler.set_epoch(epoch)` before creating DataLoader.

**Impact:** Without fix, training sees identical batch order every epoch → overfitting, reduced F1.

---

### P0-9: phases_json schema type mismatch

**Location:** Task 14, `frontend/src/lib/api/sessions.ts`

**Problem:** `phases_json: z.record(z.unknown()).nullable().optional()` is an untyped catch-all. Backend returns structured phase data with known shape. This bypasses Zod validation entirely — any malformed data passes silently.

**Fix:** Define and reuse `PhasesDataSchema`:

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

// Then in ElementSegmentSchema:
phases_json: PhasesDataSchema.nullable().optional(),
```

**Impact:** Without fix, frontend can't safely access `phases_json.takeoff.frame` — untyped, runtime errors possible.

---

### P0-10: Missing frontend ElementTimeline component

**Location:** Task 14, plan File Structure table

**Problem:** Plan adds Zod schemas and polling logic but has no task for the actual UI component that renders the timeline. Without it, `timeline` data sits in React Query cache but is never displayed.

**Fix:** Add Task 14b for `ElementTimeline` component:

```typescript
// frontend/src/components/session/element-timeline.tsx
export function ElementTimeline({ segments, fps, duration }: Props) {
  const te = useTranslations("elements")
  // Render timeline bar with colored segments
  // Confidence-based opacity
  // Click handler for segment detail
}
```

Integrate in `frontend/app/(app)/sessions/[id]/page.tsx`.

**Impact:** Feature invisible without UI component.

---

### P0-11: torch.compile incompatible with Vast.ai Serverless — replaced by ONNX

**Location:** Task 5, `ml/src/tas/inference.py`

**Problem:** `torch.compile(model, mode="reduce-overhead")` triggers JIT compilation on first inference. Vast.ai Serverless workers are ephemeral — each cold start triggers recompilation (~30-60s). The compile cache is lost between invocations.

**Fix:** Replaced torch runtime entirely with ONNX Runtime. No torch.compile needed. ONNX model is pre-compiled during export (`torch.onnx.export`), no JIT at inference time.

**Impact:** Zero cold start penalty. ONNX Runtime warms up in <5ms.

---

### P0-12: coco_to_h36m called per-frame in preload (7735 calls/sample)

**Location:** Task 4, `ml/src/tas/dataset.py` — `_load_sample()`

**Problem:** `np.stack([coco_to_h36m(p) for p in poses_coco17])` is a Python loop calling `coco_to_h36m` per frame. For a 30s video at 30fps = 900 frames, that's 900 function calls per sample. With 15 samples, that's 13,500 calls per epoch.

**Fix:** Vectorize as `coco_to_h36m_batch`:

```python
# In ml/src/pose_estimation/h36m.py:
def coco_to_h36m_batch(poses_coco: np.ndarray) -> np.ndarray:
    """Vectorized COCO 17kp → H3.6M 17kp conversion.
    Args: poses_coco: (N, 17, 2/3)
    Returns: poses_h36m: (N, 17, 2/3)
    """
    poses_h36m = poses_coco.copy()
    # Swap columns per the COCO→H36M mapping
    # [0]→[0], [1]→[1], ..., [8]→[8], [9]→[10], [10]→[9], [11]→[12], [12]→[11], [13]→[13], [14]→[14], [15]→[16], [16]→[15]
    poses_h36m[:, [9, 10]] = poses_h36m[:, [10, 9]]
    poses_h36m[:, [11, 12]] = poses_h36m[:, [12, 11]]
    poses_h36m[:, [15, 16]] = poses_h36m[:, [16, 15]]
    return poses_h36m
```

Then in `_load_sample`:

```python
poses_h36m = coco_to_h36m_batch(poses_coco17)  # vectorized
```

**Impact:** ~50x speedup in data loading during preload phase.

---

## P1 Issues (Should Fix)

### P1-1: pin_memory=True on CPU wastes memory

**Location:** Task 6, `experiments/train_tas_v2.py`

`pin_memory=True` is a no-op on CPU and wastes pinned memory on CUDA. Fix: conditional:

```python
pin_memory = (device.type == "cuda")
```

---

### P1-2: persistent_workers=True with num_workers=0 crashes

**Location:** Task 6, `experiments/train_tas_v2.py`

`persistent_workers=True` requires `num_workers > 0`. When `num_workers=0` (debug), PyTorch raises ValueError. Fix:

```python
dl_kwargs = dict(collate_fn=pad_collate)
if num_workers > 0:
    dl_kwargs.update(num_workers=num_workers, persistent_workers=True, prefetch_factor=4, pin_memory=pin_memory)
train_loader = DataLoader(train_ds, batch_sampler=train_sampler, **dl_kwargs)
```

---

### P1-3: bin_size=500 creates bins with < batch_size samples

**Location:** Task 4, `BucketBatchSampler`

With MCFS dataset (~15 samples) and `bin_size=500`, most bins have 1-3 samples. Batches smaller than `batch_size` waste GPU compute. Fix: use `bin_size=50` or adaptive bin sizing:

```python
bin_size = max(50, len(lengths) // 3)  # at least 3 bins for small datasets
```

---

### P1-4: Both sync and async process_video_remote need segments field

**Location:** Task 10, `backend/app/vastai/client.py`

Plan only updates `process_video_remote_async`. The sync `process_video_remote` also constructs `VastResult` and must include `segments`.

---

### P1-5: segmentation_status needs explicit handling for None/failed cases

**Location:** Task 13, `backend/app/worker.py`

Plan sets `segmentation_status="done"` on success but doesn't handle:
- No segments detected → should be "done" (not "pending")
- TAS fails → should be "failed" (not "pending")
- Session created but not yet processed → "pending"

Fix: explicit status transitions:

```python
status = "done" if vast_result.segments is not None else "failed"
# No segments detected = valid result with empty list
if vast_result.segments is not None and len(vast_result.segments) == 0:
    status = "done"  # not "failed" — model ran, found nothing
session_obj.segmentation_status = status
```

---

### P1-6: Frontend refetchInterval must merge with existing POLLING_STATUSES

**Location:** Task 14, `frontend/src/lib/api/sessions.ts`

If existing session detail page already has polling for `status === "processing"`, the new `segmentation_status` check must be combined, not replaced. Verify by reading the existing `useSession` implementation.

---

### P1-7: Add PYTORCH_CUDA_ALLOC_CONF env var for GPU memory

**Location:** Task 17, `ml/gpu_server/Containerfile`

Add to Containerfile:

```dockerfile
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:32
```

Prevents CUDA OOM from large allocation fragmentation.

---

### P1-8: Skeleton1DCNN AdaptiveMaxPool1d loses duration info

**Location:** Task 8, `ml/src/tas/classifier.py`

`AdaptiveMaxPool1d(1)` collapses temporal dimension → discards segment duration. Short and long segments get same representation. Fix: concatenate duration as feature:

```python
def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
    x = x.permute(0, 2, 1)
    x = torch.relu(self.bn1(self.conv1(x)))
    x = torch.relu(self.bn2(self.conv2(x)))
    x = torch.relu(self.bn3(self.conv3(x)))
    x = self.pool(x).squeeze(-1)  # (B, 512)
    # Concatenate normalized duration
    dur = (lengths.float() / lengths.max().float()).unsqueeze(1)  # (B, 1)
    x = torch.cat([x, dur], dim=1)  # (B, 513)
    return self.fc(x)  # fc input_dim=513
```

Update `self.fc = nn.Sequential(nn.Linear(513, 256), ...)`.

---

### P1-9: Mixed precision training for BiGRU

**Location:** Task 6, `experiments/train_tas_v2.py`

BiGRU with hidden_dim=128, 2 layers → can benefit from `torch.amp`. ~30% faster on CUDA:

```python
scaler = torch.amp.GradScaler("cuda")
with torch.amp.autocast("cuda"):
    logits = model(poses, lengths)
    loss = criterion(logits.view(-1, 4), labels.view(-1))
scaler.scale(loss).backward()
scaler.step(optimizer)
scaler.update()
```

---

### P1-10: Missing bucket_collate for fine classifier

**Location:** Task 9, `experiments/train_fine_classifier.py`

Fine classifier uses standard DataLoader with `shuffle=True`, but segment lengths vary wildly (30-300 frames). Should use BucketBatchSampler here too for consistent padding.

---

### P1-11: Worker should handle VastResult.segments=None gracefully

**Location:** Task 13, `backend/app/worker.py`

If Vast.ai returns no `segments` key (e.g., old worker version), `vast_result.segments` is `None`. The `if session_id and vast_result.segments:` check correctly skips, but `segmentation_status` must still be updated to indicate completion.

---

## P2 Issues (Nice to Have)

| # | Issue | Location | Suggestion |
|---|-------|----------|-----------|
| P2-1 | Confidence-based visual states undefined | Task 14b | Define opacity/color mapping: high conf → solid, low → dashed/transparent |
| P2-2 | Segment click → phase detail interaction | Task 14b | Click segment → scroll to phase markers in session detail |
| P2-3 | Timeline empty state messaging | Task 14b | "Elements will appear after processing" with spinner |
| P2-4 | Preload progress indicator for large datasets | Task 4 | Print progress bar during `preload=True` init |
| P2-5 | Gradient checkpointing for BiGRU | Task 6 | `torch.utils.checkpoint` for long sequences (T>500) |
| P2-6 | LR scheduler for training | Task 6 | CosineAnnealingLR or ReduceLROnPlateau for stable convergence |
| P2-7 | WandB/TensorBoard logging | Task 6 | Log loss, F1@50 per epoch |
| P2-8 | On-device warm-start for mobile | Not in plan | Export BiGRU to ONNX for mobile inference |
| P2-9 | Batch segment feature extraction | Task 5 | Vectorize `extract_segment_features` for all segments at once |

---

## Pipeline Architecture Analysis (recovered from failed agent)

### Concurrency Flow: Current Plan vs Fixed

**Current (broken):**
```
/process handler (event loop thread)
  ├─ asyncio.create_task(_run_tas)  ← blocks event loop!
  │   └─ segmenter.segment()  ← synchronous CUDA
  ├─ PhaseDetector.detect_phases()  ← synchronous CPU
  ├─ BiomechanicsAnalyzer.analyze()  ← synchronous CPU
  └─ await tas_task  ← already done (blocking)
```

**Fixed:**
```
/process handler (event loop thread)
  ├─ asyncio.to_thread(_run_tas_sync)  ← thread pool
  │   └─ segmenter.segment()  ← runs on worker thread
  ├─ PhaseDetector.detect_phases()  ← still inline (fast, <50ms)
  ├─ BiomechanicsAnalyzer.analyze()  ← still inline (fast, <100ms)
  └─ await segments_coro  ← real async wait
```

Alternative with `asyncio.gather` (full parallelism):
```
biomech_coro = asyncio.to_thread(run_biomechanics_sync, ...)
tas_coro = asyncio.to_thread(_run_tas_sync)
segments_result, metrics_result = await asyncio.gather(tas_coro, biomech_coro)
```

### Cold Start Timeline

With fixes applied:
```
T+0ms:   Request arrives
T+0ms:   _tas_segmenter already loaded (startup init)
T+5ms:   asyncio.to_thread dispatches TAS
T+5ms:   Biomechanics starts inline
T+150ms: TAS completes (CPU-only BiGRU, small model)
T+200ms: Biomechanics completes
T+200ms: Both done, build response
```

Without fixes:
```
T+0ms:   Request arrives
T+200ms: TASElementSegmenter loads model (per-request)
T+350ms: TAS inference (sequential, blocks event loop)
T+550ms: Biomechanics starts (after TAS finishes)
T+750ms: Response ready
```

**Speedup: 3.75x** (200ms vs 750ms)

### Memory Budget (GPU Server)

| Component | Memory |
|-----------|--------|
| ONNX Runtime (biomechanics) | ~200MB GPU |
| MogaNet-B ONNX model | ~50MB GPU |
| YOLOv8n ONNX | ~10MB GPU |
| BiGRU + Refiner (ONNX) | ~5MB RAM |
| Skeleton1DCNN (ONNX) | ~3MB RAM |
| **Total** | ~260MB GPU + ~8MB RAM |

Container unchanged at ~4.9GB — no torch dependency added. ONNX models downloaded from R2 at startup.

---

## Recommended Plan Updates

### New Tasks to Add

1. **Task 4b:** Add `coco_to_h36m_batch()` vectorized conversion + test
2. **Task 5b:** Remove `torch.compile` default, make serverless-safe
3. **Task 10-revise:** Replace `asyncio.create_task` with `asyncio.to_thread` + startup model loading
4. **Task 11-revise:** Add `segmentation_status` column to Session ORM
5. **Task 12-revise:** Add `selectinload(Session.elements)` to `get_by_id`
6. **Task 13-revise:** Single transaction for metrics + segments
7. **Task 14-revise:** Typed `PhasesDataSchema` instead of `z.record(z.unknown())`
8. **Task 14b:** `ElementTimeline` UI component
9. **Task 17-revise:** ONNX export script + R2 model entry (no torch in container)

### Existing Tasks to Modify

| Task | Change |
|------|--------|
| Task 4 | `BucketBatchSampler.set_epoch()` + smaller `bin_size` |
| Task 5 | ONNX inference (no torch) — removed torch.compile entirely |
| Task 17 | ONNX export script + R2 model entry (no Containerfile changes) |
| Task 6 | Fix `_duration_prior_loss` (soft probabilities), conditional `pin_memory`, `persistent_workers` guard |
| Task 8 | Skeleton1DCNN duration feature concatenation |
| Task 17 | ONNX export + R2 model download (no torch in container) |
