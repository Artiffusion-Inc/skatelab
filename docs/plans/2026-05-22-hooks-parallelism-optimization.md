# Hooks & CI Parallelism Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge 3 Python PreToolUse hooks into 1 (4.2x perf), fix lefthook ruff race, add missing git safety rules, optimize CI parallelism, add defense-in-depth.

**Architecture:** 4-layer defense: Claude Code hooks → lefthook local → lefthook CI → Danger CI. Merge Python scripts eliminates 2 cold starts per Bash tool call. Lefthook jobs refactor uses piped groups to eliminate stage_fixed race. CI optimizations remove bottlenecks in changes detection, mobile build deps, and Docker layer caching.

**Tech Stack:** Python 3 (hooks), Go (bash_guard.bin), lefthook, GitHub Actions, Danger Python, pytest-xdist

---

## Task 1: Merge Python PreToolUse Hooks into `bash-guards.py`

**Files:**

- Create: `$CLAUDE_CONFIG_DIR/hooks/bash-guards.py`
- Delete: `$CLAUDE_CONFIG_DIR/hooks/block-pip.py`
- Delete: `$CLAUDE_CONFIG_DIR/hooks/block-nohup.py`
- Delete: `$CLAUDE_CONFIG_DIR/hooks/block-unsafe-git.py`
- Modify: `$CLAUDE_CONFIG_DIR/settings.json` (hooks section)

- [ ] **Step 1: Write the merged hook script**

Create `$CLAUDE_CONFIG_DIR/hooks/bash-guards.py`:

