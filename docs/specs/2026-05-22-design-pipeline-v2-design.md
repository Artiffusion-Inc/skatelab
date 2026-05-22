# Design Pipeline v2 — LLM-First Generation

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task.

**Goal:** Replace Style Dictionary with LLM-based generation that reads the entire DESIGN.md (YAML + prose) and outputs complete platform files, component tokens, shadow tokens, .sh-* CSS classes, and WCAG validation.

**Architecture:** DESIGN.md → `claude -p` (structured JSON via `--json-schema`) → `scripts/design-build.js` (validate + retry + fallback) → platform files. Style Dictionary removed. Checksum lockfile for drift detection. impeccable + hallmark for quality enforcement. Hybrid fan-out for parallelism.

**Tech Stack:** Claude CLI (`claude -p` with `--json-schema --bare`), Node.js (`execa` + `p-queue`), impeccable CLI, hallmark skill, ast-grep, git checksums

---

## 1. Architecture

### Source of Truth

DESIGN.md — single source. Contains both structured data (YAML frontmatter: colors, typography, rounded, spacing, shadows, components) and prose (Named Rules, component descriptions, hover/focus styles, WCAG warnings, Do's/Don'ts).

### Pipeline

```
DESIGN.md
    │
    ├─→ scripts/design-build.js
    │     ├─ Hash DESIGN.md → if unchanged, skip generation (exit 0)
    │     ├─ Parse DESIGN.md (full content, not just YAML)
    │     ├─ Scan for comment triggers (<!-- generate:all -->, etc.)
    │     ├─ Phase 1: Architect call
    │     │    Run: claude -p "<vocab prompt>" --bare --output-format json --json-schema '<vocab-schema>'
    │     │    Produces: shared vocabulary (color names, semantic aliases, type scale)
    │     ├─ Phase 2: Platform fan-out (3 parallel calls via p-queue)
    │     │    ┬─ claude -p "<css prompt + vocab>" --bare --output-format json --json-schema '<css-schema>'
    │     │    ├─ claude -p "<kotlin prompt + vocab>" --bare --output-format json --json-schema '<kotlin-schema>'
    │     │    └─ claude -p "<swift prompt + vocab>" --bare --output-format json --json-schema '<swift-schema>'
    │     ├─ Validate each response:
    │     │    - JSON Schema compliance (guaranteed by --json-schema, verify structurally)
    │     │    - Required file keys present
    │     │    - colorCount >= 23, typographyCount >= 14, shadowsCount >= 3, componentsCount >= 14
    │     │    - Kotlin/Swift basic syntax check (regex)
    │     │    - CSS custom property format check
    │     │    - Cross-platform name consistency check (shared vocab alignment)
    │     ├─ On validation failure → retry with error context (max 3)
    │     │    Distinguish: validation errors → retry with context; API errors (429/5xx) → exponential backoff + jitter; non-retryable (4xx not 429) → immediate fallback
    │     ├─ On API error → exponential backoff: min(base * 2^attempt, 30s) + random(0, 500ms)
    │     ├─ Circuit breaker: after 5 consecutive total failures across runs, skip generation, require manual review
    │     ├─ If all retries fail → git checkout HEAD (restore last committed version)
    │     └─ Write validated files to disk
    │
    ├─→ scripts/design-wcag.js
    │     ├─ Read generated color tokens
    │     ├─ Compute contrast ratios for all named pairs
    │     └─ Fail if WCAG AA violated (4.5:1 normal, 3:1 large)
    │
    ├─→ impeccable detect --fast --json
    │     └─ UI anti-pattern scan (CI + pre-commit, deterministic, no LLM)
    │
    ├─→ ast-grep scan (expanded rules)
    │     └─ Structural pattern enforcement (10-15 design system rules)
    │
    └─→ hallmark audit (via claude -p, scheduled/manual only)
          └─ Deep design quality audit (weekly schedule or manual trigger)
```

### Removed

- `style-dictionary.config.js`
- `tokens/dtcg.json`
- `style-dictionary` from `package.json`
- `scripts/design-tokens.js` (replaced by `scripts/design-build.js`)

### Generated files (full files, not fragments)

