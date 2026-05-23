# Hooks & CI Parallelism Optimization — Design Spec

Date: 2026-05-22

## Problem

Current hook stack has performance and coverage gaps:
- 4 sequential PreToolUse hooks on Bash → ~61ms per tool call (3 Python cold starts)
- No CI-level enforcement (local hooks bypassed via `--no-verify` / `LEFTHOOK=0`)
- Lefthook `ruff-check` + `ruff-format` race on `stage_fixed` (both modify same files in parallel)
- Mobile CI build waits for lint unnecessarily
- Deploy pipeline has serializable steps running sequentially

## Findings Summary

### Lefthook Parallelism
- `parallel: true` uses Go goroutines — already optimal
- `jobs` feature (v1.10+) enables mixed parallel + piped groups
- No async/background hook support (issue #512 — Git's hook model limitation)
- `ruff-check` → `ruff-format` should be piped (format only after check passes, eliminates stage_fixed race)

### Claude Code Hooks
- Multiple PreToolUse hooks run **sequentially**, cannot parallelize
- `type: "http"` persistent server eliminates process spawn overhead entirely (~0.3ms vs 61ms)
- `async: true` available for PostToolUse only (PreToolUse must block)
- 3 Python scripts can merge into 1 → 14ms from 61ms (4.2x)
- Extended Rust binary → 2ms (30x)
- PostToolUse `code-review-graph update` can go async

### Git Safety Hooks — Gaps vs State of the Art
- **claude-code-safety-net** (kenryu42): semantic command parsing, shell wrapper detection (5 levels), worktree relaxation, audit logging
- **destructive_command_guard** (Rust): 40+ pack categories, covers Docker/K8s/Postgres/AWS
- **Missing from our hook**: `git restore` (without --staged), `git checkout -- .`, shell wrapper bypass (`bash -c "git reset --hard"`), `git worktree remove --force`
- Our **worktree enforcement** (git-dir vs git-common-dir) is **novel** — no other tool does this
- Our **LEFTHOOK=0 / HUSKY=0 blocking** is also novel

### CI Optimization
- Remove checkout from `changes` job (dorny API-only mode) → save ~10-15s
- Docker layer cache for `container.yml` (GPU worker) → 50-90% faster rebuilds
- `android-build-debug` doesn't need `needs: [android-lint]` — run in parallel
- SCP deploy files can run parallel with image builds
- Gradle → `gradle/actions/setup-gradle@v4` for auto-caching
- `pytest-xdist -n logical` for in-job test parallelism
- Bun/node_modules cache for frontend jobs (4 jobs each re-install)

### External Tooling
- **Danger Python** — CI-level PR enforcement (defense-in-depth), biggest gap in current stack
- **Lefthook** already beats husky/pre-commit for parallelism
- **overcommit** config signing pattern — prevent hook config tampering
- **OWASP Agentic Security** (ASI05) validates our deterministic hook approach
- **Endor Labs Agent Governance** / **Corridor** — commercial solutions converging on same pattern we use

## Design: 4 Layers

### Layer 1: Merge Python PreToolUse Hooks (Immediate, 5 min)

Merge `block-pip.py`, `block-nohup.py`, `block-unsafe-git.py` into single `bash-guards.py`. Add missing rules from safety-net research.

**Result**: 61ms → 14ms per Bash tool call (4.2x faster).

New rules to add:
- `git restore` (without `--staged`) — discards working tree changes
- `git checkout -- .` / `git checkout --` — discards all uncommitted changes
- `git worktree remove --force` — force-removes worktree
- Shell wrapper detection: `bash -c`, `sh -c`, `zsh -c` containing blocked commands

### Layer 2: Lefthook Jobs Refactor (Medium, 30 min)

Migrate `ruff-check` + `ruff-format` to piped job group. Keep `parallel: true` at top level.

```yaml
pre-commit:
  parallel: true
  jobs:
    - name: protect-branches
      run: |
        BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null)
        # ... existing worktree + branch check
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
        if ! command -v sg &> /dev/null; then exit 0; fi
        sg scan -c sgconfig.yml backend/ ml/ frontend/ mobile/ || true
```

**Result**: Eliminates ruff stage_fixed race, format only runs after check passes.

### Layer 3: PostToolUse Async + CI Defense-in-Depth (Medium, 1-2 hr)

**a) Make `code-review-graph update` async:**
```json
{
  "type": "command",
  "command": "code-review-graph update --skip-flows",
  "async": true
}
```

**b) Add Danger Python to CI** — enforces at PR level what local hooks enforce at commit level:
- Branch naming convention (`feature/`, `fix/`, `hotfix/`)
- Commit message format
- PR size warnings
- Test coverage requirements when src changes

**c) Run lefthook in CI** — mirror local checks so `--no-verify` doesn't escape:
```yaml
# Add to ci-reusable.yml
lefthook-check:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v5
    - run: lefthook run pre-commit
    - run: lefthook run commit-msg
```

**Result**: 4-layer defense: Claude Code hooks → lefthook local → lefthook CI → Danger CI.

### Layer 4: Persistent HTTP Hook Server (Future, 2-4 hr)

Replace command hooks with `type: "http"` persistent server for ~0.3ms per call.

```json
{
  "type": "http",
  "url": "http://localhost:9801/hooks/pre-tool-use"
}
```

Server handles all safety checks in warm process. Eliminates Python/Rust process spawn entirely.

**Result**: 61ms → 0.3ms (200x improvement). Only worth it if hook latency becomes noticeable (currently 61ms is acceptable).

## CI Optimizations (Separate from Hooks)

| Change | Impact | Effort |
|--------|--------|--------|
| Remove checkout from `changes` job | ~10-15s per CI run | Trivial |
| Docker layer cache for `container.yml` (GPU worker) | 50-90% faster rebuilds | Easy |
| Remove `android-lint` from `android-build-debug` needs | ~1-2 min faster mobile CI | Trivial |
| SCP deploy parallel with image builds | ~5-10s faster deploy | Easy |
| Gradle → `setup-gradle@v4` | Better cache coverage | Easy |
| Bun/node_modules cache for frontend | Faster fe-* jobs | Easy |
| `pytest-xdist -n logical` | ~2x test speed | Trivial |
| Lefthook config hash verification in CI | Supply chain protection | Easy |

## Priority Order

1. **Merge Python hooks** (5 min, 4.2x perf)
2. **Lefthook jobs refactor** (30 min, race condition fix)
3. **Add missing git safety rules** (15 min, coverage gaps)
4. **CI: changes job + mobile needs** (10 min, instant wins)
5. **CI: Docker layer cache + Gradle setup** (30 min, build perf)
6. **PostToolUse async** (5 min, non-blocking CRG)
7. **Danger Python in CI** (1-2 hr, defense-in-depth)
8. **CI: lefthook mirror** (30 min, catch --no-verify)
9. **HTTP hook server** (future, when needed)