```python
"""Merged PreToolUse guard for Bash commands.

Combines block-pip, block-nohup, block-unsafe-git into one script.
Eliminates 2 Python cold starts per Bash tool call (61ms → 14ms).

Exit code 2 = deny (blocks the tool call).
"""

import json
import re
import sys

# ── pip guard ──────────────────────────────────────────────────
PIP_PATTERN = re.compile(r"^pip(-?3)?(?:\.\d+)?$")
PIP_INSTALL_WORD = "install"

def check_pip(cmd: str, parts: list[str]) -> str | None:
    if not parts:
        return None
    first = parts[0]
    if PIP_PATTERN.match(first) and PIP_INSTALL_WORD in parts:
        return (
            "BLOCKED: pip install not allowed. Use uv instead.\n"
            "Pattern: uv add <packages>\n"
            "Example: uv add requests httpx"
        )
    return None

# ── nohup guard ─────────────────────────────────────────────────
def check_nohup(cmd: str, parts: list[str]) -> str | None:
    if parts and parts[0] == "nohup":
        return (
            "BLOCKED: nohup not allowed. Use tmux instead.\n"
            "\n"
            "Patterns:\n"
            "  nohup <cmd> &             →  tmux new -s <name> -d '<cmd>'\n"
            "  nohup <cmd> > out.log 2>&1 &  →  tmux new -s <name> -d '<cmd> 2>&1 | tee out.log'\n"
            "\n"
            "Attach later:  tmux attach -t <name>\n"
            "List sessions: tmux ls\n"
            "Kill session:  tmux kill-session -t <name>\n"
            "\n"
            "Quick one-liner: tmux new -s build -d 'docker build -f Containerfile .'"
        )
    return None

# ── unsafe git guard ──────────────────────────────────────────
BLOCKED_CMD_PATTERNS = [
    (r"\b--no-verify\b", "BLOCKED: --no-verify skips hooks. Fix the hook failures instead."),
    (r"\b--skip-hooks\b", "BLOCKED: --skip-hooks bypasses lefthook. Fix the hook failures instead."),
    (r"\bgit\s+push\s+.*\s+--force\b", "BLOCKED: --force push overwrites upstream. Use --force-with-lease instead."),
    (r"\bgit\s+reset\s+--hard\b", "BLOCKED: reset --hard discards uncommitted changes. Use reset --soft or --mixed."),
    (r"\bgit\s+checkout\s+-f\b", "BLOCKED: checkout -f discards local changes. Stash or commit first."),
    (r"\bgit\s+clean\s+-f\b", "BLOCKED: clean -f removes untracked files. Use clean -fd with caution."),
    (r"\bgit\s+stash\s+drop\b", "BLOCKED: stash drop loses work. Use stash pop instead."),
    (r"\bgit\s+branch\s+-D\b", "BLOCKED: branch -D force-deletes. Use branch -d for safe deletion."),
    (r"\bgit\s+restore\b", "BLOCKED: git restore discards working tree changes. Use git stash instead."),
    (r"\bgit\s+checkout\s+--\b", "BLOCKED: checkout -- discards uncommitted changes. Use git stash instead."),
    (r"\bgit\s+worktree\s+remove\s+--force\b", "BLOCKED: worktree remove --force skips safety checks. Remove without --force."),
]

BLOCKED_ENV_PATTERNS = [
    (r"LEFTHOOK=0", "BLOCKED: LEFTHOOK=0 disables all hooks. Fix the hook failures instead."),
    (r"HUSKY=0", "BLOCKED: HUSKY=0 disables all hooks. Fix the hook failures instead."),
]

SHELL_WRAPPER_PATTERNS = [
    (r"\b(bash|sh|zsh)\s+-c\s+.*\b(git\s+reset\s+--hard|git\s+checkout\s+-f|git\s+clean\s+-f|git\s+branch\s+-D|git\s+stash\s+drop|git\s+restore|git\s+push\s+.*--force)\b",
     "BLOCKED: shell wrapper detected containing blocked git command."),
]

COMPILED_CMD = [(re.compile(p), msg) for p, msg in BLOCKED_CMD_PATTERNS]
COMPILED_ENV = [(re.compile(p), msg) for p, msg in BLOCKED_ENV_PATTERNS]
COMPILED_SHELL = [(re.compile(p), msg) for p, msg in SHELL_WRAPPER_PATTERNS]

# git restore without --staged is destructive. git restore --staged is safe (un-stages).
RESTORE_STAGED_PATTERN = re.compile(r"\bgit\s+restore\s+--stage")

def check_unsafe_git(cmd: str, parts: list[str]) -> str | None:
    for pattern, message in COMPILED_ENV:
        if pattern.search(cmd):
            return message

    for pattern, message in COMPILED_SHELL:
        if pattern.search(cmd):
            return message

    for pattern, message in COMPILED_CMD:
        if pattern.search(cmd):
            # Special case: git restore --staged is safe (unstages, doesn't discard)
            if "git restore" in message and RESTORE_STAGED_PATTERN.search(cmd):
                continue
            return message

    return None

# ── main ───────────────────────────────────────────────────────
def main():
    try:
        input_data = json.loads(sys.stdin.read())
        cmd = input_data.get("tool_input", {}).get("command", "")

        if not cmd:
            sys.exit(0)

        parts = cmd.split()

        # Run all checks; return first block
        for checker in (check_pip, check_nohup, check_unsafe_git):
            result = checker(cmd, parts)
            if result:
                print(f"[hook] {result}", file=sys.stderr)
                sys.exit(2)

        sys.exit(0)

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the merged hook manually**

```bash
# Test pip block
echo '{"tool_input":{"command":"pip install requests"}}' | python3 ~/.config/claude/hooks/bash-guards.py
# Expected: exit 2, "pip install not allowed"

# Test nohup block
echo '{"tool_input":{"command":"nohup ./build.sh &"}}' | python3 ~/.config/claude/hooks/bash-guards.py
# Expected: exit 2, "nohup not allowed"

# Test git reset --hard block
echo '{"tool_input":{"command":"git reset --hard HEAD~1"}}' | python3 ~/.config/claude/hooks/bash-guards.py
# Expected: exit 2, "reset --hard"

