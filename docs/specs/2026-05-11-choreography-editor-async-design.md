# Choreography Editor — Async & Parallel Design Consolidated Report

**Date:** 2026-05-11
**Scope:** Backend I/O + ML pipeline, Frontend interactions, Architecture planning, QA / CI parallelization
**Sources:** 4 parallel domain agents (Backend audit, Frontend interactions, Architecture planning, QA & testing)

---

## 1. Executive Summary

This report consolidates findings from four parallel analysis agents into a single actionable design document for the choreography editor and supporting backend systems.

### Top 10 Recommendations

| # | Recommendation | Layer | Priority | Source |
|---|----------------|-------|----------|--------|
| 1 | Fix partial-commit and pagination bugs before any parallel work — data loss risk | Backend | P0 | Backend audit |
| 2 | Consolidate element library into a single backend `GET /elements/registry` endpoint | Backend / Frontend | P0 | Architecture + Frontend |
| 3 | Use imperative DOM updates (`setAttribute`) during rink drag; sync to Zustand only on `pointerup` | Frontend | P0 | Frontend |
| 4 | Activate existing Batch RTMO, CUDA Graph, and IO Binding code — 2.5-4x inference speedup with ~1 day of integration work | ML Pipeline | P0 | Backend audit |
| 5 | Implement patch-based undo/redo with Immer `produceWithPatches` on the main thread | Frontend | P1 | Frontend + Architecture |
| 6 | Add SSE progress endpoint for async music analysis and switch frontend from polling | Backend / Frontend | P1 | Architecture + Backend audit |
| 7 | Fix N+1 presigned URL generation with singleton aiobotocore client + `asyncio.gather` | Backend | P1 | Backend audit |
| 8 | Align ISU validation rules between frontend TES bar and backend `rules_engine.py` via the canonical registry | Cross-cutting | P1 | Architecture |
| 9 | Parallelize CI with `pytest-xdist --dist=loadfile` and vitest `pool: "threads"` | QA / CI | P2 | QA agent |
| 10 | Add deterministic choreography store tests with isolated module execution before v1.2 polish | QA | P2 | QA agent |

### Conservative Corrections

- **CUDA Graph and IO Binding are already implemented** in `ml/src/pose_estimation/rtmo_batch.py` (lines 258-322 and 362). The original design doc estimated 3-5 days and 4-6 days respectively; the audit found the real integration work is 1-3 hours each.
- **`arq` does not support `_depends_on`**. Any task chaining must use manual enqueue at the end of the parent task, not dependency primitives.
- **NVENC is already implemented** in `H264Writer`. The remaining work is NVDEC decode, not encode.

---

## 2. Backend Async / Parallel Recommendations

### 2.1 Critical Bugs — Fix Before Parallelization

The backend audit identified four bugs that break functionality or corrupt data. They must be resolved first because they affect the same files (CRUD, routes, worker) that parallel optimizations will touch.

| Bug | Location | Impact | Fix |
|-----|----------|--------|-----|
| Route path mismatch | `uploads.py:70` vs `uploads.ts:76` | Multipart upload 404/405 | Add `upload_id` path param or align frontend URL |
| Pagination `total` | `sessions.py:102`, `choreography.py:258` | Frontend pagination broken | COUNT query in CRUD layer |
| Connection names null | `connection.py` model, `schemas.py:327` | UI shows empty names | Add SQLAlchemy relationship + `selectinload` |
| Partial commit in worker | `crud/session.py:101`, `worker.py:335` | Silent data loss on failure | Remove `db.commit()` from `update_session_analysis`; let caller manage transaction |

### 2.2 I/O Parallelism Quick Wins (~12 hours total)

