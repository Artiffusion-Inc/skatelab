# AI Element Timeline — Design Specification

**Date:** 2026-05-11
**Status:** DRAFT
**Scope:** Two-level coarse→fine element classifier with timeline generation from skeleton poses

---

## Summary

Build a production element timeline system that receives H3.6M 17-keypoint poses `(T, 17, 2)` and outputs a list of detected skating elements with start/end frames, coarse type, fine label, and confidence. The system runs offline as a post-processing stage after pose estimation, on Vast.ai Serverless GPU.

**Key decision:** evolutionary architecture. Keep existing `BiGRUTAS` for coarse segmentation, add lightweight `BoundaryRefinerCNN` for boundary quality, and replace the `SegmentClassifier` (RandomForest) with a learned `Skeleton1DCNN` for fine-grained element classification.

---

## Architecture

### High-Level Flow

```
Poses (T, 17, 2) normalized
        │
        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Coarse TAS v2  │ ──► │ Segment Extractor │ ──► │ Fine Classifier │
│  (BiGRU + CNN)  │     │ (merge + filter)  │     │ (Skeleton1DCNN) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                                              │
        ▼                                              ▼
  per-frame logits                            per-segment label
  [Jump/Spin/Step/None]                       [Axel, 3Lz, FCSp4...]
        │                                              │
        └──────────────────┬───────────────────────────┘
                           ▼
                  ┌─────────────────┐
                  │  Timeline Result │
                  │  list[ElementSegment]
                  └─────────────────┘
```

### Stage 1: Coarse TAS v2

**Input:** `(T, 17, 2)` normalized poses, variable length up to ~7200 frames (4 min @ 30fps).

**Approach:** keep `BiGRUTAS` (already implemented, `pack_padded_sequence` works) and add a `BoundaryRefinerCNN` head on top of coarse logits.

**BiGRUTAS** (unchanged from current):
- 2-layer BiGRU, hidden=128, input_dim=34 (flattened xy)
- Output: `(T, 4)` logits for {None, Jump, Spin, Step}

**BoundaryRefinerCNN** (new):
- Input: coarse logits `(T, 4)` concatenated with raw features `(T, 34)` → `(T, 38)`
- Conv1D(kernel=10, channels=64) → ReLU → Dropout(0.3)
- Conv1D(kernel=10, channels=64) → ReLU
- Dense(4) → refined logits
- Loss component: duration prior (penalize segments < 0.5s during training)

**Why not MS-TCN++ yet:** The current BiGRU + refiner is faster to validate. MS-TCN++ migration becomes Plan B if F1@50 < 0.80 after refiner.

### Stage 2: Segment Extractor

1. Merge contiguous same-label frames
2. Filter by minimum duration:
   - Jump: ≥ 0.5s
   - Spin: ≥ 2.0s
   - Step: ≥ 3.0s
3. Boundary refinement: velocity minima within ±10 frames of detected edges
4. Output: `list[CoarseSegment]` with global frame indices

### Stage 3: Fine Classifier v2

**Current:** `SegmentClassifier` — RandomForest on 5 biomechanical features (airtime, height, knee angle, rotation speed, CoM trajectory shape).

**New:** `Skeleton1DCNN` — learns directly from skeleton sequences.

**Architecture:**
- Input: `(T_seg, 17, 2)` per-segment poses, variable length
- Flatten to `(T_seg, 34)`
- Conv1D(kernel=7, channels=128) → BatchNorm → ReLU → MaxPool
- Conv1D(kernel=5, channels=256) → BatchNorm → ReLU → MaxPool
- Conv1D(kernel=3, channels=512) → BatchNorm → ReLU → GlobalAveragePool
- Dense(256) → Dropout(0.5) → Dense(num_classes)

**Hierarchy (coarse known at inference):**
- Jump family: {Axel, Salchow, Toeloop, Loop, Flip, Lutz, Euler} — 7 classes
- Spin family: {Camel, Sit, Upright, Layback, Combo} — 5 classes
- Step family: {StepSequence, ChoreoSequence, Turns} — 3 classes