| File | Content |
|---|---|
| `frontend/src/app/tokens.css` | CSS custom properties (:root block + shadcn aliases + shadow vars) |
| `frontend/src/app/globals.css` | Patched: .sh-* classes block, @theme inline block |
| `mobile/.../theme/Colors.kt` | SkateLabColors object + semantic aliases |
| `mobile/.../theme/Type.kt` | InterVariable, SkateLabTypography, weightOrFallback |
| `mobile/.../theme/Theme.kt` | SkateLabLightScheme, AppTheme, toMaterialTypography |
| `mobile/.../theme/Shadows.kt` | SkateLabShadows object with Modifier extensions |
| `mobile/.../theme/Modifiers.kt` | Component token Modifier extensions (button, card, badge) |
| `mobile/iosApp/.../SkateLabColors.swift` | Color extension + skateOnPrimary |
| `mobile/iosApp/.../SkateLabTypography.swift` | CTFont-based variable weight fonts |
| `mobile/iosApp/.../SkateLabTheme.swift` | SkateLabColorScheme + environment |
| `mobile/iosApp/.../SkateLabShadows.swift` | Shadow ViewModifier extensions |
| `mobile/iosApp/.../SkateLabModifiers.swift` | Component ViewModifier extensions |

## 2. LLM Prompt Design

### CLI invocation

All `claude -p` calls use these flags:

```bash
claude -p "<prompt>" \
  --bare \
  --output-format json \
  --json-schema '<schema>' \
  --max-turns 1
```

- `--bare`: hermetic invocation — skips hooks, skills, MCP, CLAUDE.md. Reproducible across machines.
- `--json-schema`: constrained decoding — guarantees valid JSON matching schema. Eliminates 5-20% malformed JSON failure rate.
- `--max-turns 1`: single-shot generation, no multi-turn conversation.
- Model: project's configured model (Ollama Cloud or Anthropic direct). No hardcoded model in scripts.

### Hybrid Fan-Out: Architect + Platform Calls

**Phase 1 — Architect call** (~5s): Produces shared vocabulary ensuring cross-platform consistency.

Schema:
```json
{
  "colorNames": { "primary": "#155f73", "primaryDeep": "#0e3340", "..." },
  "semanticAliases": { "onPrimary": "primaryForeground", "background": "canvas", "..." },
  "typeScale": { "display-xl": { "size": "3rem", "weight": 460, "tracking": "-0.02em" }, "..." },
  "shadowTokens": { "ambient-low": { "offsetX": 0, "offsetY": 2, "blur": 8, "spread": 0, "color": "#0000001a" }, "..." },
  "componentTokens": { "btn-primary": { "bg": "primary", "text": "primaryForeground", "radius": "rounded-md" }, "..." }
}
```

**Phase 2 — Platform fan-out** (3 parallel calls, ~15-25s each): Each call receives the shared vocabulary + DESIGN.md + platform-specific rules.

Platform calls use `execa` with 120s timeout + `p-queue` (concurrency: 3):

```js
import { execa } from 'execa';
import PQueue from 'p-queue';

const queue = new PQueue({ concurrency: 3, timeout: 180_000 });
const [cssResult, kotlinResult, swiftResult] = await Promise.all([
  queue.add(() => execa('claude', cssArgs, { timeout: 120_000, reject: false })),
  queue.add(() => execa('claude', kotlinArgs, { timeout: 120_000, reject: false })),
  queue.add(() => execa('claude', swiftArgs, { timeout: 120_000, reject: false })),
]);
```

### Output schema (per platform call)

CSS call produces:
```json
{
  "files": {
    "frontend/src/app/tokens.css": "string — full file content"
  },
  "globalsCssPatch": {
    "shClasses": "string — full @layer base block containing .sh-* classes",
    "inlineThemeVars": "string — full @theme inline block"
  },
  "validation": {
    "colorCount": "number",
    "typographyCount": "number",
    "shadowsCount": "number",
    "componentsCount": "number"
  }
}
```

Kotlin call produces:
```json
{
  "files": {
    "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Colors.kt": "string",
    "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Type.kt": "string",
    "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Theme.kt": "string",
    "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Shadows.kt": "string",
    "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Modifiers.kt": "string"
  }
}
```

Swift call produces:
```json
{
  "files": {
    "mobile/iosApp/SkateLab/Theme/SkateLabColors.swift": "string",
    "mobile/iosApp/SkateLab/Theme/SkateLabTypography.swift": "string",
    "mobile/iosApp/SkateLab/Theme/SkateLabTheme.swift": "string",
    "mobile/iosApp/SkateLab/Theme/SkateLabShadows.swift": "string",
    "mobile/iosApp/SkateLab/Theme/SkateLabModifiers.swift": "string"
  }
}
```

### Prompt template