# Test git restore --staged is ALLOWED
echo '{"tool_input":{"command":"git restore --staged file.py"}}' | python3 ~/.config/claude/hooks/bash-guards.py
# Expected: exit 0

# Test git restore WITHOUT --staged is BLOCKED
echo '{"tool_input":{"command":"git restore file.py"}}' | python3 ~/.config/claude/hooks/bash-guards.py
# Expected: exit 2, "git restore"

# Test shell wrapper detection
echo '{"tool_input":{"command":"bash -c \"git reset --hard HEAD\""}}' | python3 ~/.config/claude/hooks/bash-guards.py
# Expected: exit 2, "shell wrapper"

# Test safe command passes
echo '{"tool_input":{"command":"git add file.py"}}' | python3 ~/.config/claude/hooks/bash-guards.py
# Expected: exit 0

# Test LEFTHOOK=0 block
echo '{"tool_input":{"command":"LEFTHOOK=0 git commit -m test"}}' | python3 ~/.config/claude/hooks/bash-guards.py
# Expected: exit 2, "LEFTHOOK=0"
```

- [ ] **Step 3: Update settings.json to use merged hook**

In `$CLAUDE_CONFIG_DIR/settings.json`, replace the 3 Python hook entries in `PreToolUse` with the merged one:

Before:
```json
"PreToolUse": [
  {
    "matcher": "Bash",
    "hooks": [
      {
        "type": "command",
        "command": "$CLAUDE_CONFIG_DIR/hooks/bash-guard/bash_guard.bin"
      },
      {
        "type": "command",
        "command": "python3 $CLAUDE_CONFIG_DIR/hooks/block-pip.py"
      },
      {
        "type": "command",
        "command": "python3 $CLAUDE_CONFIG_DIR/hooks/block-nohup.py"
      },
      {
        "type": "command",
        "command": "python3 $CLAUDE_CONFIG_DIR/hooks/block-unsafe-git.py"
      }
    ]
  }
]
```

After:
```json
"PreToolUse": [
  {
    "matcher": "Bash",
    "hooks": [
      {
        "type": "command",
        "command": "$CLAUDE_CONFIG_DIR/hooks/bash-guard/bash_guard.bin"
      },
      {
        "type": "command",
        "command": "python3 $CLAUDE_CONFIG_DIR/hooks/bash-guards.py"
      }
    ]
  }
]
```

- [ ] **Step 4: Verify hook fires correctly in Claude Code session**

Run a test Bash command like `pip install foo` in Claude Code. Expected: blocked by hook.

- [ ] **Step 5: Delete old individual hook scripts**

```bash
rm ~/.config/claude/hooks/block-pip.py
rm ~/.config/claude/hooks/block-nohup.py
rm ~/.config/claude/hooks/block-unsafe-git.py
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(hooks): merge 3 Python PreToolUse hooks into bash-guards.py

