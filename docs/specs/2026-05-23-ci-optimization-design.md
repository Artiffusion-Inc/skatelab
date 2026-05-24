# CI Optimization Design

> **Goal:** Reduce CI wall time from ~2.2 min to ~50s on PRs, cut runner-minutes from ~5 to ~3 per run, move design lint to lefthook for fail-fast locally.

**Architecture:** Merge Python lint+typecheck into single job, remove ast-grep from CI (exists in lefthook), skip smoke on PRs (master only), keep Docker for Containerfile PRs, replace cache with sticky disks for .venv, add design lint to lefthook pre-push, add timeout-minutes on all jobs, add `max-cache-size-mb` to setup-docker-builder, ARM runners for safe jobs, pytest-split for test sharding, Containerfile.ci for docker-frontend artifact pass-through.

**Tech Stack:** GitHub Actions (Blacksmith runners), lefthook, uv, bun, Blacksmith Docker actions

---

## Current State (Measured)

Master CI run 26337209270 — full pipeline, all jobs triggered:

```
changes (6s) ─┬─ lint (ruff+alembic) (37s)      ← 19s setup, 18s work
               ├─ typecheck (basedpyright) (36s)  ← 17s setup, 19s work
               ├─ ast-grep (7s)
               ├─ design-ci (21s)
               ├─ test (70s) ──── smoke (31s)
               │             ──── docker-backend (26s)
               ├─ fe-check (22s) ── fe-build (24s) ── docker-frontend (34s)
               └─ fe-test (18s)

Wall time: 135s (2.2 min)
Total runner-seconds: ~290s
Setup-python-venv overhead: 5 jobs × ~18s = ~90s
```

Step breakdown for lint job:
- setup-python-venv: 19s (checkout + uv + cache restore + uv sync verify)
- ruff format: 1s
- ruff check: 0s
- alembic: 1s
- post-cleanup: 11s

Step breakdown for test job:
- setup-python-venv: 17s
- pytest: 35s
- upload coverage: 3s
- upload results: 2s

## Proposed State

### On PR

```
changes (5s) ─┬─ lint+typecheck+alembic (40s)   ← 1 sticky disk setup, ruff+basedpyright+alembic
               ├─ design-ci (21s)
               ├─ test(1/2) (25s) ──┬─ coverage (5s)
               ├─ test(2/2) (25s) ──┘   ← no smoke/docker on PR
               ├─ fe-check (22s) ── fe-build (24s)
               └─ fe-test (18s)

Wall time: ~50s
Total runner-seconds: ~175s
```

### On push to master (run-all: true)

```
changes (5s) ─┬─ lint+typecheck+alembic (40s)
               ├─ design-ci (21s)
               ├─ test(1/2) (25s) ──┬─ coverage (5s) ──── docker-backend (26s)
               ├─ test(2/2) (25s) ──┘              ──── smoke (31s)
               ├─ fe-check (22s) ── fe-build (24s) ── docker-frontend (10s)
               └─ fe-test (18s)

Wall time: ~65s
```

## Changes

### 1. Merge lint+typecheck → single job

**File:** `.github/workflows/ci-reusable.yml`

Merge `lint` and `typecheck` jobs into `lint-typecheck`:

```yaml
lint-typecheck:
  name: Lint + Type Check
  needs: [changes]
  if: ${{ inputs.run-all || needs.changes.outputs.python == 'true' }}
  runs-on: blacksmith-2vcpu-ubuntu-2404-arm
  timeout-minutes: 10
  steps:
    - uses: actions/checkout@v6
    - uses: ./.github/actions/setup-python-venv
      with:
        python-version: ${{ inputs.python-version }}
    - name: Ruff format
      run: uv run ruff format --check backend/ ml/
    - name: Ruff check
      run: uv run ruff check backend/ ml/ --output-format=github
    - name: Alembic single head
      run: |
        HEADS=$(cd backend && uv run alembic heads 2>&1 | grep -c '(head)')
        if [ "$HEADS" -ne 1 ]; then
          echo "::error::Alembic has $HEADS heads (expected 1)"
          cd backend && uv run alembic heads 2>&1
          exit 1
        fi
    - name: basedpyright
      run: uv run basedpyright --level error backend/app
```

**Savings:** -18s setup overhead, -1 runner allocation, -2s wall time on critical path.

