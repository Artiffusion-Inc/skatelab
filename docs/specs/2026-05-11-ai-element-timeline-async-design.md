# AI Element Timeline — Async/Parallel Design

**Date:** 2026-05-11
**Status:** DRAFT
**Scope:** Parallel and asynchronous execution strategy for the AI Element Timeline pipeline

---

## 1. Executive Summary

Five specialized agents analyzed training, inference, GPU offloading, backend integration, and frontend rendering. The highest-impact optimization is **training data loading** (10-15x speedup via pre-loading). The highest-impact inference optimization is **batch RF predictions** (2.5x for the classification step). Architecturally, TAS should run **inside the existing GPU `/process` endpoint** concurrently with biomechanics, and the backend should **not** create a separate arq job.

---

## 2. Conflicts Resolved

### Conflict A: Where TAS physically runs
- Pipeline Architect: proposed double-buffered producer-consumer on local GPU.
- GPU Optimizer: proposed running inside Vast.ai `/process` endpoint.
- Backend Integrator: proposed embedding in `process_video_task`.

**Resolution:** All three are correct at different layers. The GPU server's `/process` endpoint runs TAS alongside biomechanics after `prepare_poses()`. The backend's `process_video_task` dispatches a single GPU job and receives unified results. The double-buffered pattern is a P1 optimization for the local inference server or batch worker, not the primary Vast.ai B=1 flow.

### Conflict B: Streaming results vs polling
- GPU Optimizer: do not stream — TAS total < 1s, Vast.ai round-trip (~200ms) exceeds compute.
- Frontend Renderer: reuse existing `useSession` polling.

**Resolution:** Standard request/response within `/process` JSON. Frontend polls via `useSession` every 3-5s while `segmentation_status` is pending. No SSE, no WebSocket.

### Conflict C: ONNX export for BiGRU
- GPU Optimizer: ONNX possible but requires refactoring `pack_padded_sequence`.
- Pipeline Architect: skip TorchScript — effort/speedup ratio poor for small model.

**Resolution:** Do **not** export BiGRU to ONNX. Install PyTorch in the GPU image. The model is <1MB; ONNX refactoring complexity outweighs the gain.

---

## 3. Prioritized Recommendations

### P0 — Must implement (>2x speedup or architectural requirement)

1. **TAS Integration Architecture**
   Run TAS inside the GPU server's `/process` endpoint, immediately after `prepare_poses()`, concurrently with biomechanics analysis. The backend's `process_video_task` consumes a unified response with both metrics and segments. No separate arq job for TAS.

2. **Training Data Loading Overhaul**
   Pre-load MCFS `.npy` into RAM at `Dataset.__init__` (dataset ~488MB). Cache converted/normalized H3.6M arrays to eliminate per-epoch conversion. GPU utilization is currently near 0% because data loading takes **0.769s/batch** while forward takes <0.05s.

3. **Async Database Writes**
   Batch insert `session_elements` in a single transaction using async SQLAlchemy. This prevents blocking the arq worker event loop when inserting 10-20 segments.

### P1 — High impact (20-100% speedup or UX)

4. **Batch RF Predictions**
   Run a single `predict_proba` call across all segments of a video (`n_jobs=-1`). A 3-segment video drops from ~450ms to ~180ms.

5. **torch.compile BiGRU**
   Add `torch.compile(mode="reduce-overhead")` after `model.eval()` in `TASElementSegmenter.__init__`. Estimated 10-20% latency reduction on the BiGRU forward pass.

6. **Training: Sequence-Length Bucketing**
   Implement `BucketBatchSampler` with 500-frame bins. Padding waste drops from 20-35% to <5%, allowing batch_size increase from 8 to 12-16.

7. **Training: DataLoader Config**
   `num_workers=4`, `pin_memory=True`, `prefetch_factor=4`, `persistent_workers=True`.

8. **Frontend: Progressive Rendering**
   Show segments immediately with confidence-based visual states (solid for >0.8, dashed for <0.5). Extend `useSession` with conditional `refetchInterval: 5000` while `segmentation_status` is pending.

### P2 — Nice to have (<20% speedup or future)

9. **Double-Buffered Producer-Consumer**
   GPU Stream A runs BiGRU on video N while CPU thread runs extraction + RF on video N-1. 2x throughput for local batch workers.

10. **Two-Pass Overlapping CUDA Streams**
    3fps coarse on primary stream, 30fps boundary refinement on secondary stream. Only useful if boundary refiner CNN is added later.