4.2x faster: 61ms → 14ms per Bash tool call (2 fewer Python cold starts).
Adds missing rules: git restore, git checkout --, git worktree remove --force,
shell wrapper detection (bash -c / sh -c / zsh -c).
"
```

---

## Task 2: Lefthook Jobs Refactor — Piped Ruff Group

**Files:**

- Modify: `lefthook.yml` (pre-commit section)

- [ ] **Step 1: Rewrite pre-commit section with piped ruff jobs**

Replace `pre-commit.commands` with `pre-commit.jobs` in `lefthook.yml`:

```yaml
pre-commit:
  parallel: true
  jobs:
    - name: protect-branches
      run: |
        BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null)
        if [[ $BRANCH =~ ^(main|master|develop)$ ]]; then
          echo "❌ Direct commits to '$BRANCH' are not allowed."
          echo "Please use a feature/hotfix/release branch."
          exit 1
        fi
        GIT_DIR=$(git rev-parse --git-dir)
        GIT_COMMON_DIR=$(git rev-parse --git-common-dir)
        if [ "$GIT_DIR" = "$GIT_COMMON_DIR" ]; then
          echo "❌ Commits must be made from a git worktree, not the main working tree."
          echo "   Use EnterWorktree tool or: git worktree add ../<name> -b <branch>"
          exit 1
        fi

    - name: ruff
      glob: "*.py"
      group:
        piped: true
        jobs:
          - name: ruff-check
            run: uv run ruff check {staged_files} --fix
            stage_fixed: true
          - name: ruff-format
            run: uv run ruff format {staged_files}
            stage_fixed: true

    - name: biome-check
      glob: "frontend/**/*.{ts,tsx,js,jsx,json,css}"
      run: bunx biome check --write {staged_files}
      stage_fixed: true

    - name: ktlint-format
      glob: "mobile/**/*.{kt,kts}"
      run: cd mobile && ./gradlew ktlintFormat 2>&1 | tail -5
      stage_fixed: true

    - name: ast-grep-scan
      run: |
        if ! command -v sg &> /dev/null; then
          exit 0
        fi
        sg scan -c sgconfig.yml backend/ ml/ frontend/ mobile/ || true
```

- [ ] **Step 2: Test lefthook pre-commit**

```bash
# Make a small Python change and try to commit
echo "# test" >> backend/app/config.py
git add backend/app/config.py
lefthook run pre-commit
# Expected: ruff-check runs first, then ruff-format (piped, not parallel)
# No race condition on stage_fixed

# Revert test change
git checkout -- backend/app/config.py
```

- [ ] **Step 3: Verify protect-branches worktree check still works**

From main tree:
```bash
lefthook run pre-commit 2>&1 | head -5
# Expected: "Commits must be made from a git worktree"
```

- [ ] **Step 4: Commit**

```bash
git add lefthook.yml
git commit -m "fix(lefthook): piped ruff group eliminates stage_fixed race

ruff-check → ruff-format now runs sequentially via piped group.
Prevents both hooks modifying same files in parallel."
```

---

## Task 3: CI — Remove Checkout from `changes` Job

**Files:**

- Modify: `.github/workflows/ci-reusable.yml` (changes job)
- Modify: `.github/workflows/mobile.yml` (changes job)

- [ ] **Step 1: Update ci-reusable.yml changes job to use API-only mode**

Replace the `changes` job steps:

Before:
```yaml
  changes:
    name: Detect changed files
    runs-on: ubuntu-latest
    outputs:
      python: ${{ steps.filter.outputs.python }}
      ml: ${{ steps.filter.outputs.ml }}
      frontend: ${{ steps.filter.outputs.frontend }}
      docker: ${{ steps.filter.outputs.docker }}
    steps:
      - uses: actions/checkout@v6
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            python:
              - "backend/**"
              - "ml/src/**"
              - "ml/tests/**"
              - "pyproject.toml"
              - "backend/pyproject.toml"
              - "ml/pyproject.toml"
            ml:
              - "ml/**"
              - "pyproject.toml"
              - "ml/pyproject.toml"
            frontend:
              - "frontend/**"
            docker:
              - "backend/Containerfile"
              - "frontend/Containerfile"
              - ".containerignore"
              - "infra/**"
```

After:
```yaml
  changes:
    name: Detect changed files
    runs-on: ubuntu-latest
    outputs:
      python: ${{ steps.filter.outputs.python }}
      ml: ${{ steps.filter.outputs.ml }}
      frontend: ${{ steps.filter.outputs.frontend }}
      docker: ${{ steps.filter.outputs.docker }}
    steps:
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          filters: |
            python:
              - "backend/**"
              - "ml/src/**"
              - "ml/tests/**"
              - "pyproject.toml"
              - "backend/pyproject.toml"
              - "ml/pyproject.toml"
            ml:
              - "ml/**"
              - "pyproject.toml"
              - "ml/pyproject.toml"
            frontend:
              - "frontend/**"
            docker:
              - "backend/Containerfile"
              - "frontend/Containerfile"
              - ".containerignore"
              - "infra/**"
