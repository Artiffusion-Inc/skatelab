# CLAUDE.md

> **PROJECT ROADMAP:** ROADMAP.md — SINGLE SOURCE OF TRUTH for implementation status
> **MODULE DOCS:** @docs/CLAUDE.md — research, specs, plans

---

## Project Overview

ML AI coach for figure skating. Analyze video, compare to pro refs, biomech feedback in Russian.

**Vision:** AI-тренер по фигурному катанию — анализ видео и рекомендации на русском.

## Coding Principles

- **Think first** — state assumptions. Unclear? Ask before code. Present tradeoffs.
- **Minimum code** — no speculative features, abstractions, "flexibility" unrequested. 200 lines → 50? Rewrite.
- **Surgical changes** — each line trace to request. No refactor working code. Match style.
- **Verifiable goals** — tasks → testable outcomes. "Fix bug" → failing test first, then fix. Verify step per plan step.

## Directory Structure

```
skatelab/
├── backend/                          # FastAPI API server
│   ├── app/                          # Python package (backend.app.*)
│   │   ├── routes/                   # FastAPI routers (auth, sessions, metrics, uploads, choreography, relationships)
│   │   ├── models/                   # SQLAlchemy ORM models (User, Session, Connection, MusicAnalysis, ChoreographyProgram)
│   │   ├── crud/                     # Database CRUD operations
│   │   ├── services/                 # Business logic (diagnostics, music analysis, choreography solver)
│   │   ├── auth/                     # JWT auth (deps.py)
│   │   ├── config.py                 # Settings (Pydantic BaseSettings)
│   │   ├── storage.py                # R2/S3 client
│   │   ├── task_manager.py           # Valkey task queue helpers
│   │   ├── metrics_registry.py       # 12+ biomechanical metric definitions
│   │   ├── vastai/                   # Vast.ai Serverless GPU dispatch
│   │   ├── worker.py                 # arq worker (process_video_task, detect_video_task, music_analysis_task)
│   │   └── schemas.py                # Pydantic request/response schemas
│   ├── alembic/                      # Database migrations
│   ├── tests/                        # Backend tests
│   └── pyproject.toml                # Backend-only dependencies
├── frontend/                         # Next.js 16 app
│   ├── app/                          # App router pages
│   ├── components/                   # React components
│   ├── lib/                          # API client, hooks, utils
│   ├── i18n/                         # next-intl (ru/en)
│   └── messages/                     # Translation files
├── ml/                               # ML pipeline (pure library, no backend deps)
│   ├── src/                   # Python package (src.*)
│   │   ├── pose_estimation/          # MogaNet-B (ONNX) + YOLO detection + tracking
│   │   ├── analysis/                 # Metrics, phase detection, recommender
│   │   ├── pose_3d/                  # 3D lifting (ONNX, MotionAGFormer/TCPFormer)
│   │   ├── detection/                # Person detection (YOLOv8n), spatial reference
│   │   ├── tracking/                 # DeepSORT, Sports2D, tracklet merger
│   │   ├── alignment/                # DTW alignment vs reference
│   │   ├── utils/                    # Smoothing, geometry, gap filling
│   │   ├── visualization/            # HUD, skeleton, comparison, export
│   │   └── tas/                      # TAS element segmentation (BiGRU + RF)
│   ├── gpu_server/                   # Vast.ai GPU server (Containerfile)
│   ├── tests/                        # ML tests
│   └── pyproject.toml                # ML dependencies
├── docs/                             # Documentation
│   └── research/                     # Research papers and findings
├── infra/                            # Infrastructure
│   ├── Containerfile                 # Docker image for backend
│   └── Caddyfile                     # Reverse proxy config
├── data/                             # Data files (datasets, references)
├── experiments/                      # Jupyter notebooks, experiments
└── pyproject.toml                    # Root config (shared dev deps)
```

## Architecture

```
Frontend (Next.js 16) → FastAPI (backend/) → Valkey queue → arq worker (backend/app/)
  → [VASTAI_API_KEY set?]
    → YES: upload to R2 → Vast.ai route → GPU worker → download from R2
    → NO:  local GPU (process_video_pipeline)

ML Pipeline:
  Video → PersonDetector (YOLOv8n) → MogaNet-B (ONNX, COCO 17kp)
    → coco_to_h36m() conversion → GapFiller → Smoothing (One-Euro, Numba JIT)
    → [Optional] CorrectiveLens (3D lift → kinematic constraints → project back to 2D)
    → Phase Detection (CoM-based, adaptive sigma)
    → Biomechanics Metrics (airtime, height, knee angles, rotation, landing quality)
    → DTW alignment vs reference → GOE proxy score
    → Rule-based Recommender → Russian Text Report

Choreography Planner:
  Upload music → librosa/MSAF analysis (BPM, key, segments)
  → pychromaprint fingerprint → arq worker
  → ISU element DB + CSP solver → SVG rink renderer + DAW timeline editor
```