| Opportunity | Current | Target | Effort |
|-------------|---------|--------|--------|
| N+1 presigned URLs | Sequential loop generates 40 presigned URLs per `limit=20` list | Singleton aiobotocore client + `asyncio.gather` | 3-4 h |
| `list_by_user` missing `selectinload(metrics)` | Lazy-load N+1 on serialization | Eager load in query | 15 min |
| `serve_output` double round-trip | HEAD then GET to R2 | Single GET with 404 handling | 30 min |
| bcrypt blocking event loop | ~300 ms sync hash in async auth handler | `asyncio.to_thread` wrapper | 15 min |
| Sync-in-async uploads routes | `boto3` client in `async def` | Switch to existing async storage functions | 1 h |
| aiobotocore client per call | New TLS handshake every call | Lifespan singleton + warm connection | 2 h |
| Valkey pool per call | Connect/close per task | Lifespan singleton pool | 3-4 h |
| arq pool per enqueue | Create/close per request | Lifespan singleton pool | 1 h |
| `session_saver` N+1 metrics | 12 queries per save | Batch query for current best values | 2-3 h |

### 2.3 ML Pipeline Optimizations (~25 hours total)

| Opportunity | Speedup | Effort | Note |
|-------------|---------|--------|------|
| Batch RTMO inference (`BatchPoseExtractor`) | 2.5-4x | 2-3 days | Tracking missing in batch extractor; keep sequential tracking post-process |
| Double buffering (`AsyncFrameReader`) | ~0.7 s net | 4-6 h | Already exists in `frame_buffer.py`; wire into `pose_extractor.py` |
| ONNX SessionOptions tuning | 10-20% | 2-3 h | `graph_optimization_level=ORT_ENABLE_ALL` |
| IO Binding switch | Zero-copy GPU transfer | 2-3 h | `infer_batch_iobinding()` already implemented in `rtmo_batch.py:362` |
| CUDA Graph enable | 5-15% kernel launch | 1-2 h | `_enable_cuda_graph()` already implemented in `rtmo_batch.py:258` |
| PoseExtractor in worker startup | Eliminates ~1-2 s cold start | 1 h | Init in `startup(ctx)`, reuse per job |
| Redundant CoM computation | Minor pipeline overhead | 1-2 h | Compute once, pass through pipeline context |
| `curve_fit` -> `np.polyfit` | ~50x for parabolic fit | 30 min | `physics_engine.py:412,486` |
| ComparisonRenderer parallel | ~2x for dual-video | 2-3 h | `asyncio.gather` or `ThreadPoolExecutor` for two extracts |

### 2.4 Choreography-Specific Backend Gaps

| Gap | Effort | Risk | Dependency |
|-----|--------|------|------------|
| `music_analysis_id` not persisted in CRUD | 30 min | High (data loss) | None |
| Dedup race condition in `upload_music` | 1 h | Medium | None |
| No `GET /elements/registry` endpoint | 15 min | Low | None |
| No SSE progress endpoint for music analysis | 2-3 h | Low | None |
| Missing ISU validation constraints (combo count, triple combo, Euler, spin types, back-half bonus, duration, spatial) | 4-6 h | Medium | Element registry schema stable |
| CSP solver random search (not OR-Tools) | 2-3 days | Low | Validation rules stable |
| PDF parser for SoV (Statement of Value) | TBD | Unknown | Research first |

---

## 3. Frontend Async / Parallel Recommendations

### 3.1 Interaction Performance (P0)

**Rink drag jank** is the highest-ROI fix. The frontend agent found that `RinkDiagram` calls `updateElementPosition()` on every `pointermove`, triggering Zustand state updates, `useMemo` recalculation for ~300 SVG nodes, and full React reconciliation at 60-120 Hz.

**Recommendation:**
- During `pointermove`, **do not call React state setters.**
- Use a `useRef` for live drag coordinates.
- Imperatively mutate the DOM node:
  ```text
  const g = svgRef.current.querySelector(`[data-el-id="${id}"]`);
  g.setAttribute('transform', `translate(${dx}, ${dy})`);
  ```