**Trade-off:** Single job failure harder to attribute. Mitigated by step-level annotations (ruff and basedpyright both support `--output-format=github`).

### 2. Remove ast-grep from CI

**File:** `.github/workflows/ci-reusable.yml`

Remove `ast-grep` job entirely. Already covered by lefthook `pre-commit.ast-grep-scan`.

**Prerequisite:** Audit `ast-grep/` rules directory to confirm backend/ml rules don't enforce anything security-critical that ruff misses. If any security rules exist, port them to ruff before removing the CI job.

**Note:** The `design-ci` job also has an `ast-grep scan` step (lines 129-133 of current workflow) that scans `frontend/`. This step should be removed from `design-ci` since it duplicates lefthook `pre-commit.ast-grep-scan`. The `design-ci` job's purpose is design drift detection, not structural linting.

**Savings:** -7s wall time, -1 runner, -1 job in ci-passed `needs`.

### 3. Skip docker+smoke on PR

**File:** `.github/workflows/ci-reusable.yml`

Gate smoke on `run-all` (master push). Keep docker `|| changes.outputs.docker == 'true'` so Containerfile-only PRs still get Docker validation:

```yaml
smoke:
  needs: [changes, test]
  if: ${{ inputs.run-all && needs.changes.outputs.ml == 'true' }}

docker-backend:
  needs: [changes, test]
  if: ${{ !inputs.skip-docker && (inputs.run-all || needs.changes.outputs.docker == 'true') }}

docker-frontend:
  needs: [changes, fe-check, fe-build]
  if: ${{ !inputs.skip-docker && (inputs.run-all || needs.changes.outputs.docker == 'true') }}
```

**Smoke:** Changes `||` to `&&` — smoke only runs on master push when ML files changed. ML-only PRs lose smoke testing. Acceptable — smoke tests GPU inference, not PR-relevant without `run-all`.

**Docker:** Keeps `||` — Containerfile-only PRs still get Docker builds. Preserves current behavior.

**Savings on PR (typical, non-Dockerfile change):** -2 runners, -60s runner-seconds. Smoke (31s) + docker-backend (26s) + docker-frontend (34s) skipped.

**Risk:** ML-only PRs no longer get smoke on PRs. Acceptable — smoke tests GPU inference, not PR-relevant.

### 4. Sticky disks for .venv (replaces cache)

**File:** `.github/actions/setup-python-venv/action.yml`

Replace `actions/cache@v4` for `.venv` with Blacksmith Sticky Disks. Sticky disks mount an NVMe-backed persistent volume in ~3s, vs ~15s for cache download + decompression. This subsumes Change #4 (skip uv sync verify) — sticky disk is always mounted, `uv sync` on an up-to-date venv is a ~2s no-op.

**Before/after comparison:**

| Cache method | Access time | Size limit | Cost |
|---|---|---|---|
| `actions/cache@v4` (GitHub) | ~60s for 500MB | 10GB/repo | Included |
| `actions/cache@v4` (Blacksmith) | ~15s for 500MB | 25GB/repo | Included |
| Sticky Disk (Blacksmith) | ~3s mount | Virtually unlimited | $0.50/GB/mo |

Our `.venv` is ~500MB. Sticky disk cost: ~$0.25/mo per repo.

```yaml
runs:
  using: "composite"
  steps:
    - uses: astral-sh/setup-uv@v7
      with:
        enable-cache: true
        cache-python: true

    - uses: actions/setup-python@v6
      with:
        python-version: ${{ inputs.python-version }}

    - name: Mount venv sticky disk
      uses: useblacksmith/stickydisk@v1
      with:
        key: ${{ github.repository }}-venv-py${{ inputs.python-version }}
        path: .venv

    - name: Sync deps
      run: uv sync --all-packages --frozen --dev
      shell: bash
```

No cache-hit conditional needed — sticky disk persists across runs, `uv sync` on an up-to-date venv completes in ~2s.

**Savings:** -12-15s per Python job that hits cache. With 4 Python job invocations (lint-typecheck, test×2 shards, smoke): ~36-45s total runner time saved. Plus eliminates `actions/cache` upload/download overhead entirely.

**Cost:** ~$0.25/mo per repo for 500MB sticky disk. Negligible.

