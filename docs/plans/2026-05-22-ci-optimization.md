# CI Pipeline Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce CI wall time from ~5 min to ~2 min by removing artificial job dependencies, caching dependency installations, merging lightweight jobs, parallelizing pytest, and optimizing design CI triggers.

**Architecture:** 6 waves of changes. Wave 1 (dependency removal) and Wave 4 (pytest-xdist) have the biggest critical-path impact. Waves 2-3 (caching + merges) reduce total time. Waves 5-6 are polish.

**Tech Stack:** GitHub Actions, uv + setup-uv@v7, pytest-xdist, actions/cache@v4, Blacksmith runners, bun

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `.github/workflows/ci-reusable.yml` | Modify | Remove deps, merge jobs, update needs |
| `.github/workflows/deploy.yml` | Modify | Add Docker registry cache |
| `.github/actions/setup-python-venv/action.yml` | Create | Composite action: Python + uv + .venv cache |
| `.github/actions/setup-frontend/action.yml` | Create | Composite action: Bun + node_modules cache |
| `pyproject.toml` | Modify | Add pytest-xdist dev dep |

---

## Wave 1: Remove Artificial Dependencies

These are one-line YAML edits. Each is independently verifiable.

### Task 1: Remove `lint` from `test` needs

**Files:**

- Modify: `.github/workflows/ci-reusable.yml:181`

- [ ] **Step 1: Edit test job needs**

Change line 181 in `.github/workflows/ci-reusable.yml`:

```yaml
# BEFORE
  test:
    name: Tests
    needs: [changes, lint]

# AFTER
  test:
    name: Tests
    needs: [changes]
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: remove lint dependency from test job — gate at ci-passed instead"
```

### Task 2: Remove `fe-lint` from `fe-test` needs

**Files:**

- Modify: `.github/workflows/ci-reusable.yml:304`

- [ ] **Step 1: Edit fe-test job needs**

Change line 304:

```yaml
# BEFORE
  fe-test:
    name: Tests (Vitest)
    needs: [changes, fe-lint]

# AFTER
  fe-test:
    name: Tests (Vitest)
    needs: [changes]
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: remove fe-lint dependency from fe-test — gate at ci-passed instead"
```

### Task 3: Remove `lint` + `typecheck` from `docker-backend` needs

**Files:**

- Modify: `.github/workflows/ci-reusable.yml:333`

- [ ] **Step 1: Edit docker-backend needs**

Change line 333:

```yaml
# BEFORE
  docker-backend:
    name: Docker Build (Backend)
    needs: [changes, lint, typecheck, test]

# AFTER
  docker-backend:
    name: Docker Build (Backend)
    needs: [changes, test]
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: remove lint+typecheck deps from docker-backend — build check doesn't need them"
```

### Task 4: Remove `fe-lint` + `fe-typecheck` from `fe-build` needs

**Files:**

- Modify: `.github/workflows/ci-reusable.yml:274`

- [ ] **Step 1: Edit fe-build needs**

Change line 274:

```yaml
# BEFORE
  fe-build:
    name: Build (Next.js)
    needs: [changes, fe-lint, fe-typecheck]

# AFTER
  fe-build:
    name: Build (Next.js)
    needs: [changes]
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: remove fe-lint+fe-typecheck deps from fe-build — gate at ci-passed instead"
```

---

## Wave 2: Cache Dependency Installation

### Task 5: Create `setup-python-venv` composite action

**Files:**

- Create: `.github/actions/setup-python-venv/action.yml`

This action replaces the repeated `setup-uv → setup-python → uv sync` boilerplate in all 5 Python jobs. It caches `.venv` keyed on `uv.lock` hash, so subsequent jobs with the same lock file get instant cache hits.

- [ ] **Step 1: Create directory**

```bash
mkdir -p .github/actions/setup-python-venv
```

- [ ] **Step 2: Write composite action**

Create `.github/actions/setup-python-venv/action.yml`:

```yaml
name: 'Setup Python + uv with venv cache'
description: 'Install Python, uv, sync deps with .venv caching (run after actions/checkout)'
inputs:
  python-version:
    description: 'Python version'
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

- [ ] **Step 3: Commit**

```bash
git add .github/actions/setup-python-venv/action.yml
git commit -m "ci: add setup-python-venv composite action with .venv caching"
```

### Task 6: Replace Python job boilerplate with composite action

**Files:**

- Modify: `.github/workflows/ci-reusable.yml` (lint, typecheck, alembic, test, smoke jobs)

Replace the repeated 4-step pattern (`setup-uv → setup-python → sync → tool`) in each Python job with the composite action.

- [ ] **Step 1: Update `lint` job**

Replace lines 76-84 in `.github/workflows/ci-reusable.yml`:

```yaml
# BEFORE (lines 76-84)
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ inputs.python-version }}
      - name: Sync deps
        run: uv sync --all-packages --frozen --dev

# AFTER
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-python-venv
        with:
          python-version: ${{ inputs.python-version }}
```

- [ ] **Step 2: Update `typecheck` job**

Same replacement for lines 96-104.

- [ ] **Step 3: Update `alembic` job**

Same replacement for lines 113-121.

- [ ] **Step 4: Update `test` job**

Same replacement for lines 185-193.

- [ ] **Step 5: Update `smoke` job**

Same replacement for lines 230-238.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: replace Python job boilerplate with setup-python-venv composite action"
```

### Task 7: Create `setup-frontend` composite action

**Files:**

- Create: `.github/actions/setup-frontend/action.yml`

Caches `node_modules` + Bun global cache keyed on `bun.lock` hash.

- [ ] **Step 1: Create directory**

```bash
mkdir -p .github/actions/setup-frontend
```

- [ ] **Step 2: Write composite action**

Create `.github/actions/setup-frontend/action.yml`:

```yaml
name: 'Setup Frontend Dependencies'
description: 'Install Bun + cache/restore frontend node_modules (run after actions/checkout)'
inputs:
  working-directory:
    description: 'Working directory for bun install'
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

- [ ] **Step 3: Commit**

```bash
git add .github/actions/setup-frontend/action.yml
git commit -m "ci: add setup-frontend composite action with node_modules caching"
```

### Task 8: Replace frontend job boilerplate with composite action

**Files:**

- Modify: `.github/workflows/ci-reusable.yml` (fe-lint, fe-typecheck, fe-build, fe-test, design-lint, design-check jobs)

Replace the repeated 3-step pattern (`setup-bun → bun install → tool`) in each frontend/design job.

- [ ] **Step 1: Update `fe-lint` job**

Replace lines 248-252:

```yaml
# BEFORE
      - uses: oven-sh/setup-bun@v2
      - name: Install deps
        working-directory: frontend
        run: bun install --frozen-lockfile

# AFTER
      - uses: ./.github/actions/setup-frontend
```

- [ ] **Step 2: Update `fe-typecheck` job**

Same replacement for lines 265-268.

- [ ] **Step 3: Update `fe-build` job**

Same replacement for lines 279-282.

- [ ] **Step 4: Update `fe-test` job**

Same replacement for lines 309-312.

- [ ] **Step 5: Update `design-lint` job**

Same replacement for lines 151-154.

- [ ] **Step 6: Update `design-check` job**

Same replacement for lines 173-176.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: replace frontend job boilerplate with setup-frontend composite action"
```

---

## Wave 3: Merge Lightweight Jobs

### Task 9: Merge `alembic` into `lint`

**Files:**

- Modify: `.github/workflows/ci-reusable.yml`

Alembic check is a 2s command. Merging eliminates an entire job (~35-40s of overhead + uv sync).

- [ ] **Step 1: Add alembic step to lint job**

Add after the `Ruff check` step in the `lint` job:

```yaml
      - name: Alembic single head
        run: |
          HEADS=$(cd backend && uv run alembic heads 2>&1 | grep -c '(head)')
          if [ "$HEADS" -ne 1 ]; then
            echo "::error::Alembic has $HEADS heads (expected 1). Run 'alembic merge' or fix revision IDs."
            cd backend && uv run alembic heads 2>&1
            exit 1
          fi
```

Rename the job:

```yaml
# BEFORE
  lint:
    name: Lint (ruff)

# AFTER
  lint:
    name: Lint (ruff) + Alembic
```

- [ ] **Step 2: Delete the entire `alembic` job block**

Remove the `alembic` job (lines 108-130 in original file).