**Training strategy:**
1. Pre-train on FSC-64 (4046 samples, 64 fine classes) for representation
2. Fine-tune on MCFS segments (129 classes mapped to unified ontology)
3. Mirror augmentation disabled for direction-sensitive elements (proven harmful, -4.1pp)
4. Class imbalance handling: weighted loss + effective sampling

### BIOES / Phase 3

**Not in v1.** BIOES labeling (YourSkatingCoach) requires isolated jump clips and provides marginal user value over existing rule-based `PhaseDetector` (parabolic CoM fit, R² > 0.80). BIOES may be added as multi-task supervision later when more labeled data is available.

---

## Data Strategy

### Datasets by Phase

| Phase | Dataset | Size | Labels | Use |
|-------|---------|------|--------|-----|
| Coarse TAS | MCFS | 271 videos | Per-frame {Jump, Spin, Step} | Train + validate coarse |
| Coarse TAS | FineFS | 1167 videos | Start/end times | Boundary supervision |
| Coarse TAS | MMFS | 1176 videos | Clip-level | Augment coarse labels |
| Fine classification | FSC-64 | 4046 clips | 64 classes | Pre-train backbone |
| Fine classification | MCFS segments | ~800 clips | 129 classes | Fine-tune |

### Unified Label Ontology

Extend `data_tools/label_ontology.py`:
- Map FSC/MCFS/FineFS classes to canonical names
- Hierarchical codes: `J.Ax.1` (Jump, Axel, 1 rotation), `S.Ca.4` (Spin, Camel, level 4)
- Russian display names for frontend

---

## Integration Plan

### ML Pipeline

```
Video → YOLOv8n → MogaNet-B → coco_to_h36m → GapFiller → Smoothing
  → [NEW] ElementTimeline (poses input)
    → BiGRUTAS + Refiner → Segment Extractor → Skeleton1DCNN
    → ElementSegment list
  → PhaseDetector (per-segment, rule-based)
  → Biomechanics Metrics
  → DTW alignment → Report
```

**Input to ElementTimeline:** `poses: np.ndarray, shape (T, 17, 2)`, normalized.

**Output:** `list[ElementSegment]` where each segment has:
- `element_type`: coarse enum {JUMP, SPIN, STEP}
- `element_name`: fine label string (e.g., "3Lz", "FCSp4")
- `start_frame`, `end_frame`: global indices
- `confidence`: float (coarse_conf × fine_conf)
- `phases`: dict with approach_start, takeoff, peak, landing, exit_end (from PhaseDetector)

### Backend Changes

1. **`VastResult`** (`ml/src/types.py`): add `segments: list[ElementSegment] | None`
2. **`Session` ORM** (`backend/app/models/session.py`): add `session_elements` relationship, `segmentation_confidence` float
3. **`SessionResponse`** (`backend/app/schemas.py`): add `timeline: TimelineData | None`
4. **Worker** (`backend/app/worker.py`): save timeline data when segmentation enabled
5. **New table** `session_elements`: id, session_id, element_type, element_name, start_frame, end_frame, confidence, phases_json, created_at

### Frontend Changes

Reuse existing DAW timeline editor from choreography planner:
- New track row: "Detected Elements"
- Element blocks colored by family (blue=jump, green=spin, yellow=step)
- Tooltip on hover: element name, confidence, duration
- Click to jump to frame in video player

### Deployment

- **Local dev:** CPU/GPU inference, `uv run python -m src.tas.inference`
- **Production:** Vast.ai Serverless GPU, consistent with existing pipeline
- **Batch processing:** arq worker dispatches `process_video_task`, receives `VastResult` with segments

---

## Evaluation Framework

### Coarse Segmentation Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| F1@50 | > 0.85 | Primary — strict boundary overlap |
| F1@25 | > 0.90 | Moderate tolerance |
| F1@10 | > 0.93 | Loose tolerance |
| Edit Score | > 0.80 | Levenshtein distance on segment sequence |
| Frame-wise Acc | > 92% | Baseline, dominated by background class |
| Over-segmentation rate | < 5% | % segments < 0.5s that are false positives |