- Sync to the store exactly once on `pointerup`.
- Memoize the static background (ice, lines, circles) with `React.memo` or move them outside the reactive tree.
- If element counts exceed ~100 or animated flow-path curves are added, migrate to a single `<canvas>` driven by `requestAnimationFrame` and `useRef`-based state.

### 3.2 State Management

**TES calculation:** Keep on the main thread. It is `O(n)` over at most 50-60 elements and executes in <0.1 ms on modern hardware. Only offload to a Web Worker if ISU rule complexity grows and execution exceeds ~5 ms on a 6x CPU throttle. If offloaded, send a compact tuple array `[code, goe, jumpPassIndex, timestamp]`, not full store state.

**Undo/redo:** Use Immer `produceWithPatches` on the main thread. Maintain a history stack of `{patches, inversePatches, timestamp}` capped at 50 steps. Group rapid-fire mutations (e.g., a drag from t=10 to t=15) into a single history entry by debouncing the patch commit until `pointerup`. Do not use a Worker — history is memory-bound, not compute-bound, and structured-clone overhead exceeds any benefit.

### 3.3 Persistence

**Auto-save:** Make it truly async with a three-layer strategy:
1. **Optimistic local state:** Zustand mutations apply immediately; never wait for server ACK before updating UI.
2. **IndexedDB write queue:** On every mutation, write a serializable command (`{type, id, timestamp, ts}`) to IndexedDB. This survives refreshes and is nearly instant.
3. **Background Sync API (or `fetch` with `keepalive`):** If a Service Worker already exists for PWA/offline, register `sync.register('choreo-save')`. If not, use `fetch(..., {keepalive: true})` inside `requestIdleCallback` to avoid event-loop blocking.
4. **Conflict resolution:** For a single-user editor, last-write-wins is sufficient. Include a `clientRevision` integer and have the backend reject stale overwrites.

### 3.4 Media — Waveform Zoom

Do **not** attempt OffscreenCanvas with WaveSurfer.js. The library is architected around a main-thread container DOM element; proxying all event handlers is high-risk and low-reward.

Instead, **pre-compute peaks in a Web Worker:**
- Decode `ArrayBuffer` using `OfflineAudioContext` or a lightweight WASM decoder.
- Generate `peaks` arrays at several resolutions (e.g., `minPxPerSec` of 5, 15, 30, 60).
- Transfer `Float32Array` peaks back via `Transferable`.
- On the main thread, call `wavesurfer.load(audioUrl, peaks)` with the appropriate pre-computed array when zoom changes.
- Use the `MediaElement` backend to move audio decoding out of the main thread.

### 3.5 Data — Element Registry & Validation

**Element registry:** Migrate the hardcoded `ELEMENTS_BV` table in `store.ts` to a backend `GET /api/elements/registry` endpoint (~3-5 KB gzipped). Fetch via React Query with `staleTime: Infinity` and `gcTime: Infinity`. Rely on HTTP caching (`Cache-Control: max-age=86400, stale-while-revalidate=604800`) rather than introducing a Service Worker solely for a tiny JSON file.

**ISU validation feedback:** Trigger backend validation via React Query `useQuery` keyed by the element array. Use `useDeferredValue(elements)` so the rule-violation UI paint is low-priority under React's concurrent renderer. Show the previous validation result while the new one loads (`placeholderData: (previousData) => previousData`) to prevent layout shifts.

---

## 4. Architecture & Cross-Cutting Concerns

### 4.1 Dependency Graph

```
FOUNDATION (start immediately, no blockers)
├── Fix music_analysis_id persistence (30 min)
├── Fix dedup race condition (1 h)
├── GET /elements/registry endpoint (15 min)
├── Element library consolidation (frontend consumes registry)
├── Keyboard shortcuts (2-3 h)
├── Zoom controls (1-2 h)
└── Critical backend bug fixes (partial commit, pagination, upload route)

VALIDATION (depends on Foundation)
├── Missing ISU validation constraints (backend) ← needs stable registry schema
├── Undo/redo (frontend) ← needs stable store schema
├── Import/export JSON ← needs stable element codes
└── Beat markers on waveform ← needs music_analysis_id linkage

EDITOR POLISH (depends on Foundation)
├── Rink snap
├── SSE progress endpoint (music analysis)
└── Tests — store + components ← needs F1 + F8 stable

V1.2 / RESEARCH (parallel, low coupling)
├── CSP solver → OR-Tools (2-3 days)
└── PDF parser for SoV (TBD)
```