### 5. Design lint in lefthook pre-push

**File:** `lefthook.yml`

Add design-lint job to `pre-push` hook:

```yaml
pre-push:
  parallel: false
  skip:
    - rebase
  commands:
    warn-pr-size:
      run: | ...  # existing

    design-lint:
      tags:
        - frontend
        - lint
      run: |
        cd frontend
        if [ -f node_modules/.bin/impeccable ] || command -v impeccable &> /dev/null; then
          impeccable detect --json src/ 2>&1 | node ../scripts/impeccable-report.js || true
        fi
        if command -v sg &> /dev/null; then
          sg scan -c ../sgconfig.yml frontend/ || true
        fi
        node ../scripts/design-lock.js check || exit 1
      # exit 1 only on drift — lint violations are warnings
```

**Effect:** Design drift caught locally before push, not after 21s CI wait. CI `design-ci` job remains as blocking gate.

### 6. Add timeout-minutes to all jobs

**File:** `.github/workflows/ci-reusable.yml`

Prevent runaway costs from hung jobs:

| Job | timeout-minutes | Rationale |
|-----|-----------------|-----------|
| changes | 5 | Simple path filter |
| lint-typecheck | 10 | ruff + basedpyright |
| design-ci | 10 | npm + lint + drift check |
| test | 15 | pytest with xdist |
| smoke | 20 | ML inference on GPU |
| fe-check | 10 | Biome + tsc |
| fe-build | 15 | Next.js build |
| fe-test | 10 | Vitest |
| docker-backend | 15 | Container build |
| docker-frontend | 15 | Container build |
| danger | 5 | PR checks |
| ci-passed | 5 | Summary only |

**Savings:** Cost protection — a hung job kills the runner after N minutes instead of running until GitHub's 6h default.

### 7. Add max-cache-size-mb to setup-docker-builder

**File:** `.github/workflows/ci-reusable.yml`

`useblacksmith/setup-docker-builder@v1` already exists (lines 273, 290). Add `max-cache-size-mb` to cap Docker layer cache:

```yaml
- name: Setup Blacksmith Builder
  uses: useblacksmith/setup-docker-builder@v1
  with:
    max-cache-size-mb: "10240"  # 10GB cap
```

**Why:** Without a cap, Docker layer cache grows unbounded, eventually evicting useful layers or hitting storage limits. 10GB is sufficient for 2 Dockerfiles with typical layer sizes.

### 8. ARM runners for safe jobs

**File:** `.github/workflows/ci-reusable.yml`

Switch non-Docker, non-GPU jobs to Blacksmith ARM runners. ARM 2vCPU costs `$0.0025/min` vs x64 `$0.004/min` — **37.5% cheaper per minute**.

| Job | Current | ARM | Risk |
|-----|---------|-----|------|
| lint-typecheck | `blacksmith-2vcpu-ubuntu-2404` | `blacksmith-2vcpu-ubuntu-2404-arm` | Low — ruff + basedpyright have aarch64 wheels |
| design-ci | `blacksmith-2vcpu-ubuntu-2404` | `blacksmith-2vcpu-ubuntu-2404-arm` | Low — node/npm/bun native on ARM |
| fe-check | `blacksmith-2vcpu-ubuntu-2404` | `blacksmith-2vcpu-ubuntu-2404-arm` | Low — bun + biome native on ARM |
| fe-test | `blacksmith-2vcpu-ubuntu-2404` | `blacksmith-2vcpu-ubuntu-2404-arm` | Low — bun + vitest native on ARM |
| danger | `blacksmith-2vcpu-ubuntu-2404` | `blacksmith-2vcpu-ubuntu-2404-arm` | Low — node only |
| ci-passed | `blacksmith-2vcpu-ubuntu-2404` | `blacksmith-2vcpu-ubuntu-2404-arm` | Low — shell only |

**Stay on x64:**
| Job | Why |
|-----|-----|
| test | Python deps (numpy, onnxruntime, numba) — need aarch64 wheel verification first |
| smoke | ONNX Runtime GPU = CUDA = x86 only |
| fe-build | Next.js `.next` output potentially arch-specific; keep x64 for parity with docker-frontend |
| docker-backend / docker-frontend | Building x86 container images for VPS deployment |
| changes | `ubuntu-latest` — lightweight, no Blacksmith needed |

