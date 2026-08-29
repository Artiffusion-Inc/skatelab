# SkateLab

AI coach for figure skating: video and IMU analysis, biomechanical metrics, progress tracking, choreography planning, and Russian-first feedback.

## Source Of Truth

- This `AGENTS.md` and nested `AGENTS.md` files are canonical agent instructions.
- `CLAUDE.md` compatibility files are intentionally absent. Do not recreate parallel instruction sources.
- Product intent lives in `PRODUCT.md`; design system in `DESIGN.md`; detailed research and plans in `docs/`.

## Repository Map

- `backend/` — Litestar API, SQLAlchemy, Alembic, S3, Valkey/arq workers.
- `ml/` — GPU ML library and Vast.ai worker; no web or database concerns.
- `frontend/` — Next.js 16, React 19, Tailwind 4, TanStack Query, next-intl.
- `mobile/` — KMP shared logic, Android Compose app, SwiftUI iOS shell.
- `infra/` — production Compose, Caddy, Prometheus, deployment scripts.
- `data/` — dataset registry, converters, local model/data layout.
- `experiments/` — exploratory ML work; never production imports.
- `docs/` — research, specifications, plans, and business material.

## Architecture

Frontend/mobile -> Litestar `/v1` API -> PostgreSQL + S3 + Valkey/arq -> Vast.ai Serverless GPU.

ML flow: video -> person detection + MogaNet-B pose -> H3.6M -> tracking/gap fill -> normalization -> optional TCPFormer 3D lift -> smoothing -> phases -> biomechanics/physics -> DTW/GOE -> recommendations.

Boundaries:
- Backend routes must not import pose, analysis, or visualization internals.
- `backend/app/worker.py` may import stable ML data types and scoring helpers; heavy inference runs on Vast.ai.
- `ml/` must not depend on backend, database, queue, or web-framework code.
- Production processing requires `VASTAI_API_KEY`; local GPU fallback is removed.

## Working Policy

- Work directly on `master`. Do not create branches or git worktrees unless user explicitly requests one.
- Preserve unrelated dirty changes. Never reset, checkout, clean, stash, or rewrite user work without approval.
- Keep changes surgical and MVP-first. No speculative abstractions or unrelated refactors.
- For bugs, reproduce with a failing test before fixing. Run checks covering changed scope.
- Commit format: `<type>(<scope>): <description>`; valid values are in `.commit-conventions`.
- Commit completed work automatically after validation; include all repository changes unless user explicitly asks to exclude specific files.

## Commands

```bash
uv sync
bash ml/scripts/setup_cuda_compat.sh

task py-test          # backend + ML tests, excluding slow
task py-typecheck     # basedpyright
task py-lint          # Ruff check + format
task fe-test          # Vitest
task fe-typecheck     # TypeScript
task fe-lint          # Biome
task fe-build         # production Next.js build
task ci               # complete repository checks
task dev              # backend + frontend dev servers
```

Use `uv` for Python, `bun` for frontend, and Gradle wrapper under `mobile/`. Do not substitute npm, pip, or system Gradle.

## ML And Tracking Constraints

- Inference is CUDA-only. Run `ml/scripts/setup_cuda_compat.sh` after dependency sync.
- Distinguish normalized `[0,1]` poses from pixel coordinates; validate formats at boundaries.
- Tracking bugs require frame-level evidence. Locate exact divergence among tracker, anti-steal validator, and tracklet merger.
- Anti-steal requires centroid jump AND skeletal anomaly. Figure-skating motion itself is not an anomaly.

## Safety

- Never commit credentials, production `.env` values, test passwords, private keys, or raw personal data.
- Do not run destructive Git, database, storage, or deployment commands without explicit approval.
- Production infrastructure changes require targeted validation and rollback notes.