11. **Frontend: Click-to-Seek, Hover Debounce**
    Reuse existing `PhaseTimeline` pattern. Trivial implementation.

12. **Fallback Rule-Based Segmenter**
    If Vast.ai fails, run local `ElementSegmenter` as fallback. Product decision required.

---

## 4. Unified Async Architecture

```
Frontend (Next.js)          Backend (FastAPI + arq)       GPU Server (Vast.ai / Local)
     |                              |                               |
     | POST /sessions/{id}/process  |                               |
     |----------------------------->|                               |
     |                              | enqueue process_video_task    |
     |                              |------------------------------>|
     |                              |                               |
     |  202 Accepted                |                         prepare_poses()
     |<-----------------------------|                               |
     |                              |                               |
     |                              |                    +----------+----------+
     |                              |                    |                     |
     |                              |              Biomechanics         TAS Pipeline
     |                              |              (CPU/GPU)            (BiGRU + RF)
     |                              |                    |                     |
     |                              |              (concurrent on GPU)          |
     |                              |                    |                     |
     |                              |                    +----------+----------+
     |                              |                               |
     |                              |<------------------------------|
     |                              |   {metrics, segments} JSON    |
     |                              |                               |
     |<-----------------------------|  200 OK (batch_insert done)   |
     |                              |                               |
     | [useSession poll 3-5s]       |                               |
     |<----------------------------->|                               |
     |                              |                               |
```

**Async flow:**
1. User uploads video → backend queues `process_video_task`.
2. Worker dispatches to GPU `/process`.
3. GPU server extracts poses, then runs biomechanics and TAS **concurrently** (both read from `poses_norm`).
4. GPU returns unified JSON with `metrics` and `segments`.
5. Worker batch inserts `session_elements` into Postgres via async SQLAlchemy.
6. Frontend polls `GET /sessions/{id}`; when `segmentation_status == "done"`, renders timeline with progressive confidence states.

---

## 5. Integration Spec

| # | File | Change | Phase |
|---|------|--------|-------|
| 1 | `ml/gpu_server/server.py` | Add TAS call after `prepare_poses()`. Run concurrently with biomechanics. Add `segments` to response model. | P0 |
| 2 | `ml/src/tas/inference.py` | Implement batched `predict_proba` across all segments. Optional: `torch.compile` wrapper. | P1 |
| 3 | `backend/app/worker.py` | Update `process_video_task` to parse `segments` from GPU response and pass to batch insert. | P0 |
| 4 | `backend/app/models/session.py` | Add `session_elements` relationship and `segmentation_status` enum. | P0 |
| 5 | `backend/app/crud/session.py` | Add `async def batch_insert_elements(...)` using async SQLAlchemy. | P0 |
| 6 | `backend/app/schemas.py` | Add `TimelineData` to `SessionResponse`. | P0 |
| 7 | `frontend/lib/api/sessions.ts` | Extend `SessionSchema` with `segments` and `segmentation_status`. Add conditional `refetchInterval`. | P1 |
| 8 | `frontend/components/analysis/element-timeline.tsx` | New component: render segments with confidence-based visual states, click-to-seek. | P1 |
| 9 | `ml/src/tas/dataset.py` | Pre-load `.npy` to RAM in `__init__`. Cache normalized arrays. | P0 |
| 10 | `ml/scripts/train_tas.py` | Add `BucketBatchSampler`, `num_workers=4`, `pin_memory=True`, `persistent_workers=True`. | P1 |
| 11 | `data/data_tools/label_ontology.py` | Extend with FineFS classes and hierarchy codes for `session_elements`. | P0 |

---

## 6. Open Questions

1. **Concurrent GPU safety.** Biomechanics (ONNX Runtime) and TAS (PyTorch) on the same GPU in the same process. Do they share the CUDA context safely, or do they need separate `torch.cuda.Stream`?
2. **Partial results.** Should the frontend show coarse BiGRU segments before RF classification completes? This would require streaming or backend-to-frontend push, contradicting the "no streaming" decision. Product call needed.
3. **Fallback strategy.** If Vast.ai `/process` fails, do we run local rule-based `ElementSegmenter` or simply mark `segmentation_status = "failed"`?
4. **Dataset growth.** MCFS is ~488MB today. If training dataset grows beyond RAM (e.g. FineFS 1167 videos), what is the paging strategy? `memmap` or lazy loading?
5. **Biomechanics dependency.** `BiomechanicsAnalyzer` may use poses that TAS also needs. If both run concurrently, do we need a shared `poses_norm` buffer or can both read independently?