**Architect prompt:**
```
You are a design token architect. Read the DESIGN.md below and produce a shared vocabulary JSON.

RULES:
1. Extract all color names with hex values. Map each to OKLCH.
2. Define semantic aliases (onPrimary = primaryForeground, background = canvas, etc.).
3. Extract the full type scale (size, weight, tracking, line-height for each level).
4. Define shadow tokens (ambient-low, ambient-medium, ambient-high) with CSS box-shadow parameters.
5. Define component tokens (btn-primary, card-default, badge-opaque) mapping to semantic names.
6. Output JSON matching the exact schema.

DESIGN.md:
<full DESIGN.md content>
```

**CSS platform prompt:**
```
You are a CSS design token code generator. Given the shared vocabulary and DESIGN.md below, generate complete CSS files.

RULES:
1. Generate COMPLETE files, not fragments. Each file must be valid and self-contained.
2. Use OKLCH for CSS custom properties. Values from shared vocabulary.
3. Include shadcn semantic aliases in tokens.css (--background: var(--canvas), etc.).
4. Shadow tokens as CSS box-shadow custom properties.
5. Component tokens as .sh-* classes matching current globals.css pattern.
6. Typography as .sh-* classes.
7. Preserve AUTO-GENERATED headers in all files.
8. Output JSON matching the exact schema.

SHARED VOCABULARY:
<architect output>

DESIGN.md:
<full DESIGN.md content>
```

**Kotlin/Swift prompts:** Similar structure, with platform-specific rules (Color(0xFF...) / Color(red:g:b:), Modifier extensions / ViewModifier, etc.)

### Validation

`scripts/design-build.js` validates each platform response:

1. **Schema compliance:** `--json-schema` guarantees valid JSON structure. Verify `finish_reason` is not `"length"` (truncation).
2. **File presence:** All expected file keys exist in response
3. **Count check:** `colorCount >= 23`, `typographyCount >= 14`, `shadowsCount >= 3`, `componentsCount >= 14`
4. **Format check:** CSS files contain `:root {`, Kotlin files contain `package ru.skatelab` + `object SkateLabColors` + `val` keyword, Swift files contain `import SwiftUI` + `extension Color`
5. **Hex check:** All CSS custom properties with hex comments match the hex values in DESIGN.md
6. **OKLCH check:** CSS tokens use `oklch()` format, not raw hex
7. **Cross-platform consistency:** Color names in CSS/Kotlin/Swift match the shared vocabulary from architect call

### Retry strategy

Distinguish error types for appropriate handling:

1. **Validation failure** (malformed output, wrong counts, missing keys):
   - Add error message to prompt: "Previous attempt failed: [specific error]. Fix this issue."
   - Re-run `claude -p` with augmented prompt
   - Maximum 3 attempts

2. **API error** (429 rate limit, 500/502/503/504 server error):
   - Exponential backoff: `min(base * 2^attempt, 30s) + random(0, 500ms)` jitter
   - Maximum 3 attempts

3. **Non-retryable error** (400 bad request, 401/403 auth):
   - Immediate fallback, no retry

4. **All retries exhausted → git checkout fallback**

### Circuit breaker

Track consecutive total failures in `tokens/build.log`:
- After 5 consecutive total failures across runs → skip generation entirely, use `git checkout HEAD`, require manual review
- Reset counter on successful generation
- Prevents burning API credits on a fundamentally broken prompt

### Fallback

On complete LLM failure (CLI error, timeout, all retries exhausted):
- `git checkout HEAD -- <generated-files>` to restore last committed version
- Log error to `tokens/build.log`
- Exit with code 1

## 3. Comment Triggers

DESIGN.md supports HTML comment directives that control what the LLM generates:

| Trigger | Effect |
|---|---|
| `<!-- generate:all -->` | Generate all platform files (default if no triggers) |
| `<!-- generate:tokens -->` | Only base tokens (colors, typography, spacing, radius) |
| `<!-- generate:components -->` | Only component tokens + .sh-* classes |
| `<!-- generate:shadows -->` | Only shadow tokens |
| `<!-- audit:impeccable -->` | Run impeccable detect on frontend/src/ |
| `<!-- audit:hallmark -->` | Run hallmark audit |

The parser (`design-build.js`) scans DESIGN.md for these comments and constructs the prompt accordingly. If no triggers found, defaults to `generate:all`.

## 4. Drift Detection

### Checksum lockfile

`tokens/lock.json` — SHA-256 checksums with source tracking:

```json
{
  "version": 2,
  "timestamp": "2026-05-22T14:30:00Z",
  "designMdHash": "sha256:abc123...",
  "sectionHashes": {
    "colors": "sha256:def...",
    "typography": "sha256:ghi...",
    "shadows": "sha256:jkl...",
    "components": "sha256:mno..."
  },
  "files": {
    "frontend/src/app/tokens.css": "sha256:pqr...",
    "mobile/.../Colors.kt": "sha256:stu...",
    "..."
  },
  "platformHashes": {
    "css": "sha256:vwx...",
    "kotlin": "sha256:yz0...",
    "swift": "sha256:123..."
  }
}
```

**`designMdHash`**: SHA-256 of DESIGN.md content. If unchanged, skip generation entirely ($0 cost, 0ms).

**`sectionHashes`**: Per-section hashes from YAML frontmatter keys. Enable incremental generation — only regenerate platforms affected by changed sections.

**`platformHashes`**: Aggregate hash per platform output. Detect which platform outputs drifted.

### `task design:check`

1. Hash DESIGN.md → compare with `lock.json` `designMdHash`
2. If unchanged → exit 0 (skip generation, no drift possible)
3. If changed → run `task design:build`
4. Compute SHA-256 of each generated file
5. Compare with `tokens/lock.json` per-file hashes
6. If all match → exit 0 (no drift)
7. If any differ → print diff summary, exit 1 (drift detected — run `task design:lock` and commit)

### `task design:lock`

Update `tokens/lock.json` with current checksums + designMdHash. Run after manual review of LLM-generated changes.

## 5. Impeccable Integration

impeccable detect (npm `impeccable` v2.1.9, 29.2k stars) — deterministic UI anti-pattern scanner. No LLM, no API key, exit code 2 on findings. Detects 25+ patterns: AI slop (gradient text, side-stripe, purple gradients), typography (overused fonts, flat hierarchy), color (WCAG, gray-on-color, pure black/white), layout (card-in-card, monotonous spacing), motion (bounce easing, transition-all), quality (tiny text, cramped padding).

### Taskfile

```yaml
design:lint:
  desc: UI anti-pattern scan (impeccable + ast-grep)
  cmds:
    - npx impeccable detect --fast --json frontend/src/ 2>&1 | node scripts/impeccable-report.js
    - ast-grep scan
```

### `scripts/impeccable-report.js`

- Parses impeccable JSON output
- Groups by severity (error → fail, warning → informational)
- Outputs summary to stdout
- Exits with code 1 if any errors found

### Pre-commit hook

Add to `lefthook.yml`:

```yaml
impeccable:
  glob: "frontend/src/**/*.{tsx,jsx,css}"
  run: npx impeccable detect --fast frontend/src/ --json 2>/dev/null | node scripts/impeccable-report.js
```

### CI job

Add `design-lint` job to `.github/workflows/ci-reusable.yml`:
- Trigger: changes in DESIGN.md or frontend/
- Run `npx impeccable detect --json frontend/src/`
- Parse and fail on errors, warn on warnings
- Also runs `ast-grep scan` for structural pattern enforcement

## 6. Ast-grep Expanded Rules

Current 5 design rules → expand to 10-15. New rules from impeccable + hallmark overlap:

| Rule | Catches | ast-grep feasible? |
|---|---|---|
| `no-raw-tailwind-colors` | Raw Tailwind color classes | Yes (existing) |
| `no-backdrop-blur` | Frosted glass | Yes (existing) |
| `no-static-shadow` | Shadows on static elements | Yes (existing) |
| `no-dark-variant` | `dark:` prefix | Yes (existing) |
| `no-raw-font-weights` | `font-bold`/`font-semibold`/`font-medium` | Yes (existing) |
| `no-transition-all` | `transition-all` class or property | Yes (new) |
| `no-uniform-scale-hover` | Uniform `hover:scale-105` | Yes (new) |
| `no-gradient-text` | `bg-gradient-to-r` + `bg-clip-text` | Partially (new) |
| `no-pure-black-white` | Raw `#000`/`#fff` / `black`/`white` | Yes (new) |
| `no-banned-easing` | `cubic-bezier(0.34, 1.56` bounce patterns | Yes (new) |
| `no-banned-font-import` | Inter/Roboto/Open Sans font imports | Yes (new) |

## 7. Hallmark Integration

hallmark (github.com/Nutlope/hallmark) is an LLM skill, NOT a CLI tool. It teaches Claude/Cursor/Codex design quality via 65 slop-test gates. Its audit verb requires `claude -p` — expensive, slow, non-deterministic. Unique value: macrostructure diversification, brand fit, holistic quality judgment that requires LLM reasoning.

Overlaps with impeccable: purple gradients, Inter/Roboto fonts, 3-column cards, card-in-card, gradient text, centered heroes, `transition-all`, pure black/white.