```

Key change: removed `actions/checkout@v6` step, added `token` input. `dorny/paths-filter` uses GitHub API instead of local git diff when `token` is provided and checkout is skipped.

- [ ] **Step 2: Update mobile.yml changes job similarly**

In `.github/workflows/mobile.yml`, remove the `actions/checkout@v5` step from the `changes` job and add `token` to `dorny/paths-filter`:

Before:
```yaml
    steps:
      - uses: actions/checkout@v5
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
```

After:
```yaml
    steps:
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          filters: |
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci-reusable.yml .github/workflows/mobile.yml
git commit -m "ci: remove checkout from changes jobs (API-only paths-filter)

~10-15s saved per CI run. dorny/paths-filter uses GitHub API
when token provided and no checkout step."
```

---

## Task 4: CI — Remove `android-lint` from `android-build-debug` Needs

**Files:**

- Modify: `.github/workflows/mobile.yml`

- [ ] **Step 1: Change android-build-debug needs**

Before:
```yaml
  android-build-debug:
    name: Build debug APK
    needs: [android-lint, android-test]
```

After:
```yaml
  android-build-debug:
    name: Build debug APK
    needs: [android-test]
```

`android-lint` and `android-build-debug` run in parallel after `android-test`. Lint does not gate the build.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/mobile.yml
git commit -m "ci(mobile): run android-build-debug parallel with android-lint

Both only need android-test. ~1-2 min faster mobile CI."
```

---

## Task 5: CI — Docker Layer Cache for GPU Worker

**Files:**

- Modify: `.github/workflows/container.yml`

- [ ] **Step 1: Add Docker layer caching to container.yml**

Replace the build-push step with cached version:

Before:
```yaml
      - name: Build and push
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          file: ml/gpu_server/Containerfile
          push: true
          tags: |
            ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-worker:latest
            ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-worker:${{ github.sha }}
          secrets: |
            moganet_url=${{ steps.presign.outputs.moganet_url }}
            yolo_url=${{ steps.presign.outputs.yolo_url }}
```

After:
```yaml
      - name: Build and push
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          file: ml/gpu_server/Containerfile
          push: true
          tags: |
            ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-worker:latest
            ghcr.io/${{ steps.ghcr.outputs.owner }}/skatelab-worker:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          secrets: |
            moganet_url=${{ steps.presign.outputs.moganet_url }}
            yolo_url=${{ steps.presign.outputs.yolo_url }}
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/container.yml
git commit -m "ci(container): add GitHub Actions Docker layer cache

50-90% faster GPU worker rebuilds via GHA cache backend."
```

---

## Task 6: CI — Gradle Setup Action with Auto-Caching

**Files:**

- Modify: `.github/actions/setup-android/action.yml` (if exists)
- Modify: `.github/workflows/mobile.yml` (replace setup-android usage)

- [ ] **Step 1: Check current setup-android action**

```bash
cat .github/actions/setup-android/action.yml
```

- [ ] **Step 2: Add gradle/actions/setup-gradle@v4 to setup-android**

If setup-android doesn't already use `gradle/actions/setup-gradle@v4`, add it. The action should become:

```yaml
name: 'Setup Android SDK + Gradle'
description: 'JDK 17 + Android SDK + Gradle cache'

runs:
  using: "composite"
  steps:
    - uses: actions/setup-java@v4
      with:
        distribution: 'temurin'
        java-version: '17'

    - uses: gradle/actions/setup-gradle@v4
      with:
        cache-read-only: false

    - name: Setup Android SDK
      uses: android-actions/setup-android@v3
```

If setup-android already has `gradle/actions/setup-gradle@v4`, skip this step.