**Critical path:** Element library consolidation (F8/B5) → ISU validation constraints (B2) → Import/export JSON (F7). Any work on score calculation or validation before the registry lands risks a second migration.

### 4.2 Parallel Workstreams

| Dev | Focus | Days 1-2 | Days 3-5 |
|-----|-------|----------|----------|
| A | Backend Core | Critical bugs, registry endpoint, dedup, SSE progress | ISU validation constraints, OR-Tools CSP |
| B | Frontend Core | Element library consolidation, zoom, keyboard shortcuts | Undo/redo, import/export, TES alignment |
| C | Editor Polish | — | Beat markers, rink snap, waveform worker, rink rendering |
| D | QA / Infra | — | Frontend/backend tests, CI sharding, coverage gates |

If only 2 developers are available: **A** takes Backend Core + OR-Tools; **B** takes Frontend Core + Editor Polish + Tests. Sequentialize beat markers after `music_analysis_id` fix, and tests after undo/redo + registry stable.

### 4.3 Architectural Flags Preventing Parallelism

1. **Element Library Schema Lock.** Frontend `store.ts` hardcodes `ELEMENTS_BV` and `DEFAULT_DURATIONS`. Until the backend endpoint and frontend refactor land, any ISU rule fix or score calculation will require a second migration. **Recommendation:** B5 + F8 should be the first PR merged.

2. **ISU Rules Bifurcation.** Frontend `score-bar.tsx` and `store.ts` compute TES client-side; backend `rules_engine.py` validates separately. If B2 and F8 proceed independently, the two will diverge. **Mitigation:** Make the backend registry the single source of truth; have the frontend derive all TES data from it.

3. **`music_analysis_id` as Foreign Key.** The DB model has the column, but CRUD ignores it. Programs saved today lose their music reference, so any feature relying on `MusicAnalysis` data (beat markers, SSE progress) will fail on existing records. Fix B1 first.

4. **Rink Renderer Duality.** Client-side rink (`RinkRenderer.tsx`, three.js) and server-side rink (`rink_renderer.py`, SVG) do not share generation logic. Rink snap and server export may produce inconsistent diagrams. **Mitigation:** Define a shared layout schema (JSON) consumed by both renderers; do not encode rendering logic in snap behavior.

5. **Zustand Store as Implicit API.** The frontend store mixes UI state, business logic (`calculateClientSideTes`), and persistence format (`getLayoutForSave`). Undo/redo and tests will be brittle until the store is split into `editor-ui.ts`, `program-data.ts`, and `program-history.ts`. **Recommendation:** Implement undo/redo as a store refactor, not a patch.

---

## 5. Testing & CI Parallelization

### 5.1 Frontend Test Parallelization (Vitest)

Current: single-threaded default. Only 4 real project tests exist; zero choreography component tests.

**Configuration:**
```typescript
// vitest.config.ts
pool: "threads",
poolOptions: {
  threads: {
    singleThread: false,
    isolate: true,
  },
},
maxWorkers: process.env.CI ? 2 : undefined,
sequence: { hooks: "list" },
retry: process.env.CI ? 2 : 0,
testTimeout: 10000,
```

**Key decisions:**
- Use `pool: "threads"` (not `forks`) because happy-dom is lightweight and thread startup is faster.
- `isolate: true` is critical to prevent Zustand store singleton state from leaking between test files.
- Cap at 2 workers in CI to match `blacksmith-2vcpu-ubuntu-2404` runners.
- Do **not** use `pool: "vmThreads"` — happy-dom has known issues with VM context isolation.

