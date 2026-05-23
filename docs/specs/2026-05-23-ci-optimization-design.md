# CI Optimization Design

> **Goal:** Reduce CI wall time from ~2.2 min to ~1 min on PRs, cut runner-minutes from ~5 to ~2.5 per run, move design lint to lefthook for fail-fast locally.

**Architecture:** Merge Python lint+typecheck into single job, remove ast-grep from CI (exists in lefthook), skip docker+smoke on PRs (master only), eliminate uv sync on cache hit, add design lint to lefthook pre-push, shallow checkout where possible.

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
changes (5s) ─┬─ lint+typecheck+alembic (40s)  ← 1 setup, ruff+basedpyright+alembic
               ├─ design-ci (21s)
               ├─ test (60s)                    ← no smoke/docker after
               ├─ fe-check (22s) ── fe-build (24s)
               └─ fe-test (18s)

Wall time: ~65s (1.1 min)
Total runner-seconds: ~160s
```

### On push to master (run-all: true)

```
changes (5s) ─┬─ lint+typecheck+alembic (40s)
               ├─ design-ci (21s)
               ├─ test (60s) ──── smoke (31s)
               │             ──── docker-backend (26s)
               ├─ fe-check (22s) ── fe-build (24s) ── docker-frontend (34s)
               └─ fe-test (18s)

Wall time: ~100s (1.7 min)
```

## Changes

### 1. Merge lint+typecheck → single job

**File:** `.github/workflows/ci-reusable.yml`

Merge `lint` and `typecheck` jobs into `lint-typecheck`:

```yaml
lint-typecheck:
  name: Lint + Type Check
  needs: [changes]
  if: inputs.run-all || needs.changes.outputs.python == 'true'
  runs-on: blacksmith-2vcpu-ubuntu-2404
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

**Savings:** -7s wall time, -1 runner, -1 job in ci-passed `needs`.

### 3. Skip docker+smoke on PR

**File:** `.github/workflows/ci-reusable.yml`

Use `inputs.run-all` (already exists, true on push to master) to gate docker and smoke jobs. No new input needed — `run-all` is already `true` when `github.event_name == 'push'`:

```yaml
# ci.yml — no changes needed, run-all already set:
jobs:
  ci:
    uses: ./.github/workflows/ci-reusable.yml
    with:
      python-version: "3.11"
      run-all: ${{ github.event_name == 'push' }}
```

Smoke and docker jobs — require `run-all: true` (push to master), not just path filter:

```yaml
smoke:
  needs: [changes, test]
  if: inputs.run-all && needs.changes.outputs.ml == 'true'
  # ...

docker-backend:
  needs: [changes, test]
  if: ${{ !inputs.skip-docker && inputs.run-all && needs.changes.outputs.docker == 'true' }}
  # ...

docker-frontend:
  needs: [changes, fe-check, fe-build]
  if: ${{ !inputs.skip-docker && inputs.run-all && needs.changes.outputs.docker == 'true' }}
  # ...
```

**Savings on PR:** -2 runners, -60s runner-seconds. Smoke (31s) + docker-backend (26s) + docker-frontend (34s) skipped.

**Risk:** Docker build issue not caught until merge. Low risk — Dockerfiles rarely change independently of code that triggers other CI jobs.

### 4. Skip uv sync on cache hit

**File:** `.github/actions/setup-python-venv/action.yml`

Add `cache-hit` output. Skip verify step on hit:

```yaml
outputs:
  cache-hit:
    description: "Whether venv was restored from cache"
    value: ${{ steps.venv-cache.outputs.cache-hit }}

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
```

Remove the `Verify venv` step entirely. On cache hit, rely on `uv sync` being idempotent — if a package is missing, the subsequent `uv run ruff` / `uv run pytest` will fail with a clear `ModuleNotFoundError`.

**Savings:** -8-10s per Python job that hits cache. With 3 Python jobs (lint-typecheck, test, smoke), saves ~18-30s total runner time.

**Risk:** Stale cache after lockfile change. Mitigated by cache key including `hashFiles('uv.lock')` — lockfile change = cache miss = full sync.

### 5. Design lint in lefthook pre-push

**File:** `lefthook.yml`

Add design-ci job to `pre-push` hook:

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
        if [ -f ../node_modules/.bin/impeccable ] || command -v impeccable &> /dev/null; then
          impeccable detect --json src/ 2>&1 | node ../scripts/impeccable-report.js || true
        fi
        if command -v sg &> /dev/null; then
          sg scan -c ../sgconfig.yml frontend/ || true
        fi
        node ../scripts/design-lock.js check || exit 1
      # exit 1 only on drift — lint violations are warnings
```

**Effect:** Design drift caught locally before push, not after 21s CI wait. CI `design-ci` job remains as blocking gate.

**Note:** `impeccable` and `ast-grep` (sg) are optional — `|| true` for detect step, `|| exit 1` only for drift check which is the blocking concern.

### 6. Shallow checkout for lint-typecheck

**File:** `.github/workflows/ci-reusable.yml`

Add `fetch-depth: 1` to checkout in lint-typecheck and fe-check jobs (no git history needed):

```yaml
- uses: actions/checkout@v6
  with:
    fetch-depth: 1