- [ ] **Step 3: Commit**

```bash
git add .github/actions/setup-android/action.yml
git commit -m "ci(mobile): use gradle/actions/setup-gradle@v4 for auto-caching

Better cache coverage than manual .gradle caching.
"
```

---

## Task 7: CI — pytest-xdist for In-Job Test Parallelism

**Files:**

- Modify: `.github/workflows/ci-reusable.yml` (test job)

- [ ] **Step 1: Add pytest-xdist flag to test command**

In `ci-reusable.yml`, update the pytest run step:

Before:
```yaml
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
```

After:
```yaml
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
          -n logical
          --cov=backend/app --cov=ml/src
          --cov-report=xml --junitxml=junit.xml --tb=short
```

Key addition: `-n logical` uses all logical CPUs for parallel test execution.

- [ ] **Step 2: Verify pytest-xdist is in dependencies**

```bash
grep -r "pytest-xdist" pyproject.toml backend/pyproject.toml ml/pyproject.toml
```

If not present, add it:
```bash
cd /home/michael/Github/skating-biomechanics-ml && uv add --group dev pytest-xdist
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci-reusable.yml pyproject.toml
git commit -m "ci: add pytest-xdist -n logical for parallel test execution

~2x test speed on multi-core runners."
```

---

## Task 8: CI — Bun/Node Modules Cache for Frontend Jobs

**Files:**

- Modify: `.github/workflows/ci-reusable.yml` (fe-lint, fe-typecheck, fe-build, fe-test)

- [ ] **Step 1: Add bun cache to frontend jobs**

Each frontend job currently runs `bun install --frozen-lockfile`. Add caching via `oven-sh/setup-bun@v2`:

Before (example for fe-lint):
```yaml
  fe-lint:
    name: Lint (Biome)
    needs: [changes]
    if: inputs.run-all || needs.changes.outputs.frontend == 'true'
    runs-on: blacksmith-2vcpu-ubuntu-2404
    steps:
      - uses: actions/checkout@v6
      - uses: oven-sh/setup-bun@v2
      - name: Install deps
        working-directory: frontend
        run: bun install --frozen-lockfile
```

After:
```yaml
  fe-lint:
    name: Lint (Biome)
    needs: [changes]
    if: inputs.run-all || needs.changes.outputs.frontend == 'true'
    runs-on: blacksmith-2vcpu-ubuntu-2404
    steps:
      - uses: actions/checkout@v6
      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: latest
      - uses: actions/cache@v4
        with:
          path: frontend/node_modules
          key: bun-${{ runner.os }}-${{ hashFiles('frontend/bun.lockb') }}
          restore-keys: bun-${{ runner.os }}-
      - name: Install deps
        working-directory: frontend
        run: bun install --frozen-lockfile
```

Apply the same cache step to: `fe-typecheck`, `fe-build`, `fe-test`.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci(frontend): add bun/node_modules cache for all fe-* jobs

4 jobs each re-installed from scratch. Cache skips install on cache hit."
```

---

## Task 9: PostToolUse Async — code-review-graph update

**Files:**

- Modify: `$CLAUDE_CONFIG_DIR/settings.json` (PostToolUse hooks)

- [ ] **Step 1: Add async: true to PostToolUse code-review-graph hook**

In `$CLAUDE_CONFIG_DIR/settings.json`, update the PostToolUse hook:

Before:
```json
"PostToolUse": [
  {
    "matcher": "Edit|Write|Bash",
    "hooks": [
      {
        "type": "command",
        "command": "code-review-graph update --skip-flows",
        "timeout": 30
      }
    ]
  }
]
```

After:
```json
"PostToolUse": [
  {
    "matcher": "Edit|Write|Bash",
    "hooks": [
      {
        "type": "command",
        "command": "code-review-graph update --skip-flows",
        "timeout": 30,
        "async": true
      }
    ]
  }
]
```

- [ ] **Step 2: Verify async fires correctly**

Make an Edit in Claude Code. The graph update should run in background without blocking the next tool call.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat(hooks): make PostToolUse code-review-graph update async

Non-blocking graph update after edits. Eliminates ~2s wait per edit cycle."
```