### 5.2 Backend Test Parallelization (pytest-xdist)

Current: sequential pytest. `pyproject.toml` does not list `pytest-xdist`.

**Add to dev dependencies:** `pytest-xdist>=3.6.0`, `pytest-rerunfailures>=15.0`, `pytest-timeout>=2.3.0`.

**Execution modes:**

| Mode | Command |
|------|---------|
| Local fast | `uv run pytest backend/tests/ -n auto --dist=loadfile` |
| CI unit | `uv run pytest backend/tests/ -n 2 --dist=loadfile -m "not slow and not integration"` |
| CI full | `uv run pytest backend/tests/ -n 2 --dist=loadfile` |

**Why `--dist=loadfile`:** Tests within the same file run in the same worker, preserving `conftest.py` session-scoped fixtures and avoiding DB transaction leakage across files.

### 5.3 Integration vs Unit Test Separation

Maintain a strict three-tier marker system:

| Category | Markers | CI job | Parallel? |
|----------|---------|--------|-----------|
| Pure unit | none | `test` (every PR) | Yes |
| DB unit | `integration` | `test` (every PR) | Yes |
| Full integration | `integration`, `slow` | `integration` (nightly/merge queue) | No (sequential, `-n0`) |
| Determinism | `determinism` | `test` | Sequential within file |

Integration tests requiring `AsyncTestClient` + Postgres + Valkey are I/O-bound. Parallelizing them with xdist yields diminishing returns and increases DB connection pool pressure. Run them in a separate CI job that spins up `postgres:16` and `valkey/valkey:8` services sequentially.

### 5.4 CI Pipeline Optimizations

| Optimization | Impact |
|--------------|--------|
| Unify backend `pytest` + coverage upload into one step | -30 s setup overhead |
| Move `fe-test` to not require `fe-build` | Saves ~2-3 min |
| Shard frontend tests (`vitest --shard=${{ matrix.shard }}/2`) | Halves wall time on 2 vCPU |
| Conditional integration (only on `master` PRs or label `run-integration`) | Reduces CI spend |

### 5.5 Mock Strategy for Music Analysis

Music analysis depends on `librosa`, `msaf`, and `pychromaprint` — slow, non-deterministic, and require audio files.

**Three-layer mocking pyramid:**

| Layer | Target | Approach |
|-------|--------|----------|
| Unit | `music_analyzer.py` | Patch `librosa.load`, `msaf.process`, `chromaprint.fingerprint` globally in `conftest.py` |
| Service | `score_calculator`, `rules_engine`, `csp_solver` | Inject pre-computed `MusicFeatures` dataclass; never touch librosa |
| Integration | Full upload-to-analysis flow | Use 1-second synthetic sine wave generated in-memory |

Add `@pytest.mark.slow` to any test calling the real `analyze_music()`. With global mocking, choreography unit tests run in <1 s total.

### 5.6 Deterministic Drag-and-Drop Testing

HTML5 drag-and-drop is non-deterministic across environments and hard to test in happy-dom.

| Layer | Method | Scope |
|-------|--------|-------|
| 1 (Primary) | Test store actions directly (`moveElement`, `swapElements`) | Unit tests |
| 2 (Secondary) | Synthetic pointer events with `@testing-library/user-event`; fire `DragEvent` manually for happy-dom | Component tests |
| 3 (Tertiary) | Playwright/Cypress actual browser DnD | Nightly E2E |

**Determinism safeguards:**
- Reset Zustand store to a known state in `beforeEach` (`useChoreographyStore.setState(createInitialState(), true)`).
- Use fixed element IDs (UUID v5 from deterministic seed) in fixtures.

### 5.7 Coverage Gates & Flaky Test Prevention