- [ ] **Step 3: Update ci-passed needs**

Remove `alembic` from the ci-passed needs list:

```yaml
# BEFORE
    needs: [changes, lint, typecheck, alembic, ast-grep, design-lint, design-check, test, smoke, fe-lint, fe-typecheck, fe-build, fe-test, docker-backend, docker-frontend]

# AFTER
    needs: [changes, lint, typecheck, ast-grep, design-lint, design-check, test, smoke, fe-lint, fe-typecheck, fe-build, fe-test, docker-backend, docker-frontend]
```

- [ ] **Step 4: Remove ALEMBIC env var from ci-passed**

Remove `ALEMBIC: ${{ needs.alembic.result }}` and the `check_job "Alembic Check" "$ALEMBIC"` line from the ci-passed script. Add the alembic check to the lint check_job display instead:

```yaml
# In the env block, remove:
          ALEMBIC: ${{ needs.alembic.result }}

# In the run script, remove:
          check_job "Alembic Check" "$ALEMBIC"

# And add after the lint check_job line:
          check_job "Lint (ruff) + Alembic" "$LINT"
```

Wait — the `LINT` env var already references `needs.lint.result` which now includes the alembic step. Just remove the separate alembic check_job line and the ALEMBIC env var. The lint check_job already covers it.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: merge alembic check into lint job — eliminate 35s job overhead"
```

### Task 10: Merge `fe-lint` + `fe-typecheck` → `fe-check`

**Files:**

- Modify: `.github/workflows/ci-reusable.yml`

- [ ] **Step 1: Replace fe-lint job with fe-check**

Replace the entire `fe-lint` job block:

```yaml
# BEFORE
  fe-lint:
    name: Lint (Biome)
    needs: [changes]
    if: inputs.run-all || needs.changes.outputs.frontend == 'true'
    runs-on: blacksmith-2vcpu-ubuntu-2404
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-frontend
      - name: Biome check
        working-directory: frontend
        run: bunx biome check .

# AFTER
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

- [ ] **Step 2: Delete the entire `fe-typecheck` job block**

Remove the fe-typecheck job.

- [ ] **Step 3: Update fe-build needs**

```yaml
# BEFORE
  fe-build:
    name: Build (Next.js)
    needs: [changes]

# AFTER (already [changes] after Task 4, add fe-check back as optional gate)
  fe-build:
    name: Build (Next.js)
    needs: [changes, fe-check]
```