### Fine Classification Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| H-Type | > 90% | Coarse {Jump, Spin, Step} accuracy |
| H-Family | > 75% | Family-level (toe-pick, edge, Axel jumps) |
| H-Element | > 65% | Specific element top-1 (jump 7-class) |
| H-Full | > 55% | Full hierarchy (element + rotation) |
| Top-5 | > 80% | Within 5 guesses |

### System Metrics

| Metric | Target |
|--------|--------|
| Inference time (4 min program) | < 500ms on V100 |
| GPU memory | < 2GB |
| Model size (total) | < 50MB |

---

## Implementation Roadmap

### Phase 1: Coarse TAS v2 (1–2 weeks)

1. Implement `BoundaryRefinerCNN` in `ml/src/tas/model.py`
2. Add `MultiOverlapF1` metric (thresholds [0.10, 0.25, 0.50]) in `ml/src/tas/metrics.py`
3. Train BiGRU + refiner on MCFS; target F1@50 > 0.80
4. Update `TASElementSegmenter.segment()` for two-pass inference (3fps coarse + 30fps boundary refine)
5. Add minimum duration filtering to segment extractor

### Phase 2: Fine Classifier v2 (2–3 weeks)

6. Implement `Skeleton1DCNN` in `ml/src/tas/classifier.py`
7. Pre-train on FSC-64, fine-tune on MCFS segments
8. Add hierarchical loss: `L = L_coarse + α * L_fine`
9. Replace RF classifier default to Skeleton1DCNN when H-Element > 60%
10. Add `FineFSBoundaryDataset` to `ml/src/tas/dataset.py`

### Phase 3: Integration (1–2 weeks)

11. Extend `VastResult` with `segments` field
12. Add `session_elements` SQLAlchemy model and migration
13. Update worker to persist timeline data
14. Frontend: reuse DAW editor for element timeline display
15. API endpoint: `GET /api/sessions/{id}/timeline`

### Phase 4: Validation & Polish (1 week)

16. Run full pipeline on 20 test videos
17. Measure end-to-end metrics against manual labels
18. Fix over-segmentation outliers
19. Update `ROADMAP.md` and documentation

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BiGRU + refiner fails to reach F1@50 > 0.80 | Medium | High | Fallback Plan B: MS-TCN++ migration (est. 3–4 days) |
| Insufficient data for fine classification | High | Medium | Pre-train on FSC-64; group labels to families if < 60% |
| Over-segmentation persists | Medium | High | CRF post-processing + rule-based merge for < 1s segments |
| Inference too slow on long videos | Medium | Medium | Two-pass: 3fps coarse + boundary refinement only ±2s |
| FineFS label format incompatible | Low | Medium | Converter script: timing string → frame indices |

---

## Key Files

| File | Action |
|------|--------|
| `ml/src/tas/model.py` | Add `BoundaryRefinerCNN`; wrap `BiGRUTAS` → `BiGRUTASRefiner` |
| `ml/src/tas/classifier.py` | Replace `SegmentClassifier` with `Skeleton1DCNN` |
| `ml/src/tas/inference.py` | Update `TASElementSegmenter` for v2 models + two-pass |
| `ml/src/tas/metrics.py` | Extend to `MultiOverlapF1` with thresholds [0.10, 0.25, 0.50] |
| `ml/src/tas/dataset.py` | Add `FineFSBoundaryDataset` |
| `ml/src/types.py` | Extend `VastResult` with `segments: list[ElementSegment]` |
| `ml/src/analysis/element_segmenter.py` | Update `_segment_with_tas()` for new fields and `tas_ml_v2` |
| `backend/app/models/session.py` | Add `session_elements` relationship |
| `backend/app/schemas.py` | Add `TimelineData` to `SessionResponse` |
| `backend/app/worker.py` | Save timeline data when segmentation enabled |
| `data/data_tools/label_ontology.py` | Extend with FineFS classes and hierarchy codes |

---

## Appendix: Mirror Augmentation Decision

**Disabled for direction-sensitive elements.** Experiments in `experiments/README.md` proved mirror flip harmful (-4.1pp) because:
- Lutz vs Flip are mirror images of each other
- Counter-clockwise vs clockwise spin entry
- Approach edge (inside vs outside) is direction-dependent

Mirror augmentation remains enabled only for non-directional classes ( upright spins, generic step sequences).