| Component | Target | Enforcement |
|-----------|--------|-------------|
| Backend services | 80% lines | `pytest --cov-fail-under=80` |
| Backend routes | 70% lines | `pytest --cov-fail-under=70` |
| Frontend `lib/` | 70% lines | vitest `coverage.thresholds.lines=70` |
| Frontend `components/` | 50% lines | vitest `coverage.thresholds.functions=50` |
| New code in PR | 60% lines | Codecov `patch` status check |

**Flaky prevention:**
- CSP solver: accept `seed` param; tests must pass `seed=42` and be marked `@pytest.mark.determinism`.
- Mock `Date.now()` / `performance.now()`; use `vi.useFakeTimers()` in vitest.
- MSW intercepts all `fetch()` in frontend tests; `responses` or `aioresponses` for backend.
- `pytest-rerunfailures`: `--reruns 2 --reruns-delay 1 --only-rerun "AssertionError"`.
- `pytest-timeout`: `--timeout=60` per test, `--timeout-method=thread`.
- Zustand stores reset between files (thread isolation); DB transactions roll back per test.

---

## 6. Unified Implementation Priority Matrix

| ID | Task | Priority | Est. Effort | Layer | Dependencies | Agent |
|----|------|----------|-------------|-------|--------------|-------|
| B1 | Fix partial commit / pagination / upload route | P0 | 3 h | Backend | None | Backend |
| B2 | Fix N+1 presigned URLs + S3/Valkey/arq singletons | P0 | 6 h | Backend | None | Backend |
| F1 | Imperative DOM drag for rink | P0 | 1-2 h | Frontend | None | Frontend |
| M1 | Activate Batch RTMO + CUDA Graph + IO Binding | P0 | 1 day | ML | None | Backend |
| B3 | `GET /elements/registry` endpoint | P0 | 15 min | Backend | None | Architecture |
| B4 | Fix `music_analysis_id` persistence | P0 | 30 min | Backend | None | Architecture |
| B5 | Fix dedup race condition in upload | P0 | 1 h | Backend | None | Architecture |
| F2 | Element library consolidation (frontend) | P1 | 4 h | Frontend | B3 | Frontend + Arch |
| F3 | Async auto-save (IndexedDB + Background Sync) | P1 | 1 day | Frontend | None | Frontend |
| B6 | SSE progress endpoint for music analysis | P1 | 2-3 h | Backend | B4 | Architecture + Backend |
| F4 | Undo/redo with Immer patches | P1 | 1-2 days | Frontend | F2 stable | Frontend + Arch |
| B7 | Missing ISU validation constraints | P1 | 4-6 h | Backend | F2 / B3 | Architecture |
| F5 | Waveform peaks Web Worker + MediaElement backend | P2 | 1 day | Frontend | None | Frontend |
| F6 | Rink snap + zoom controls | P2 | 3-5 h | Frontend | None | Architecture |
| F7 | Beat markers on waveform | P2 | 2-3 h | Frontend | B4 | Architecture |
| Q1 | Frontend/backend test parallelization (xdist, vitest threads) | P2 | 1 day | QA | None | QA |
| Q2 | Choreography store + component tests | P2 | 2-3 days | QA | F4, F2 | QA |
| F8 | Import/export JSON | P3 | 3-4 h | Frontend | F2 + B7 | Architecture |
| F9 | ISU validation deferred UI + React Query | P3 | 2-3 h | Frontend | F2 + B7 | Frontend |
| B8 | Worker GPU cleanup + checkpointing | P3 | 2-3 days | Backend | None | Backend |
| B9 | Post-process task decomposition (manual enqueue) | P3 | 3-5 days | Backend | None | Backend |
| B10 | CSP solver → OR-Tools | P4 | 2-3 days | Backend | B7 | Architecture |
| M2 | FP16 quantization | P4 | 1-2 days | ML | M1 | Backend |
| M3 | NVDEC hardware decode | P4 | 2-3 days | ML | None | Backend |
| B11 | PDF parser for SoV | P4 | TBD | Backend | None | Architecture |

---

## 7. Migration Path

