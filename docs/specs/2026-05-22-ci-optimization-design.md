# CI Pipeline Optimization Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce CI wall time from ~5 min to ~2 min through parallelism, caching, and dependency graph optimization.

**Architecture:** Remove unnecessary job serialization, cache dependency installation across jobs, parallelize pytest via xdist, merge lightweight jobs, and optimize the design system CI path.

**Tech Stack:** GitHub Actions (ci-reusable.yml, deploy.yml), uv + setup-uv v7, pytest-xdist, actions/cache, Blacksmith runners

---

## Current State

### Timing (master branch, 2026-05-22)

```
changes (6s)
├── lint/ruff (37s) ───────────┐
├── typecheck (37s)            │
├── alembic (38s)              │
├── ast-grep (7s)              ├── test (174s) ← BOTTLENECK ──→ smoke (35s)
├── design-lint (25s)          │                              ──→ docker-backend (23s)
├── design-check (11s)         │
├── fe-lint/Biome (10s) ───────┼── fe-test (16s)
│                              └── fe-typecheck (15s) ──→ fe-build (23s) ──→ docker-frontend (40s)
└────────────────────────────────────────────────────────────────────────────────────→ ci-passed (3s)

Wall time: ~292s (~5 min)
Critical path: changes(6s) → lint(37s) → test(174s) → docker-backend(23s) = 240s
```

### Problems Identified