---

## Task 10: CI — Lefthook Mirror (Defense-in-Depth)

**Files:**

- Modify: `.github/workflows/ci-reusable.yml` (add lefthook job)

- [ ] **Step 1: Add lefthook-check job to ci-reusable.yml**

Add a new job before the `ci-passed` summary job:

```yaml
  lefthook-check:
    name: Lefthook Checks
    runs-on: blacksmith-2vcpu-ubuntu-2404
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: oven-sh/setup-bun@v2
      - name: Install lefthook
        run: uv run lefthook install
      - name: Run pre-commit hooks
        run: uv run lefthook run pre-commit
      - name: Run commit-msg hooks
        run: uv run lefthook run commit-msg
```

Add `lefthook-check` to the `ci-passed` job's `needs` list.

- [ ] **Step 2: Update ci-passed needs**

Before:
```yaml
    needs: [changes, lint, typecheck, alembic, ast-grep, test, smoke, fe-lint, fe-typecheck, fe-build, fe-test, docker-backend, docker-frontend]
```

After:
```yaml
    needs: [changes, lint, typecheck, alembic, ast-grep, test, smoke, fe-lint, fe-typecheck, fe-build, fe-test, docker-backend, docker-frontend, lefthook-check]
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci: add lefthook-check job — defense-in-depth vs --no-verify

Mirrors local lefthook hooks in CI so --no-verify doesn't escape checks."
```

---

## Task 11: Danger Python in CI — PR-Level Enforcement

**Files:**

- Create: `dangerfile.py` (project root)
- Modify: `.github/workflows/ci-reusable.yml` (add danger job)
- Modify: `pyproject.toml` (add danger-python dev dep)

- [ ] **Step 1: Add danger-python dependency**

```bash
uv add --group dev danger-python
```

- [ ] **Step 2: Create dangerfile.py**

```python
"""Danger CI rules — PR-level enforcement.

Runs in CI only. Complements local lefthook hooks (defense-in-depth).
"""

from danger import Danger, Violation

danger = Danger()

# ── Branch naming convention ──────────────────────────────────
if danger.github.pr.branch_name:
    branch = danger.github.pr.branch_name
    valid_prefixes = ("feature/", "fix/", "hotfix/", "refactor/", "chore/", "ci/", "docs/", "test/")
    if not any(branch.startswith(p) for p in valid_prefixes):
        danger.fail(f"Branch '{branch}' doesn't follow naming convention. Use: {', '.join(valid_prefixes)}")

# ── Commit message format ─────────────────────────────────────
if danger.git.commits:
    pattern = r"^(feat|fix|refactor|chore|docs|test|ci)\([a-z0-9_-]+\): .{3,}$"
    import re
    for commit in danger.git.commits:
        if not re.match(pattern, commit.message.split("\n")[0]):
            danger.fail(
                f"Bad commit message: `{commit.message.split(chr(10))[0]}`\n"
                f"  Expected: `type(scope): summary`"
            )
            break  # One failure enough

# ── PR size warning ───────────────────────────────────────────
if danger.github.pr.additions and danger.github.pr.deletions:
    total = danger.github.pr.additions + danger.github.pr.deletions
    if total > 1000:
        danger.warn(f"Large PR: {total} lines changed. Consider splitting.")
    elif total > 500:
        danger.message(f"PR size: {total} lines changed.")

# ── Test coverage requirement ─────────────────────────────────
src_files = [f for f in danger.git.modified_files if f.endswith(".py") and "test" not in f]
test_files = [f for f in danger.git.modified_files if f.endswith(".py") and "test" in f]
if src_files and not test_files:
    danger.warn("Source files changed without tests. Consider adding test coverage.")
```