**Savings:** On a typical PR (~65s wall, ~160 runner-seconds across ~5 ARM-eligible jobs):
- x64 cost: ~106s × $0.004/60 = $0.007
- ARM cost: ~106s × $0.0025/60 = $0.004
- Per-PR savings: ~$0.003 (~43% cheaper on these jobs)
- Free tier leverage: 3000 ARM min ≈ 4800 x64-min equivalent

**Prerequisite:** Verify `uv sync` succeeds on ARM by running a one-off test workflow with `blacksmith-2vcpu-ubuntu-2404-arm` before merging. If any dep lacks aarch64 wheels, keep that job on x64.

### 9. pytest-split for test sharding

**Files:** `.github/workflows/ci-reusable.yml`, `pyproject.toml`

Split the test suite across 2 matrix jobs using `pytest-split`. Each shard runs ~50% of tests by execution time, reducing wall time for the test job.

**How it works:** pytest-split reads a `.test_durations` file (committed to repo) that maps each test to its average runtime. It then splits tests into N groups of roughly equal total duration. New tests without timing data get average duration assigned.

**pyproject.toml addition:**

```toml
[project.optional-dependencies]
dev = [
    # ... existing ...
    "pytest-split>=0.10",
]
```

**Workflow change:**

```yaml
test:
  name: Tests (${{ matrix.group }}/${{ strategy.job-total }})
  needs: [changes]
  if: ${{ inputs.run-all || needs.changes.outputs.python == 'true' }}
  runs-on: blacksmith-4vcpu-ubuntu-2404
  timeout-minutes: 15
  strategy:
    fail-fast: false
    matrix:
      group: [1, 2]
  steps:
    - uses: actions/checkout@v6
    - uses: ./.github/actions/setup-python-venv
      with:
        python-version: ${{ inputs.python-version }}
    - name: pytest
      run: >
        uv run pytest backend/tests/
        ml/tests/test_device.py ml/tests/test_types.py ml/tests/test_gap_filling.py
        ml/tests/test_worker_metrics.py ml/tests/test_tracked_extraction.py
        ml/tests/test_projection.py ml/tests/test_pipeline_parallel.py
        ml/tests/alignment/ ml/tests/analysis/
        ml/tests/utils/ ml/tests/references/ ml/tests/pose_3d/ ml/tests/pose_estimation/ ml/tests/datasets/
        --splits 2 --group ${{ matrix.group }}
        -n auto --dist loadfile
        -v -m "not slow and not integration"
        --cov=backend/app --cov=ml/src
        --cov-report= --junitxml=junit.xml --tb=short
        --durations-file=.test_durations
    - name: Upload coverage data
      if: always()
      uses: actions/upload-artifact@v7
      with:
        name: coverage-group-${{ matrix.group }}
        path: .coverage
    - name: Upload test results
      if: ${{ !cancelled() }}
      uses: actions/upload-artifact@v7
      with:
        name: test-results-group-${{ matrix.group }}
        path: junit.xml

coverage:
  name: Coverage combine
  needs: [test]
  if: always()
  runs-on: blacksmith-2vcpu-ubuntu-2404-arm
  timeout-minutes: 5
  steps:
    - uses: actions/checkout@v6
    - uses: ./.github/actions/setup-python-venv
      with:
        python-version: ${{ inputs.python-version }}
    - uses: actions/download-artifact@v5
      with:
        pattern: coverage-group-*
        path: .coverage-artifacts
        merge-multiple: true
    - name: Combine coverage
      run: |
        coverage combine .coverage-artifacts/.coverage*
        coverage xml -o coverage.xml
        coverage report --fail-under=0
    - uses: codecov/codecov-action@v6
      with:
        files: coverage.xml
        flags: backend,ml
        name: python-coverage
        token: ${{ secrets.CODECOV_TOKEN }}
    - uses: actions/download-artifact@v5
      with:
        pattern: test-results-group-*
        path: test-results-artifacts
        merge-multiple: true
    - uses: codecov/test-results-action@v1
      with:
        token: ${{ secrets.CODECOV_TOKEN }}
        files: test-results-artifacts/junit.xml
```