```

Already present on fe-check. Apply to lint-typecheck too.

**Savings:** -2-3s per job on checkout step.

### 7. Blacksmith Docker layer caching

**File:** `.github/workflows/ci-reusable.yml`

Currently docker jobs use `useblacksmith/build-push-action@v2` but **without** `useblacksmith/setup-docker-builder@v1`. Per Blacksmith docs, without setup-docker-builder the runner uses the default builder — no NVMe layer cache, no Docker analytics. Adding setup-docker-builder hydrates cached layers from previous runs, only rebuilding changed layers.

```yaml
docker-backend:
  name: Docker Build (Backend)
  needs: [changes, test]
  if: ${{ !inputs.skip-docker && inputs.run-all && needs.changes.outputs.docker == 'true' }}
  runs-on: blacksmith-4vcpu-ubuntu-2404
  steps:
    - uses: actions/checkout@v6
    - name: Setup Blacksmith Builder
      uses: useblacksmith/setup-docker-builder@v1
    - name: Build backend image
      uses: useblacksmith/build-push-action@v2
      with:
        context: .
        file: backend/Containerfile
        push: false
        tags: skatelab-backend:ci

docker-frontend:
  name: Docker Build (Frontend)
  needs: [changes, fe-check, fe-build]
  if: ${{ !inputs.skip-docker && inputs.run-all && needs.changes.outputs.docker == 'true' }}
  runs-on: blacksmith-4vcpu-ubuntu-2404
  steps:
    - uses: actions/checkout@v6
    - name: Setup Blacksmith Builder
      uses: useblacksmith/setup-docker-builder@v1
    - name: Build frontend image
      uses: useblacksmith/build-push-action@v2
      with:
        context: frontend
        file: frontend/Containerfile
        push: false
        tags: skatelab-frontend:ci
```

**Savings on master:** First run = uncached (same as now). Subsequent runs: 2x-40x faster Docker builds (per Blacksmith customer reports). If Dockerfile hasn't changed, most layers cached → near-instant rebuild.

**Note:** Docker layer cache is scoped per-repo, shared across all runners (Last Write Wins). No cross-branch cache leakage — Blacksmith caches are branch-scoped by default.

### 8. Leverage Blacksmith colocated cache (no action needed)

Blacksmith automatically redirects `actions/cache@v4` and `setup-*` action caches to their colocated NVMe backend (4x faster than GitHub's Azure Blob Storage). Our setup-python-venv already uses `actions/cache@v4` and `astral-sh/setup-uv@v7` with `enable-cache: true` — both automatically benefit from Blacksmith's colocated cache. No code changes required.

**Free tier:** 25GB per repo per week (vs GitHub's 10GB). No additional cost.

## ci-passed Updates

Update `needs` and env vars to reflect merged/removed jobs:

```yaml
ci-passed:
  needs: [changes, lint-typecheck, design-ci, test, smoke, fe-check, fe-build, fe-test, docker-backend, docker-frontend, danger]
  if: always()
  steps:
    - env:
        LINT_TYPECHECK: ${{ needs.lint-typecheck.result }}
        # removed: TYPECHECK, AST_GREP
```

Update summary table accordingly.

## Before/After Summary

| Metric | Before (PR) | After (PR) | Delta |
|--------|-------------|------------|-------|
| Wall time | 135s | ~65s | **-52%** |
| Runner-seconds | ~290s | ~160s | **-45%** |
| Python jobs | 5 | 3 | -2 |
| Total jobs | 13 | 9 | -4 |
| Setup overhead (Python) | 5×18s = 90s | 3×10s = 30s | **-67%** |

| Metric | Before (master) | After (master) | Delta |
|--------|-----------------|----------------|-------|
| Wall time | 135s | ~100s | **-26%** |
| Runner-seconds | ~290s | ~220s | **-24%** |

## Files Modified

1. `.github/workflows/ci-reusable.yml` — merge lint+typecheck, remove ast-grep, gate docker/smoke behind `run-all`, add `setup-docker-builder`, shallow checkout, update ci-passed
2. `.github/actions/setup-python-venv/action.yml` — add cache-hit output, skip uv sync on cache hit
3. `lefthook.yml` — add design-lint to pre-push

## Blacksmith-Specific Notes

- **Colocated cache**: `actions/cache@v4` + `setup-uv` cache automatically use Blacksmith's 4x faster NVMe cache. No code changes.
- **Docker layer caching**: Requires `useblacksmith/setup-docker-builder@v1` before `useblacksmith/build-push-action@v2`. Currently missing.
- **Sticky disks**: Considered for `.venv` (500MB+) but overkill — `actions/cache` with Blacksmith backend is sufficient and simpler.
- **Free tier**: 3000 x64-2vCPU min/month, 25GB cache/repo/week. Our CI usage is well within limits.