- [ ] **Step 3: Add danger job to ci-reusable.yml**

```yaml
  danger:
    name: Danger (PR checks)
    if: github.event_name == 'pull_request'
    runs-on: blacksmith-2vcpu-ubuntu-2404
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ inputs.python-version }}
      - name: Install deps
        run: uv sync --all-packages --frozen --dev
      - name: Run Danger
        run: uv run danger ci
        env:
          DANGER_GITHUB_API_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Add `danger` to the `ci-passed` job's `needs` list (informational only — danger warnings shouldn't block CI).

- [ ] **Step 4: Make danger informational in ci-passed**

In the `ci-passed` job, add danger to needs but treat it as informational:

```yaml
    needs: [changes, lint, typecheck, alembic, ast-grep, test, smoke, fe-lint, fe-typecheck, fe-build, fe-test, docker-backend, docker-frontend, lefthook-check, danger]
```

In the check_job function, add a special case for danger:
```bash
          check_job_info() {
            local name="$1" result="$2"
            echo "| :information_source: ${name} | \`${result}\` (informational) |" >> "$GITHUB_STEP_SUMMARY"
          }

          check_job_info "Danger (PR checks)" "$DANGER"
```

- [ ] **Step 5: Commit**

```bash
git add dangerfile.py pyproject.toml uv.lock .github/workflows/ci-reusable.yml
git commit -m "ci: add Danger Python — PR-level enforcement (defense-in-depth)

Branch naming, commit format, PR size warnings, test coverage nudges.
Complements local lefthook hooks — 4th layer of defense."
```

---

## Task 12: CI — Deploy Pipeline Parallel SCP

**Files:**

- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Read current deploy.yml**

```bash
cat .github/workflows/deploy.yml
```

- [ ] **Step 2: Identify SCP step that can run parallel with image builds**

Find the step that SCPs deploy files. If it currently runs after image builds, move it to a separate job that runs in parallel with the image build job (both after CI passes).

This depends on the current deploy.yml structure. The general pattern:

```yaml
  deploy-files:
    name: Deploy files to VPS
    needs: [ci]  # Only needs CI, not image builds
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: SCP deploy files
        run: ...  # existing SCP command

  build-images:
    name: Build & Push Images
    needs: [ci]
    runs-on: ubuntu-latest
    steps:
      ...  # existing image build steps

  deploy:
    name: Deploy
    needs: [deploy-files, build-images]
    ...
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci(deploy): run SCP deploy parallel with image builds

~5-10s faster deploy pipeline."
```

---

## Summary: Expected Impact

| Task | Change | Impact |
|------|--------|--------|
| 1. Merge Python hooks | 3→1 scripts, +5 safety rules | 61ms→14ms (4.2x), coverage gaps fixed |
| 2. Lefthook piped ruff | Sequential ruff-check→format | Race condition eliminated |
| 3. CI: changes API-only | Remove checkout | ~10-15s per CI run |
| 4. CI: mobile needs | Parallel lint+build | ~1-2 min faster mobile CI |
| 5. CI: Docker layer cache | GHA cache for GPU worker | 50-90% faster rebuilds |
| 6. CI: Gradle setup | setup-gradle@v4 | Better cache coverage |
| 7. CI: pytest-xdist | -n logical | ~2x test speed |
| 8. CI: Bun cache | node_modules cache | Faster fe-* jobs |
| 9. PostToolUse async | async: true | Non-blocking CRG update |
| 10. CI: lefthook mirror | CI lefthook job | Catches --no-verify |
| 11. Danger Python | PR-level checks | Defense-in-depth |
| 12. Deploy parallel SCP | Parallel deploy files | ~5-10s faster deploy |

**Task 9 (HTTP hook server) deferred** — 61ms acceptable today. Revisit if hook latency becomes noticeable.