### Phase 1: Foundation (Days 1-2)
**Goal:** Data integrity + single source of truth for elements + eliminate drag jank.

- Fix critical backend bugs (B1: partial commit, pagination, upload route mismatch).
- Fix N+1 presigned URLs and pool singletons (B2).
- Add `GET /elements/registry` (B3) and fix `music_analysis_id` persistence (B4).
- Fix dedup race condition (B5).
- Implement imperative DOM drag for rink (F1).
- Frontend consumes element registry (F2).
- Add keyboard shortcuts (F2b) and zoom controls (F6b).

**Deliverable:** Backend list endpoints return correct totals; programs correctly link to music; element picker uses live registry; rink drag is smooth.

### Phase 2: Validation Alignment + Async Persistence (Days 2-4)
**Goal:** Backend and frontend agree on ISU rules; user never loses work.

- Add missing ISU validation constraints (B7).
- Refactor frontend score-bar to use registry-derived BV + backend-aligned GOE factors (F2c).
- Implement undo/redo with Immer patches (F4).
- Implement async auto-save with IndexedDB queue + Background Sync (F3).
- Add SSE progress endpoint for music analysis (B6); switch frontend from polling.

**Deliverable:** Live TES matches backend `/validate`; undo/redo stable; auto-save non-blocking; upload progress visible.

### Phase 3: Editor Polish + Media Performance (Days 4-6)
**Goal:** Professional DAW-like experience.

- Pre-compute waveform peaks in Web Worker (F5).
- Add beat markers on waveform (F7).
- Add rink snap (F6).
- Add import/export JSON (F8).
- Align deferred ISU validation UI (F9).

**Deliverable:** Timeline zooms without stutter; beat markers visible; elements snap to grid; programs portable.

### Phase 4: Pipeline Speedup + QA Hardening (Days 6-9)
**Goal:** Sub-second analysis + production test coverage.

- Activate Batch RTMO, CUDA Graph, and IO Binding (M1).
- Parallelize CI with pytest-xdist and vitest threads (Q1).
- Write choreography store + component tests (Q2).
- Configure coverage gates (Codecov patch + project).
- Fix worker GPU cleanup and ONNX session lifecycle (B8).

**Deliverable:** 80%+ test coverage on choreography module; ML inference 2.5-4x faster; CI runs in parallel.

### Phase 5: Strategic v1.2 (Week 2+)
**Goal:** Better AI generation and advanced features.

- Migrate CSP solver to OR-Tools (B10).
- FP16 quantization (M2).
- NVDEC hardware decode (M3).
- Post-process task decomposition with manual enqueue (B9).
- PDF parser for SoV research (B11).

**Deliverable:** Optimal layout generation; faster video decode; reliable task chaining.

---

## 8. Summary of Risks & Safeguards

| Risk | Likelihood | Impact | Safeguard |
|------|------------|--------|-----------|
| Batch inference breaks tracking | Medium | High | Keep tracking sequential post-process; `BatchPoseExtractor` already exists without tracking — add it carefully |
| ISU rules diverge between frontend and backend | Medium | High | Backend registry is single source of truth; frontend derives all scores from it |
| FP16 degrades pose accuracy | Low | Medium | Validate on skating dataset; fallback to FP32 |
| S3 singleton client leaks connections | Low | Medium | Lifespan cleanup + health check |
| Partial commit fix breaks existing flow | Medium | High | Single caller is `worker.py`; add rollback scenario test |
| Element library schema changes require second migration | Medium | High | Land B3 + F2 as the very first PR |
| `music_analysis_id` fix breaks existing programs | Low | Medium | Backfill migration or tolerate nulls in beat-marker rendering |
| CUDA Graph re-capture overhead | Medium | Low | Only on batch_size change — rare in production |
| Connection model relationship migration | Medium | Medium | Alembic migration + backward compatibility |
| happy-dom DnD tests flaky | Medium | Medium | Layer 1 store tests are primary; synthetic DOM events are secondary; E2E is safety net |