1. **test → lint dependency is artificial** — lint failures don't affect test correctness. Gate at ci-passed instead.
2. **uv sync runs 5x** — each Python job reinstalls deps (~25s each, ~125s total wasted)
3. **bun install runs 6x** — each frontend/design job reinstalls node_modules (~5-8s each)
4. **pytest runs sequentially** — 1662 tests on 2vCPU runner, no parallelism
5. **alembic is a separate job** — 38s job for a 2s command, wastes uv sync
6. **fe-lint + fe-typecheck are separate** — two 10-15s jobs that share identical setup
7. **design-lint + design-check are separate** — two short jobs with duplicate bun install
8. **docker-backend waits for test** — build validation doesn't need functional tests
9. **fe-test waits for fe-lint** — vitest doesn't depend on biome
10. **Design path filter too broad** — ast-grep/*.yml and Taskfile.yml trigger design CI unnecessarily

---

## Proposed Changes

### Wave 1: Remove artificial dependencies (LOW effort, HIGH impact)

**P0: Remove `lint` from `test` needs** (-37s critical path)

```yaml
# BEFORE
test:
  needs: [changes, lint]

# AFTER
test:
  needs: [changes]
```

ci-passed still gates on lint result. Branch protection rules enforce lint pass before merge.

**P1: Remove `fe-lint` from `fe-test` needs** (-10s frontend path)

```yaml
# BEFORE
fe-test:
  needs: [changes, fe-lint]

# AFTER
fe-test:
  needs: [changes]
```

**P2: Remove `lint` + `typecheck` from `docker-backend` needs**

```yaml
# BEFORE
docker-backend:
  needs: [changes, lint, typecheck, test]

# AFTER
docker-backend:
  needs: [changes, test]
```

Docker build is a compilation check, not a functional test. Test still gates it.

**P3: Remove `fe-lint` + `fe-typecheck` from `fe-build` needs**

```yaml
# BEFORE
fe-build:
  needs: [changes, fe-lint, fe-typecheck]

# AFTER
fe-build:
  needs: [changes]
```

Build and lint are independent. Gate at ci-passed.

### Wave 2: Cache dependency installation (MEDIUM effort, HIGH impact)

**C1: Create `.github/actions/setup-python-venv/action.yml`** composite action

Caches `.venv` directory keyed on `uv.lock` hash + Python version. On cache hit, `uv sync` becomes a verification-only step (~3-5s vs ~25s).

```yaml
name: 'Setup Python + uv with venv cache'
description: 'Install Python, uv, sync deps with .venv caching'
inputs:
  python-version:
    required: false
    default: '3.11'
runs:
  using: 'composite'
  steps:
    - uses: astral-sh/setup-uv@v7
      with:
        enable-cache: true
        cache-python: true
    - uses: actions/setup-python@v6
      with:
        python-version: ${{ inputs.python-version }}
    - name: Cache venv
      id: venv-cache
      uses: actions/cache@v4
      with:
        path: .venv
        key: venv-${{ runner.os }}-py${{ inputs.python-version }}-${{ hashFiles('uv.lock') }}
        restore-keys: |
          venv-${{ runner.os }}-py${{ inputs.python-version }}-
    - name: Sync deps
      if: steps.venv-cache.outputs.cache-hit != 'true'
      run: uv sync --all-packages --frozen --dev
      shell: bash
    - name: Verify venv
      if: steps.venv-cache.outputs.cache-hit == 'true'
      run: uv sync --all-packages --frozen --dev
      shell: bash
```

Saves ~20s per Python job × 5 jobs = ~100s total. Requires `actions/checkout@v6` before this action.

**C2: Create `.github/actions/setup-frontend/action.yml`** composite action

Caches `node_modules` keyed on `bun.lock` hash + Bun global cache.

```yaml
name: 'Setup Frontend Dependencies'
description: 'Install Bun + cache/restore frontend node_modules'
inputs:
  working-directory:
    required: false
    default: 'frontend'
runs:
  using: 'composite'
  steps:
    - uses: oven-sh/setup-bun@v2
    - name: Cache bun global cache
      uses: actions/cache@v4
      with:
        path: ~/.bun/install/cache
        key: fe-bun-global-${{ runner.os }}-${{ hashFiles(format('{0}/bun.lock', inputs.working-directory)) }}
        restore-keys: |
          fe-bun-global-${{ runner.os }}-
    - name: Cache node_modules
      id: cache-nm
      uses: actions/cache@v4
      with:
        path: ${{ inputs.working-directory }}/node_modules
        key: fe-node-modules-${{ runner.os }}-${{ hashFiles(format('{0}/bun.lock', inputs.working-directory)) }}
        restore-keys: |
          fe-node-modules-${{ runner.os }}-
    - name: Install deps
      if: steps.cache-nm.outputs.cache-hit != 'true'
      working-directory: ${{ inputs.working-directory }}
      shell: bash
      run: bun install --frozen-lockfile
```

Saves ~5s per frontend job × 4 remaining jobs (after merges) = ~20s.

### Wave 3: Merge lightweight jobs (LOW effort, MEDIUM impact)

**M1: Merge `alembic` into `lint`**

Alembic check is a 2s command paying 38s of job overhead + uv sync. Merge into lint:

```yaml
lint:
  name: Lint (ruff) + Alembic
  needs: [changes]
  if: inputs.run-all || needs.changes.outputs.python == 'true'
  runs-on: blacksmith-2vcpu-ubuntu-2404
  steps:
    - uses: actions/checkout@v6
    - uses: ./.github/actions/setup-python-venv
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
```

Eliminates 1 job (~35-40s overhead). Remove `alembic` from ci-passed needs.

**M2: Merge `fe-lint` + `fe-typecheck` → `fe-check`**

Both are fast checks (10s + 15s) sharing identical setup. Merge:

```yaml
fe-check:
  name: Check (Biome + tsc)
  needs: [changes]
  if: inputs.run-all || needs.changes.outputs.frontend == 'true'
  runs-on: blacksmith-2vcpu-ubuntu-2404
  steps:
    - uses: actions/checkout@v6
    - uses: ./.github/actions/setup-frontend
    - name: Biome check
      working-directory: frontend
      run: bunx biome check .
    - name: tsc
      working-directory: frontend
      run: bun run typecheck
```

Update fe-build needs: `[changes, fe-check]`. Update docker-frontend needs: `[changes, fe-check, fe-build]`. Eliminates 1 job (~8-12s overhead).

**M3: Merge `design-lint` + `design-check` → `design-ci`**

Both share identical setup and trigger on same path filter:

```yaml
design-ci:
  name: Design Lint + Drift
  needs: [changes]
  if: inputs.run-all || needs.changes.outputs.design == 'true'
  runs-on: blacksmith-2vcpu-ubuntu-2404
  steps:
    - uses: actions/checkout@v6
    - uses: ./.github/actions/setup-frontend
    - name: Install impeccable
      run: npm install -g impeccable
    - name: Impeccable detect
      run: impeccable detect --json frontend/src/ 2>&1 | node scripts/impeccable-report.js
    - name: Ast-grep scan
      uses: ast-grep/action@v1.5.0
      with:
        config: sgconfig.yml
        paths: "frontend/"
    - name: Check for drift
      run: node scripts/design-lock.js check
```

Eliminates 1 job (~8-10s overhead).

### Wave 4: Parallelize pytest (MEDIUM effort, HIGH impact)

**T1: Add `pytest-xdist` and move test to 4vCPU runner**

```toml
# pyproject.toml dev deps
"pytest-xdist>=3.6.0"
```

```yaml
test:
  name: Tests
  needs: [changes]
  if: inputs.run-all || needs.changes.outputs.python == 'true'
  runs-on: blacksmith-4vcpu-ubuntu-2404  # Was 2vCPU
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
        ml/tests/utils/test_gap_filling.py ml/tests/utils/test_geometry.py
        ml/tests/utils/test_geometry_numba.py ml/tests/utils/test_profiler.py
        ml/tests/utils/test_profiling.py ml/tests/utils/test_smoothing.py
        ml/tests/utils/test_smoothing_numba.py ml/tests/utils/test_video_writer_nvenc.py
        ml/tests/references/ ml/tests/pose_3d/ ml/tests/pose_estimation/ ml/tests/datasets/
        -n auto --dist worksteal
        -v -m "not slow and not integration"
        --cov=backend/app --cov=ml/src
        --cov-report=xml --junitxml=junit.xml --tb=short
```

Estimated: 174s → ~50-60s on 4 cores. **~110s saved.**

**Prerequisite:** Run `uv run pytest -n auto --dist worksteal` locally to verify all tests are xdist-safe.

### Wave 5: Design system optimizations (LOW effort, MEDIUM impact)

**D1: Narrow design path filter**

Remove `ast-grep/*.yml` and `Taskfile.yml` from design filter — they're general tools, not design-specific:

```yaml
design:
  - "DESIGN.md"
  - "scripts/design-*.js"
  - "tokens/lock.json"
  - "frontend/src/app/tokens.css"
  - "frontend/src/app/globals.css"
  - "mobile/androidApp/**/theme/**"
  - "mobile/iosApp/**/Theme/**"
```

**D2: Long-term: deterministic transform layer**

The LLM pipeline (design-build.js) is innovative but inherently non-deterministic. Long-term, split into:
1. **Authoring phase** (LLM): Help designers write/validate DESIGN.md YAML — local, not CI
2. **Transform phase** (deterministic): Parse YAML → generate CSS/Kotlin/Swift via templates — CI-safe, <1s

The DESIGN.md YAML frontmatter is structured enough for programmatic parsing. Cobalt, Handlebars, or a custom Node transformer could handle 80%+ of token generation deterministically. LLM handles the 20% long-tail (Kotlin Compose wiring, SwiftUI annotations).

### Wave 6: Deploy pipeline optimization (LOW effort, MEDIUM impact)

**E1: Add registry cache to deploy.yml Docker builds**

```yaml
# deploy.yml — both build steps
cache-from: type=registry,ref=ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-frontend:latest
cache-to: type=inline
```

Reuse previously pushed layers. Saves 50-70% on deploy Docker build time.

---

## Updated Dependency Graph (After All Changes)

```
changes (6s)
├── lint+alembic (37s) ──────────┐
├── typecheck (37s)              │
├── ast-grep (7s)                 │
├── design-ci (25s)               │
├── fe-check (25s) ──→ fe-build (23s) ──→ docker-frontend (40s)
├── fe-test (16s)                 │
└── test (~55s, xdist) ───────────┴──→ smoke (35s)
                                      ──→ docker-backend (23s)
                                                               ──→ ci-passed (3s)

Estimated critical path: changes(6s) → test(55s) → docker-backend(23s) = 84s
Total wall time: ~110-120s (~2 min)
```

**Improvement: 292s → ~115s = ~60% reduction**

---

## Updated ci-passed needs

```yaml
ci-passed:
  needs: [changes, lint, typecheck, ast-grep, design-ci, test, smoke, fe-check, fe-build, fe-test, docker-backend, docker-frontend]
```

Merged away: `alembic` (→ lint), `fe-lint` + `fe-typecheck` (→ fe-check), `design-lint` + `design-check` (→ design-ci).

---

## Implementation Priority Matrix

| Wave | Change | Effort | Critical Path Savings | Total Savings | Risk |
|------|--------|--------|-----------------------|---------------|------|
| **1** | Remove test→lint dep | 1 line | -37s | -37s | Low (ci-passed gates) |
| **1** | Remove fe-test→fe-lint dep | 1 line | 0s (not on crit path) | -10s | Low |
| **1** | Remove docker-backend→lint+typecheck | 2 lines | 0s | -37s (earlier start) | Low |
| **1** | Remove fe-build→fe-lint+fe-typecheck | 1 line | 0s | -15s | Low |
| **2** | setup-python-venv composite action | New file + 5 refs | -20s | -100s | Low |
| **2** | setup-frontend composite action | New file + 4 refs | 0s | -20s | Low |
| **3** | Merge alembic→lint | 10 lines | 0s (not on crit path) | -35s | Low |
| **3** | Merge fe-lint+fe-typecheck→fe-check | 15 lines | 0s | -12s | Low |
| **3** | Merge design-lint+design-check→design-ci | 15 lines | 0s | -10s | Low |
| **4** | pytest-xdist + 4vCPU runner | Dep + 3 lines | **-119s** | -119s | Medium (xdist compat) |
| **5** | Narrow design path filter | 5 lines | 0s | Fewer false triggers | None |
| **6** | Deploy registry cache | 4 lines | 0s (deploy only) | -60-120s deploy | Low |

**Wave 1+4 alone** (remove test→lint + xdist): critical path 240s → 84s = **65% reduction**.

---

## Risks

1. **pytest-xdist compatibility**: Some async fixtures or shared-state tests may fail. Mitigation: run locally first with `-n auto --dist worksteal`. Fallback: `-n 2` (conservative parallelism).

2. **.venv cache invalidation**: When `uv.lock` changes, all jobs get cache miss → full install. This is correct behavior. Cache key includes lock hash + Python version.

3. **GHA cache size**: .venv is ~1-2GB, node_modules ~1.3GB. Total ~3GB per branch. GHA limit is 10GB/repo — safe for several branches.

4. **Job merges reduce parallelism visibility**: If Biome fails inside fe-check, tsc still runs but the whole job fails. The ci-passed summary table still shows individual job results. Trade-off: simpler graph vs granular failure reporting.

5. **Removing dependencies from docker jobs**: docker-backend no longer waits for lint/typecheck. If code has type errors, docker build may succeed but code is broken. Mitigation: ci-passed still requires all jobs, branch protection requires ci-passed.

---

## What We're NOT Doing

- **Cache-warmup job**: Adds serialization. Not worth it since venv cache already handles this.
- **Vitest sharding**: 16s test suite — sharding overhead exceeds benefit. Threshold: >60s.
- **Next.js build cache**: 23s build — cache overhead doesn't justify. Threshold: >40s.
- **pytest-split (matrix)**: Multiple jobs × uv sync overhead. pytest-xdist within single job is better for this suite size.
- **LLM response caching in CI**: design-build.js doesn't run in CI (only lint + drift check). Cache would only help local runs.