**Key architectural constraint:** Backend (`backend/`) no import ML pipeline internals (pose estimation, analysis, visualization). arq worker may import ML types (`H36Key`, `VastResult`) and dispatch to ML, never call pipeline internals direct. Heavy ML → GPU (local or Vast.ai Serverless).

**Key decisions:**

- **MogaNet-B (ONNX)**: primary 2D pose estimation — top-down, YOLO detect → MogaNet-B keypoints, 384x288 input, COCO 17kp
- **COCO 17kp → H3.6M 17kp**: `coco_to_h36m()` conversion after MogaNet-B inference
- **CorrectiveLens**: 3D lift corrective layer 2D skeleton (disabled by default, ~3px max shift)
- **Tracking**: DeepSORT (preferred) → Sports2D (fallback) → TrackValidator anti-steal → TrackletMerger post-hoc
- **CoM trajectory** not flight time (eliminates 60% error low jumps)
- **OOFSkate proxy features**: landing quality, torso lean, approach arc (no blade edge detection)

## Tech Stack

| Component           | Technology                                                                 |
| ------------------- | -------------------------------------------------------------------------- |
| **ML Pipeline**     | Python, ultralytics, onnxruntime-gpu, scipy, numba                              |
| **Backend API**     | FastAPI, SQLAlchemy, Alembic, arq + Valkey                                 |
| **Frontend**        | Next.js 16, React, Tailwind CSS, shadcn/ui, Recharts, three.js             |
| **Storage**         | Cloudflare R2 (S3-compatible), Postgres                                    |
| **Remote GPU**      | Vast.ai Serverless                                                         |
| **Testing**         | pytest (backend), tsc + next lint + vitest (frontend) |
| **Task Runner**     | go-task (Taskfile.yaml)                                                    |
| **Package Manager** | uv (Python), bun (JS)                                                      |

## Git & GitHub Workflow

### Branches

- **Format**: `feature/<short-name>` (e.g., `feature/onnx-export`)
- **Main branch**: `master`
- **Pre-push**: `git fetch origin && git merge origin/master`

### Commits

- **Format**: `<type>(<scope>): <description>`
- **Types**: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `ci`
- **Scopes**: `pose`, `viz`, `tracking`, `analysis`, `pipeline`, `cli`, `models`, `repo`, `frontend`, `backend`, `dev`, `ci`, `vastai`, `infra`

### Pull Requests

| Field       | Value                                              |
| ----------- | -------------------------------------------------- |
| Base branch | `master`                                           |
| Title       | Same format as commit                              |
| Description | Include "Что сделано" and "Как проверить" sections |

## GPU Requirements

**GPU-only. CPU inference forbidden.** Always use `device='cuda'`.
Pre-run: `bash ml/scripts/setup_cuda_compat.sh` (required after `uv sync`).
System CUDA 13.2, onnxruntime-gpu needs CUDA 12 compat libs `.venv/cuda-compat/`.

## Key Concepts

- `poses_norm` — Normalized [0,1], `poses_px` — Pixel coords. Validate `assert_pose_format()`.
- MogaNet-B outputs COCO 17kp → `coco_to_h36m()` → H3.6M 17kp format
- **CorrectiveLens**: 2D → MotionAGFormer 3D lift → kinematic constraints → anchor projection → blend. Disabled by default.
- **CUDA compat**: standalone CUDA 12 libs `.venv/cuda-compat/` with patched RUNPATH.

## Remote GPU Processing (Vast.ai Serverless)

Worker dispatches Vast.ai Serverless GPU when `VASTAI_API_KEY` set, fallback local GPU. Worker code `backend/app/worker.py`, Vast.ai server `ml/gpu_server/`.

**Image**: `ghcr.io/Artiffusion-Inc/skatelab-worker:latest` — multi-stage, 4.9GB, no torch/timm/triton.

## Tracking Debugging Workflow

Tracking degrades (skeleton jumps wrong person) → data-driven analysis. **Do NOT guess — extract data, find exact divergence frame.**

### Step 1: Isolate the layer

Tracking pipeline 3 layers, each can cause track switches:

1. **DeepSORT** (preferred) / **Sports2D** (fallback) — appearance-based ReID + Kalman filter or centroid association
2. **Anti-steal logic** — `ml/src/pose_estimation/_track_validator.py`, guards centroid jumps + skeletal anomaly
3. **Tracklet merger** — post-hoc NaN gap fill with biometric re-association (SkeletalIdentity)

### Step 2: Analyze centroid trajectories

CSV check:

- **Sports2D misassignment**: track ID wrong detection index, no anti-steal trigger
- **Anti-steal false positive**: `target_track_id` switched though Sports2D assigned correct
- **Tracklet merger error**: wrong track merged into gap

### Step 3: Fix root cause

Lessons:

- **Anti-steal use AND (not OR)** position + biometric signals.
- **Kalman dt=1.0 (frame-based), not dt=1/fps**.
- **Figure skating movements NOT anomalies** — leg swings, rotations normal.

### Anti-steal thresholds

- Centroid jump: `> 0.15` (normalized coords)
- Skeletal anomaly: `> 0.25` (bone ratio change)
- **Logic: AND** — both exceed threshold same time
