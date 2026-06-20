# .github/CLAUDE.md — GitHub Actions

## Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | PR/push to master | Entry point → calls `ci-reusable.yml` |
| `ci-reusable.yml` | `workflow_call` | Full CI: lint, typecheck, test, build, docker. Path-filtered. |
| `deploy.yml` | Push to master (excl. docs/ml-gpu) | CI → build GHCR images → SSH deploy to VPS |
| `container.yml` | Push to master (ml/gpu_server/**) | Build + push GPU worker image to GHCR |
| `mobile.yml` | PR/push (mobile/**, backend/app/**) | KMP shared tests, Android lint/test/build debug APK |
| `secrets.yml` | PR/push | GitGuardian secret scanning |
| `actionlint.yml` | PR/push (.github/workflows/*) | Lint workflow YAML syntax |
| `renovate.yml` | Weekly (Mon 04:00) | Auto dependency updates |
| `claude.yml` | Issue/PR comments with `@claude` mention | Claude Code via Ollama Cloud (open models) |

> **Danger CI removed (2026-06-20).** Was failing on every PR due to `ERR_STREAM_PREMATURE_CLOSE` on the GitHub API fetch (ARM64 runner + node-fetch gzip), and even if fixed, its branch-naming rule conflicted with the worktree mandate (`worktree-*` branches). Commit/branch/PR-size conventions are now enforced solely by lefthook (`.commit-conventions` is the single source of truth).

## Composite Actions

| Action | Purpose |
|--------|---------|
| `setup-android` | JDK 17 + Gradle cache (used by mobile.yml) |

## CI Pipeline (ci-reusable.yml)

Path-filtered via `dorny/paths-filter`. Runs only relevant jobs per changed files:

| Job | Filter | Runner | Tool |
|-----|--------|--------|------|
| lint | python/** | Blacksmith 2vCPU | ruff format + check |
| typecheck | python/** | Blacksmith 2vCPU | basedpyright |
| ast-grep | python/** or frontend/** | Blacksmith 2vCPU | ast-grep rules |
| test | python/** | Blacksmith 2vCPU | pytest (no slow/integration marks) |
| smoke | ml/** | Blacksmith 4vCPU | pytest smoke tests |
| fe-lint | frontend/** | Blacksmith 2vCPU | Biome |
| fe-typecheck | frontend/** | Blacksmith 2vCPU | tsc |
| fe-build | frontend/** | Blacksmith 4vCPU | next build + bundle analyzer |
| fe-test | frontend/** | Blacksmith 2vCPU | Vitest + coverage |
| docker-backend | docker/** | Blacksmith 4vCPU | Containerfile build (no push) |
| docker-frontend | docker/** | Blacksmith 4vCPU | Containerfile build (no push) |

Coverage: Codecov (backend+ml flags, frontend flag, shared flag, android flag).
All jobs gated by `needs` — lint/typecheck must pass before test/build.

## Deploy Pipeline (deploy.yml)

1. Full CI (ci-reusable, `run-all: true`, `skip-docker: true`)
2. Build + push frontend/backend images to GHCR **+ SCP deploy files to VPS** (all parallel)
3. Write .env + run `deploy.sh` on VPS via SSH (zero-downtime rollout, alembic, health check)

`concurrency: deploy-production` — no cancel-in-progress (never kill a deploy mid-way).

## Mobile CI (mobile.yml)

Path-filtered: `shared` vs `android` changes.

| Job | Filter | Steps |
|-----|--------|-------|
| shared-test | shared/**, backend/app/** | `./gradlew :shared:testDebugUnitTest` + Kover + Codecov |
| android-lint | androidApp/** | ktlintCheck |
| android-test | androidApp/** | compile + unit tests + Kover + Codecov |
| android-build-debug | after lint+test | assembleDebug → upload APK artifact |

## GPU Worker (container.yml)

Triggered by `ml/gpu_server/**` changes. Generates S3 pre-signed URLs for model weights, builds multi-stage container, pushes `ghcr.io/.../skatelab-worker:latest` + SHA tag.

## Runners

Blacksmith (useblacksmith) for CPU-heavy jobs. ubuntu-latest for lightweight (actionlint, secrets, mobile). All use `actions/checkout@v6` + `fetch-depth: 1`.

> **Runner labels fixed (2026-06-20).** `ci-reusable.yml` jobs were on `blacksmith-*-ubuntu-2404[-arm]` labels that Blacksmith stopped provisioning — every CI run hit `startup_failure` (0 jobs created, runner never spawned). Replaced with the labels registered in `.github/actionlint.yaml`: `blacksmith-2vcpu-ubuntu-2204` (light jobs: changes, lint, typecheck, coverage, design-ci, fe-check, fe-test, ci-passed) and `blacksmith-4vcpu-ubuntu-2204` (heavy jobs: test, smoke, fe-build, docker-backend, docker-frontend). vCPU tier preserved per job.

## Secrets

| Secret | Used by | Purpose |
|--------|---------|---------|
| `VPS_SSH_KEY` | deploy.yml | SSH deploy key |
| `VPS_HOST` | deploy.yml | Server IP |
| `VPS_USER` | deploy.yml | SSH user |
| `GHCR_PAT` | deploy.sh on VPS | GHCR login |
| `JWT_SECRET_KEY` | deploy.yml env | JWT signing |
| `SKATELAB_DB_PASSWORD` | deploy.yml env | Postgres |
| `S3_*` | container.yml, deploy.yml | S3-compatible storage (RustFS) |
| `VASTAI_API_KEY` | deploy.yml env | Remote GPU |
| `RESEND_API_KEY` | deploy.yml env | Email service |
| `CODECOV_TOKEN` | ci-reusable, mobile.yml | Coverage upload |
| `GITGUARDIAN_API_KEY` | secrets.yml | Secret scanning |
| `RENOVATE_TOKEN` | renovate.yml | Dep auto-updates |
| `OLLAMA_API_KEY` | claude.yml | Claude Code via Ollama |

## Conventions

- **Reusable workflow**: CI logic in `ci-reusable.yml`, called by `ci.yml` and `deploy.yml`
- **Path filters**: `dorny/paths-filter` — skip irrelevant jobs
- **Concurrency**: CI cancels in-progress; deploy never cancels
- **Permissions**: minimal per workflow (`contents: read` default)
- **Skill**: Use `/writing-github-actions` when creating or modifying workflows