Note: Task 4 removed fe-lint+fe-typecheck from fe-build needs. Now we add fe-check back so fe-build waits for the merged check to complete (it's a single fast job, ~25s).

- [ ] **Step 4: Update docker-frontend needs**

```yaml
# BEFORE
  docker-frontend:
    needs: [changes, fe-lint, fe-typecheck, fe-build]

# AFTER
  docker-frontend:
    needs: [changes, fe-check, fe-build]
```

- [ ] **Step 5: Update ci-passed needs**

Replace `fe-lint, fe-typecheck` with `fe-check`:

```yaml
# BEFORE
    needs: [..., fe-lint, fe-typecheck, fe-build, fe-test, ...]

# AFTER
    needs: [..., fe-check, fe-build, fe-test, ...]
```

- [ ] **Step 6: Update ci-passed env and script**

Replace `FE_LINT` and `FE_TYPECHECK` env vars with `FE_CHECK`:

```yaml
# In env block, replace:
          FE_LINT: ${{ needs.fe-lint.result }}
          FE_TYPECHECK: ${{ needs.fe-typecheck.result }}

# With:
          FE_CHECK: ${{ needs.fe-check.result }}

# In run script, replace:
          check_job "Lint (Biome)" "$FE_LINT"
          check_job "Type Check (tsc)" "$FE_TYPECHECK"

# With:
          check_job "Check (Biome + tsc)" "$FE_CHECK"
```

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: merge fe-lint + fe-typecheck into fe-check — eliminate job overhead"
```

### Task 11: Merge `design-lint` + `design-check` → `design-ci`

**Files:**

- Modify: `.github/workflows/ci-reusable.yml`

- [ ] **Step 1: Replace design-lint job with design-ci**

Replace the entire `design-lint` job block:

```yaml
# BEFORE
  design-lint:
    name: Design Lint
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

# AFTER
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

- [ ] **Step 2: Delete the entire `design-check` job block**

Remove the design-check job (lines 165-177 in original).

- [ ] **Step 3: Update ci-passed needs**

Replace `design-lint, design-check` with `design-ci`:

```yaml
# BEFORE
    needs: [..., ast-grep, design-lint, design-check, test, ...]

# AFTER
    needs: [..., ast-grep, design-ci, test, ...]
```

- [ ] **Step 4: Update ci-passed env and script**

Replace `DESIGN_LINT` and `DESIGN_CHECK` env vars with `DESIGN_CI`:

```yaml
# In env block, replace:
          DESIGN_LINT: ${{ needs.design-lint.result }}
          DESIGN_CHECK: ${{ needs.design-check.result }}

# With:
          DESIGN_CI: ${{ needs.design-ci.result }}

# In run script, replace:
          check_job "Design Lint (impeccable + ast-grep)" "$DESIGN_LINT"
          check_job "Design Drift Check" "$DESIGN_CHECK"

# With:
          check_job "Design Lint + Drift" "$DESIGN_CI"
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: merge design-lint + design-check into design-ci — eliminate job overhead"
```

---

## Wave 4: Parallelize pytest

### Task 12: Add `pytest-xdist` dev dependency

**Files:**

- Modify: `pyproject.toml:23`

- [ ] **Step 1: Add pytest-xdist to dev dependencies**

Add after the existing pytest line (around line 23) in `pyproject.toml`:

```toml
    "pytest-xdist>=3.6.0",
```

- [ ] **Step 2: Run uv sync to update lock**

```bash
uv sync --all-packages --frozen --dev 2>&1 || uv lock && uv sync --all-packages --dev
```

If `--frozen` fails (new dep), run `uv lock` first to update `uv.lock`.

- [ ] **Step 3: Verify xdist installed**

```bash
uv run pytest --help | grep -A1 "xdist"
```

Expected: xdist plugin listed.

- [ ] **Step 4: Run tests locally with xdist**

```bash
uv run pytest backend/tests/ ml/tests/test_device.py ml/tests/test_types.py ml/tests/test_gap_filling.py ml/tests/test_worker_metrics.py ml/tests/test_tracked_extraction.py ml/tests/test_projection.py ml/tests/test_pipeline_parallel.py ml/tests/alignment/ ml/tests/analysis/ ml/tests/utils/ ml/tests/references/ ml/tests/pose_3d/ ml/tests/pose_estimation/ ml/tests/datasets/ -n auto --dist worksteal -v -m "not slow and not integration" --tb=short
```

Expected: All tests pass with xdist. If failures occur, investigate per-failure and either fix xdist-incompatibility or use `-n 2` as fallback.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "ci: add pytest-xdist for parallel test execution"
```

### Task 13: Update test job for xdist + 4vCPU runner

**Files:**

- Modify: `.github/workflows/ci-reusable.yml` (test job)

- [ ] **Step 1: Change runner and add xdist flags**

Update the test job:

```yaml
# BEFORE
  test:
    name: Tests
    needs: [changes]
    if: inputs.run-all || needs.changes.outputs.python == 'true'
    runs-on: blacksmith-2vcpu-ubuntu-2404
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
          -v -m "not slow and not integration"
          --cov=backend/app --cov=ml/src
          --cov-report=xml --junitxml=junit.xml --tb=short

# AFTER
  test:
    name: Tests
    needs: [changes]
    if: inputs.run-all || needs.changes.outputs.python == 'true'
    runs-on: blacksmith-4vcpu-ubuntu-2404
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

Key changes: `blacksmith-2vcpu-ubuntu-2404` → `blacksmith-4vcpu-ubuntu-2404`, added `-n auto --dist worksteal`.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: run pytest with xdist on 4vCPU runner — 174s→~55s expected"
```

---

## Wave 5: Design System Path Filter

### Task 14: Narrow design path filter

**Files:**

- Modify: `.github/workflows/ci-reusable.yml:57-68`

- [ ] **Step 1: Remove non-design entries from design filter**

Replace the design filter in the changes job:

```yaml
# BEFORE
            design:
              - "DESIGN.md"
              - "scripts/design-build.js"
              - "scripts/design-lock.js"
              - "scripts/design-wcag.js"
              - "tokens/lock.json"
              - "frontend/src/app/tokens.css"
              - "frontend/src/app/globals.css"
              - "mobile/androidApp/**/theme/**"
              - "mobile/iosApp/**/Theme/**"
              - "ast-grep/*.yml"
              - "Taskfile.yml"

# AFTER
            design:
              - "DESIGN.md"
              - "scripts/design-*.js"
              - "tokens/lock.json"
              - "frontend/src/app/tokens.css"
              - "frontend/src/app/globals.css"
              - "mobile/androidApp/**/theme/**"
              - "mobile/iosApp/**/Theme/**"
```

Removed: `ast-grep/*.yml` (general lint tool), `Taskfile.yml` (task runner, not design-specific). Simplified `scripts/design-build.js` + `scripts/design-lock.js` + `scripts/design-wcag.js` → `scripts/design-*.js`.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: narrow design path filter — remove ast-grep and Taskfile triggers"
```

---

## Wave 6: Deploy Pipeline Docker Cache

### Task 15: Add registry cache to deploy.yml Docker builds

**Files:**

- Modify: `.github/workflows/deploy.yml:53-61` and `:98-107`

- [ ] **Step 1: Add cache-from/cache-to to frontend build**

Update the `Build & push Frontend` step in deploy.yml:

```yaml
      - name: Build & push Frontend
        id: build
        uses: useblacksmith/build-push-action@v2
        with:
          context: frontend
          file: frontend/Containerfile
          push: true
          tags: |
            ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-frontend:latest
            ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-frontend:${{ github.sha }}
          cache-from: type=registry,ref=ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-frontend:latest
          cache-to: type=inline
```

- [ ] **Step 2: Add cache-from/cache-to to backend build**

Update the `Build & push Backend` step in deploy.yml:

```yaml
      - name: Build & push Backend
        id: build
        uses: useblacksmith/build-push-action@v2
        with:
          context: .
          file: backend/Containerfile
          push: true
          tags: |
            ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-backend:latest
            ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-backend:${{ github.sha }}
          cache-from: type=registry,ref=ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-backend:latest
          cache-to: type=inline
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add Docker registry cache to deploy builds — reuse pushed layers"
```

---

## Verification Task

### Task 16: Verify full CI pipeline

After all waves, verify the workflow YAML is valid and the dependency graph is correct.

- [ ] **Step 1: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci-reusable.yml')); print('ci-reusable.yml: OK')"
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml')); print('deploy.yml: OK')"
```

Expected: Both files parse without error.

- [ ] **Step 2: Verify ci-passed needs references only existing jobs**

```bash
grep -A1 'needs:' .github/workflows/ci-reusable.yml | grep -o '\[[^]]*\]' | tail -1
```

Expected list: `[changes, lint, typecheck, ast-grep, design-ci, test, smoke, fe-check, fe-build, fe-test, docker-backend, docker-frontend]`

No `alembic`, no `fe-lint`, no `fe-typecheck`, no `design-lint`, no `design-check`.

- [ ] **Step 3: Verify no dangling references**

```bash
grep -n 'needs\.\(alembic\|fe-lint\|fe-typecheck\|design-lint\|design-check\)' .github/workflows/ci-reusable.yml
```

Expected: No output (no references to removed job names).

- [ ] **Step 4: Run actionlint if available**

```bash
which actionlint && actionlint .github/workflows/ci-reusable.yml .github/workflows/deploy.yml || echo "actionlint not installed, skip"
```

- [ ] **Step 5: Commit any fixes**

If validation found issues, fix them and commit.

- [ ] **Step 6: Push and monitor CI**

```bash
git push origin worktree-design-system-unify
gh run list --limit=1
```

Monitor the CI run to verify all jobs pass.

---

## Expected Outcome

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Critical path | 240s | ~84s | 65% |
| Total wall time | ~292s | ~115s | 60% |
| Python jobs | 5 × uv sync | 5 × cached venv | ~100s saved |
| Frontend jobs | 6 × bun install | 4 × cached nm | ~20s saved |
| Job count | 16 | 12 | 4 fewer jobs |