**Note on coverage:** Each shard uses `--cov-report=` (no XML output, only `.coverage` binary). The `coverage` job combines `.coverage` files with `coverage combine`, then produces `coverage.xml` for Codecov. This is the correct Coverage.py workflow for merging sharded coverage.

**Note on xdist + pytest-split:** `--dist loadfile` groups tests by file within each shard. This is fine — pytest-split assigns tests to shards based on duration, then xdist distributes each shard's tests across CPU cores by file. No conflict.

**Bootstrapping timing data:** First run without `--splits` to generate `.test_durations`:

```bash
uv run pytest backend/tests/ ml/tests/ --store-durations
```

Commit `.test_durations` to repo root. Subsequent runs use it for balanced splits. After significant test additions, regenerate:

```bash
uv run pytest backend/tests/ ml/tests/ --store-durations
git commit .test_durations -m "chore(ci): update test durations"
```

**Savings:** Test job currently ~60s (35s pytest). With 2 shards on 4vCPU runners: ~20-25s wall time per shard. Critical path reduction: 35-40s → ~25s (shard finishes when slowest shard completes).

**Trade-offs:**
- 2 runners instead of 1 for test → +1 runner-minute, but wall time -10-15s on critical path
- `.test_durations` file needs periodic refresh (monthly or after major test additions)
- `fail-fast: false` ensures all shards report failures, not just the first

### 10. Artifact pass-through fe-build → docker-frontend

**File:** `.github/workflows/ci-reusable.yml`, `frontend/Containerfile`

Currently `docker-frontend` rebuilds `bun install` + `next build` from scratch (~24s fe-build + ~34s docker build = ~58s total). If fe-build uploads `.next/` + `node_modules/` as an artifact, docker-frontend can skip both steps.

**Problem:** The current `frontend/Containerfile` uses a multi-stage build where the production stage `COPY --from=builder` copies `.next/standalone`, `.next/static`, and `public` from the builder stage. If we skip `bun install && bun run build` in the builder, there's nothing to copy. The `SKIP_BUILD` approach with a build arg doesn't work because:

1. `COPY --from=builder` expects artifacts in the builder stage
2. The pre-built `.next/` is on the host (from artifact download), not in the builder stage
3. `bun install` is still needed for standalone tracing even if `bun run build` is skipped

**Solution:** Create a separate `frontend/Containerfile.ci` that skips the builder stage entirely and copies pre-built artifacts from the host context directly into the production image:

```dockerfile
# syntax=docker/dockerfile:1.7
# Containerfile.ci — CI-only build using pre-built artifacts from fe-build
FROM docker.io/library/node:22-alpine3.21

RUN apk add --no-cache libc6-compat

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

RUN addgroup --system --gid 1001 nextjs \
    && adduser --system --uid 1001 --ingroup nextjs --shell /usr/sbin/nologin nextjs

# Pre-built artifacts from fe-build job (downloaded via artifact)
COPY --chown=nextjs:nextjs public ./public
COPY --chown=nextjs:nextjs .next/standalone ./
COPY --chown=nextjs:nextjs .next/static ./.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
```

**Workflow change:**

```yaml
# In fe-build job (add after bundle analyzer upload):
- name: Upload build output for Docker
  if: always()
  uses: actions/upload-artifact@v7
  with:
    name: frontend-build-output
    path: |
      frontend/public
      frontend/.next/standalone
      frontend/.next/static
    retention-days: 1

# In docker-frontend job:
steps:
  - uses: actions/checkout@v6
  - name: Download build output
    uses: actions/download-artifact@v5
    with:
      name: frontend-build-output
      path: frontend
  - name: Setup Blacksmith Builder
    uses: useblacksmith/setup-docker-builder@v1
    with:
      max-cache-size-mb: "10240"  # 10GB cap
  - name: Build frontend image
    uses: useblacksmith/build-push-action@v2
    with:
      context: frontend
      file: frontend/Containerfile.ci
      push: false
      tags: skatelab-frontend:ci
```

**Why a separate Containerfile:** The original `Containerfile` remains for local `podman build` and production deploys. `Containerfile.ci` is a lean single-stage build that only copies pre-built artifacts — no bun install, no next build. This is the standard pattern for CI artifact pass-through with multi-stage builds.

**Savings on master:** docker-frontend drops from ~34s to ~8-12s (no bun install, no next build, only Docker COPY + HEALTHCHECK). Wall time reduction: ~22s on master path.