### Taskfile

```yaml
design:audit:
  desc: Deep design quality audit (scheduled/manual only)
  cmds:
    - claude -p "hallmark audit frontend/src/ using DESIGN.md as design system" --bare --output-format json --max-turns 5 --append-system-prompt "<hallmark SKILL.md excerpt>"
```

### Output

Structured JSON report saved to `docs/design-audit.json` (git-ignored):

```json
{
  "timestamp": "2026-05-22T14:30:00Z",
  "scores": {
    "philosophy": 4,
    "hierarchy": 5,
    "execution": 4,
    "specificity": 3,
    "restraint": 5,
    "variety": 3
  },
  "issues": [
    { "severity": "warning", "rule": "pill-outside-hero", "file": "...", "line": 42, "description": "..." }
  ],
  "recommendations": ["..."]
}
```

### CI job

`design-audit` — informational job (allow failure), runs on schedule (weekly) or manual trigger. NOT a CI gate — too slow and non-deterministic for per-PR checks.

## 8. WCAG Validation

### `scripts/design-wcag.js`

- Reads color tokens from generated `tokens.css`
- Defines contrast pairs: ink/canvas, on-dark-faint/badge-bg, etc.
- Computes relative luminance from OKLCH (convert OKLCH → linear sRGB → sRGB → luminance)
- Checks WCAG AA: 4.5:1 for normal text, 3:1 for large text
- Exits 1 if violations found, 0 if all pass
- Run as part of `design:check`

### Known violations to document

- `on-dark-faint` on `badge-opaque` background: fails 4.5:1 — documented in DESIGN.md as known issue

## 9. Taskfile Summary

| Task | Command | Purpose |
|---|---|---|
| `design:build` | `node scripts/design-build.js` | LLM generation of all platform files |
| `design:lint` | `impeccable detect + ast-grep` | UI anti-pattern scan (deterministic) |
| `design:check` | `build + drift + WCAG` | Full validation |
| `design:lock` | `node scripts/design-lock.js` | Update checksum lockfile |
| `design:audit` | `claude -p hallmark` | Deep design audit (manual/scheduled) |
| `design:wcag` | `node scripts/design-wcag.js` | WCAG contrast validation |

## 10. CI Integration

### New CI jobs in `.github/workflows/ci-reusable.yml`

**`design-lint` job** (deterministic, CI gate):
- Trigger: changes in `DESIGN.md` or `frontend/`
- Run `npx impeccable detect --json frontend/src/`
- Run `ast-grep scan`
- Parse impeccable output, fail on errors, warn on warnings
- Exit code determines pass/fail

**`design-check` job** (LLM-dependent, CI gate):
- Trigger: changes in `DESIGN.md`
- Run `task design:check` (build + WCAG + drift)
- Needs `ANTHROPIC_API_KEY` or `OLLAMA_API_KEY` secret
- Fallback on LLM failure: git checkout (non-blocking if DESIGN.md unchanged)

**`design-audit` job** (LLM-dependent, informational, allow failure):
- Schedule: weekly (cron) or manual workflow_dispatch
- Run `task design:audit`
- Save report to `docs/design-audit.json`
- `continue-on-error: true`

### Pre-commit hooks (lefthook.yml)

```yaml
impeccable:
  glob: "frontend/src/**/*.{tsx,jsx,css}"
  run: npx impeccable detect --fast frontend/src/ --json 2>/dev/null | node scripts/impeccable-report.js
```

## 11. Migration from Style Dictionary

1. Delete `style-dictionary.config.js`
2. Delete `tokens/dtcg.json`
3. Remove `style-dictionary` from `package.json` deps
4. Rename `scripts/design-tokens.js` → `scripts/design-build.js` (full rewrite)
5. Create `scripts/impeccable-report.js`
6. Create `scripts/design-wcag.js`
7. Create `scripts/design-lock.js`
8. Create `tokens/lock.json` (initial)
9. Update `Taskfile.yml` design tasks
10. Update `.gitattributes` (remove dtcg.json entry, add lock.json)
11. Update `.github/workflows/ci-reusable.yml` (design-lint, design-check, design-audit jobs)
12. Update `.gitignore` (add `docs/design-audit.json`, `tokens/build.log`)
13. Add new ast-grep rules (no-transition-all, no-uniform-scale-hover, no-pure-black-white, no-banned-easing, no-banned-font-import)
14. Add `execa` + `p-queue` to package.json deps
15. Verify `design:build` → `design:check` pipeline works end-to-end