**Trade-offs:**
- Two Containerfiles to maintain — `Containerfile.ci` is simple (single stage, no build steps) and rarely changes
- Artifact size: `frontend/public/` + `frontend/.next/standalone/` + `frontend/.next/static/` ≈ 30-50MB (much smaller than including `node_modules`)
- Only works on `run-all: true` (master) since docker-frontend skips on PRs
- Must ensure fe-build produces standalone output (already configured via `output: 'standalone'` in next.config)

## ci-passed Updates

Update `needs` and env vars to reflect merged/removed jobs:

```yaml
ci-passed:
  needs: [changes, lint-typecheck, design-ci, test, coverage, smoke, fe-check, fe-build, fe-test, docker-backend, docker-frontend, danger]
  if: always()
  steps:
    - env:
        LINT_TYPECHECK: ${{ needs.lint-typecheck.result }}
        COVERAGE: ${{ needs.coverage.result }}
        # removed: TYPECHECK, AST_GREP
```

Update summary table accordingly.

## Before/After Summary

| Metric | Before (PR) | After (PR) | Delta |
|--------|-------------|------------|-------|
| Wall time | 135s | ~50s | **-63%** |
| Runner-seconds | ~290s | ~175s | **-40%** |
| Python jobs | 5 | 4 (2 shards + lint-typecheck + smoke) | -1 |
| Total jobs | 13 | 11 (9 + 2 test shards) | -2 |
| Setup overhead (Python) | 5×18s = 90s | 4×3s = 12s (sticky disk) | **-87%** |
| ARM-eligible jobs | 0 | 7 (6 + coverage) | -37.5% per-minute cost |

| Metric | Before (master) | After (master) | Delta |
|--------|-----------------|----------------|-------|
| Wall time | 135s | ~65s | **-52%** |
| Runner-seconds | ~290s | ~235s | **-19%** |
| docker-frontend | ~34s | ~10s | **-71%** (Containerfile.ci) |

## Files Modified

1. `.github/workflows/ci-reusable.yml` — merge lint+typecheck, remove ast-grep, gate smoke behind `run-all`, keep Docker for Containerfile PRs, add timeout-minutes, add `max-cache-size-mb` to setup-docker-builder, ARM runners for safe jobs, pytest-split matrix, artifact pass-through fe-build→docker-frontend, remove ast-grep from design-ci, update ci-passed
2. `.github/actions/setup-python-venv/action.yml` — replace `actions/cache@v4` with sticky disk for `.venv`, remove verify step
3. `lefthook.yml` — add design-lint to pre-push
4. `pyproject.toml` — add `pytest-split` dev dependency
5. `.test_durations` — bootstrap test timing data (committed)
6. `frontend/Containerfile.ci` — new CI-only single-stage Containerfile for artifact pass-through

## Future Optimizations (Not in Scope)

These ideas were researched by agents but deferred — they add complexity disproportionate to current CI scale:

- **workflow_run for progressive CI**: Decouple slow checks (Docker, smoke) from merge gate via `workflow_run` trigger. Useful when CI becomes merge bottleneck.
- **ARM for test job**: 4vCPU ARM runner for pytest — needs aarch64 wheel verification for numpy, onnxruntime, numba, scipy.
- **Dependency-aware change detection**: Custom script detecting cross-component imports (e.g., backend importing ml types). Current `paths-filter` misses these. ~100 lines Python. Revisit when cross-component bugs from CI misses become frequent.
- **Sticky disks for node_modules**: `useblacksmith/stickydisk@v1` for `frontend/node_modules` (~200MB). Currently `setup-frontend` handles this; sticky disk would save ~5s per frontend job.

## Blacksmith-Specific Notes

- **Colocated cache**: `actions/cache@v4` + `setup-uv` cache automatically use Blacksmith's 4x faster NVMe cache. No code changes.
- **Docker layer caching**: Already configured with `setup-docker-builder@v1`. Adding `max-cache-size-mb` to cap cache growth.
- **Sticky disks**: Replacing `actions/cache@v4` for `.venv`. 3s mount vs 15s cache download. Cost: ~$0.25/mo for 500MB.
- **Free tier**: 3000 x64-2vCPU min/month, 25GB cache/repo/week. Our CI usage is well within limits.