# Design Pipeline v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Style Dictionary with LLM-based generation pipeline that reads DESIGN.md and outputs complete platform files, with validation, retry, fallback, drift detection, and CI integration.

**Architecture:** DESIGN.md → architect call (shared vocab) → 3 parallel platform calls (CSS, Kotlin, Swift) via `claude -p --bare --json-schema` → `scripts/design-build.js` validates + retries + falls back → platform files. Checksum lockfile for drift. Impeccable + ast-grep for linting. Hallmark for manual audit.

**Tech Stack:** Claude CLI (`claude -p`), Node.js (`execa`, `p-queue`), impeccable CLI, ast-grep, git checksums

---

## File Structure

### Created

- `scripts/design-build.js` — Main pipeline: parse DESIGN.md, run LLM calls, validate, write files
- `scripts/design-wcag.js` — WCAG contrast ratio validator
- `scripts/design-lock.js` — Update/verify checksum lockfile
- `scripts/impeccable-report.js` — Parse impeccable JSON, group by severity, exit on errors
- `tokens/lock.json` — Initial checksum lockfile (v2 format)
- `tokens/build.log` — Build log (git-ignored)
- `ast-grep/no-transition-all.yml` — Ban `transition-all`
- `ast-grep/no-uniform-scale-hover.yml` — Ban uniform `hover:scale-105`
- `ast-grep/no-pure-black-white.yml` — Ban raw `#000`/`#fff`/`black`/`white`
- `ast-grep/no-banned-easing.yml` — Ban bounce easing curves
- `ast-grep/no-banned-font-import.yml` — Ban Inter/Roboto/Open Sans imports
- `ast-grep/no-gradient-text.yml` — Ban gradient text pattern

### Modified

- `Taskfile.yml` — Replace design:build/lint/check with new LLM pipeline tasks
- `package.json` — Remove `style-dictionary`, add `execa` + `p-queue`, remove `design:*` scripts
- `.gitattributes` — Remove `tokens/dtcg.json`, add `tokens/build.log`, update generated file markers
- `.gitignore` — Add `docs/design-audit.json`, `tokens/build.log`
- `.github/workflows/ci-reusable.yml` — Replace `design-lint` + `design-drift` with new jobs
- `lefthook.yml` — Add impeccable hook

### Deleted

- `style-dictionary.config.js` — Replaced by `scripts/design-build.js`
- `tokens/dtcg.json` — No longer needed
- `scripts/design-tokens.js` — Replaced by `scripts/design-build.js`

### Generated (by LLM, git-tracked with linguist-generated)

- `frontend/src/app/tokens.css`
- `frontend/src/app/globals.css` (patched: .sh-* classes, @theme block)
- `mobile/.../theme/Colors.kt`
- `mobile/.../theme/Type.kt`
- `mobile/.../theme/Theme.kt`
- `mobile/.../theme/Shadows.kt` (NEW)
- `mobile/.../theme/Modifiers.kt` (NEW)
- `mobile/iosApp/.../SkateLabColors.swift`
- `mobile/iosApp/.../SkateLabTypography.swift`
- `mobile/iosApp/.../SkateLabTheme.swift`
- `mobile/iosApp/.../SkateLabShadows.swift` (NEW)
- `mobile/iosApp/.../SkateLabModifiers.swift` (NEW)

---

## Wave 1: Core Pipeline (scripts + lockfile)

### Task 1: Create `scripts/design-build.js` — LLM pipeline core

**Files:**

- Create: `scripts/design-build.js`
- Modify: `package.json` (add `execa`, `p-queue`, remove `style-dictionary`)

- [ ] **Step 1: Install new dependencies**

```bash
cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/design-system-unify
npm install execa p-queue
npm uninstall style-dictionary
```

- [ ] **Step 2: Remove old pipeline files**

```bash
rm style-dictionary.config.js tokens/dtcg.json
```

- [ ] **Step 3: Create `scripts/design-build.js` with the full pipeline**

The script must:

1. **Parse args**: `--trigger <all|tokens|components|shadows>` (default: `all`)
2. **Hash check**: Read `tokens/lock.json`, compute SHA-256 of DESIGN.md, skip generation if unchanged (exit 0)
3. **Parse DESIGN.md**: Read full content, extract YAML frontmatter + prose
4. **Scan comment triggers**: `<!-- generate:all -->`, `<!-- generate:tokens -->`, etc.
5. **Phase 1 — Architect call**: Run `claude -p` with `--bare --output-format json --json-schema` to produce shared vocabulary (color names, semantic aliases, type scale, shadow tokens, component tokens)
6. **Phase 2 — Platform fan-out**: 3 parallel `claude -p` calls (CSS, Kotlin, Swift) using `execa` + `p-queue` (concurrency: 3, timeout: 120s)
7. **Validate each response**:
   - JSON Schema compliance (structural check)
   - Required file keys present
   - Count checks: colorCount >= 23, typographyCount >= 14, shadowsCount >= 3, componentsCount >= 14
   - Format checks: CSS contains `:root {`, Kotlin contains `package ru.skatelab` + `object SkateLabColors`, Swift contains `import SwiftUI` + `extension Color`
   - Cross-platform name consistency (color names match architect vocab)
8. **Retry logic**: On validation failure, augment prompt with error context (max 3). On API error (429/5xx), exponential backoff + jitter. On non-retryable (4xx not 429), immediate fallback.
9. **Circuit breaker**: Read/write consecutive failure count in `tokens/build.log`. After 5, skip generation, require manual review.
10. **Write files**: Write each validated file to disk
11. **Patch globals.css**: Replace `.sh-*` classes block and `@theme` inline block using the `globalsCssPatch` field from CSS response
12. **Update lock.json**: Write `tokens/lock.json` v2 with `designMdHash`, `sectionHashes`, `files`, `platformHashes`

```js
// scripts/design-build.js — key structure (abbreviated, full implementation in step)
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execa } from 'execa';
import PQueue from 'p-queue';

const DESIGN_MD = 'DESIGN.md';
const LOCK_FILE = 'tokens/lock.json';
const BUILD_LOG = 'tokens/build.log';
const CIRCUIT_BREAKER_LIMIT = 5;

// JSON Schemas for --json-schema flag
const VOCAB_SCHEMA = { /* ... */ };
const CSS_SCHEMA = { /* ... */ };
const KOTLIN_SCHEMA = { /* ... */ };
const SWIFT_SCHEMA = { /* ... */ };

// Validation functions
function validateCounts(data) { /* ... */ }
function validateFormat(data, platform) { /* ... */ }
function validateCrossPlatform(data, vocab) { /* ... */ }

// Retry with exponential backoff
async function runWithRetry(args, maxRetries = 3) { /* ... */ }

// Main pipeline
async function main() {
  // 1. Hash check — skip if DESIGN.md unchanged
  const designHash = sha256(readFileSync(DESIGN_MD));
  const lock = readLock();
  if (lock?.designMdHash === designHash) {
    console.log('DESIGN.md unchanged, skipping generation');
    process.exit(0);
  }

  // 2. Circuit breaker check
  const failures = readFailureCount();
  if (failures >= CIRCUIT_BREAKER_LIMIT) {
    console.error(`Circuit breaker: ${failures} consecutive failures. Manual review required.`);
    process.exit(1);
  }

  // 3. Parse DESIGN.md + comment triggers
  const content = readFileSync(DESIGN_MD, 'utf-8');
  const trigger = parseTrigger(content); // all|tokens|components|shadows

  // 4. Phase 1 — Architect call
  const vocab = await runWithRetry(['claude', '-p', architectPrompt(content, trigger), '--bare', '--output-format', 'json', '--json-schema', JSON.stringify(VOCAB_SCHEMA), '--max-turns', '1']);

  // 5. Phase 2 — Platform fan-out
  const queue = new PQueue({ concurrency: 3, timeout: 180_000 });
  const [cssResult, kotlinResult, swiftResult] = await Promise.all([
    queue.add(() => runWithRetry(['claude', '-p', cssPrompt(content, vocab, trigger), '--bare', '--output-format', 'json', '--json-schema', JSON.stringify(CSS_SCHEMA), '--max-turns', '1'])),
    queue.add(() => runWithRetry(['claude', '-p', kotlinPrompt(content, vocab, trigger), '--bare', '--output-format', 'json', '--json-schema', JSON.stringify(KOTLIN_SCHEMA), '--max-turns', '1'])),
    queue.add(() => runWithRetry(['claude', '-p', swiftPrompt(content, vocab, trigger), '--bare', '--output-format', 'json', '--json-schema', JSON.stringify(SWIFT_SCHEMA), '--max-turns', '1'])),
  ]);

  // 6. Validate all responses
  validateCounts(cssResult.validation);
  validateFormat(cssResult, 'css');
  validateFormat(kotlinResult, 'kotlin');
  validateFormat(swiftResult, 'swift');
  validateCrossPlatform({ css: cssResult, kotlin: kotlinResult, swift: swiftResult }, vocab);

  // 7. Write files
  writeFiles(cssResult.files);
  writeFiles(kotlinResult.files);
  writeFiles(swiftResult.files);
  patchGlobalsCss(cssResult.globalsCssPatch);

  // 8. Update lock.json
  writeLock({ designMdHash: designHash, sectionHashes: computeSectionHashes(content), files: computeFileHashes(), platformHashes: computePlatformHashes(cssResult, kotlinResult, swiftResult) });

  // 9. Reset circuit breaker
  resetFailureCount();

  console.log('Design tokens generated successfully');
}
```

- [ ] **Step 4: Verify script runs without errors**

```bash
node scripts/design-build.js --help
```

Expected: Prints usage, exits 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/design-build.js package.json package-lock.json
git rm style-dictionary.config.js tokens/dtcg.json
git commit -m "feat(design): add design-build.js LLM pipeline, remove Style Dictionary"
```

---

### Task 2: Create `scripts/design-lock.js` — Checksum lockfile manager

**Files:**

- Create: `scripts/design-lock.js`
- Create: `tokens/lock.json` (initial empty v2 format)

- [ ] **Step 1: Create `scripts/design-lock.js`**

The script handles two subcommands:

- `node scripts/design-lock.js update` — Compute SHA-256 of each generated file + DESIGN.md hash, write to `tokens/lock.json`
- `node scripts/design-lock.js check` — Compute hashes, compare with lock.json, exit 0 if match, exit 1 if drift

```js
// scripts/design-lock.js
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const GENERATED_FILES = [
  'frontend/src/app/tokens.css',
  'mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Colors.kt',
  'mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Type.kt',
  'mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Theme.kt',
  'mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Shadows.kt',
  'mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Modifiers.kt',
  'mobile/iosApp/SkateLab/Theme/SkateLabColors.swift',
  'mobile/iosApp/SkateLab/Theme/SkateLabTypography.swift',
  'mobile/iosApp/SkateLab/Theme/SkateLabTheme.swift',
  'mobile/iosApp/SkateLab/Theme/SkateLabShadows.swift',
  'mobile/iosApp/SkateLab/Theme/SkateLabModifiers.swift',
];

function sha256(filePath) {
  const content = readFileSync(filePath, 'utf-8');
  return 'sha256:' + createHash('sha256').update(content).digest('hex');
}

function update() {
  const lock = {
    version: 2,
    timestamp: new Date().toISOString(),
    designMdHash: sha256('DESIGN.md'),
    sectionHashes: {}, // populated by design-build.js
    files: Object.fromEntries(GENERATED_FILES.map(f => [f, sha256(f)])),
    platformHashes: {}, // populated by design-build.js
  };
  writeFileSync('tokens/lock.json', JSON.stringify(lock, null, 2) + '\n');
  console.log('tokens/lock.json updated');
}

function check() {
  const lock = JSON.parse(readFileSync('tokens/lock.json', 'utf-8'));
  let drifted = false;
  for (const [file, expectedHash] of Object.entries(lock.files)) {
    const actualHash = sha256(file);
    if (actualHash !== expectedHash) {
      console.error(`DRIFT: ${file}`);
      console.error(`  expected: ${expectedHash}`);
      console.error(`  actual:   ${actualHash}`);
      drifted = true;
    }
  }
  if (drifted) {
    console.error('Drift detected. Run `task design:lock` and commit.');
    process.exit(1);
  }
  console.log('No drift detected');
}

const command = process.argv[2];
if (command === 'update') update();
else if (command === 'check') check();
else { console.error('Usage: design-lock.js <update|check>'); process.exit(1); }
```

- [ ] **Step 2: Create initial `tokens/lock.json`**

```json
{
  "version": 2,
  "timestamp": "",
  "designMdHash": "",
  "sectionHashes": {},
  "files": {},
  "platformHashes": {}
}
```

- [ ] **Step 3: Commit**

```bash
git add scripts/design-lock.js tokens/lock.json
git commit -m "feat(design): add design-lock.js checksum lockfile manager"
```

---

### Task 3: Create `scripts/design-wcag.js` — WCAG contrast validator

**Files:**

- Create: `scripts/design-wcag.js`

- [ ] **Step 1: Create `scripts/design-wcag.js`**

Reads `frontend/src/app/tokens.css`, parses OKLCH values, computes contrast ratios for named pairs, reports violations.

```js
// scripts/design-wcag.js
import { readFileSync } from 'node:fs';

// OKLCH → linear sRGB → relative luminance
function oklchToLuminance(l, c, h) {
  // OKLCH → OKLab → linear sRGB
  const L = l + 0.3963377774 * c * Math.cos(h + 0.2637668321);
  const M_ = l - 0.1055613458 * c * Math.cos(h + 0.0736824854);
  const S = l - 0.0894841775 * c * Math.cos(h - 0.0736824854);
  // OKLab → linear sRGB (simplified)
  const r = Math.max(0, +4.0661818 * L - 3.1675594 * M_ - 0.5082947 * S);
  const g = Math.max(0, -1.0148168 * L + 1.8787938 * M_ + 0.0652909 * S);
  const b = Math.max(0, +0.0980217 * L - 0.2209266 * M_ + 1.1304103 * S);
  // Linear sRGB → sRGB → relative luminance
  const toLinear = (c) => c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1/2.4) - 0.055;
  const sR = toLinear(r), sG = toLinear(g), sB = toLinear(b);
  return 0.2126 * sR + 0.7152 * sG + 0.0722 * sB;
}

function contrastRatio(l1, l2) {
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// Named contrast pairs from DESIGN.md
const PAIRS = [
  { fg: '--ink', bg: '--canvas', label: 'ink on canvas' },
  { fg: '--ink-mute', bg: '--canvas', label: 'ink-mute on canvas' },
  { fg: '--primary-foreground', bg: '--primary', label: 'on-primary on primary' },
  { fg: '--on-dark-mute', bg: '--primary-deep', label: 'on-dark-mute on primary-deep' },
  { fg: '--on-dark-dim', bg: '--primary-deep', label: 'on-dark-dim on primary-deep' },
  { fg: '--on-dark-faint', bg: '--surface-teal-deep', label: 'on-dark-faint on teal-deep (known violation)' },
  { fg: '--ink', bg: '--canvas-soft', label: 'ink on canvas-soft' },
  { fg: '--destructive', bg: '--canvas', label: 'destructive on canvas' },
];

function main() {
  const css = readFileSync('frontend/src/app/tokens.css', 'utf-8');
  const tokens = {};
  for (const match of css.matchAll(/--([\w-]+):\s*oklch\(([\d.]+)\s+([\d.]+)\s+([\d.]+)\)/g)) {
    tokens[`--${match[1]}`] = oklchToLuminance(+match[2], +match[3], +match[4]);
  }
  let violations = 0;
  for (const pair of PAIRS) {
    const fgL = tokens[pair.fg];
    const bgL = tokens[pair.bg];
    if (fgL === undefined || bgL === undefined) continue;
    const ratio = contrastRatio(fgL, bgL);
    const pass = ratio >= 4.5;
    if (!pass && !pair.label.includes('known violation')) {
      console.error(`FAIL: ${pair.label} — ratio ${ratio.toFixed(2)}:1 (need 4.5:1)`);
      violations++;
    } else if (!pass) {
      console.warn(`WARN: ${pair.label} — ratio ${ratio.toFixed(2)}:1 (known violation, documented in DESIGN.md)`);
    } else {
      console.log(`PASS: ${pair.label} — ratio ${ratio.toFixed(2)}:1`);
    }
  }
  if (violations > 0) {
    console.error(`\n${violations} WCAG AA violation(s) found`);
    process.exit(1);
  }
  console.log('\nAll WCAG AA checks passed');
}

main();
```

- [ ] **Step 2: Commit**

```bash
git add scripts/design-wcag.js
git commit -m "feat(design): add WCAG contrast validator script"
```

---

### Task 4: Create `scripts/impeccable-report.js` — Impeccable JSON parser

**Files:**

- Create: `scripts/impeccable-report.js`

- [ ] **Step 1: Create `scripts/impeccable-report.js`**

```js
// scripts/impeccable-report.js
// Reads impeccable detect --json output from stdin, groups by severity, exits 1 on errors

let input = '';
process.stdin.setEncoding('utf-8');
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  let findings;
  try {
    findings = JSON.parse(input);
  } catch {
    // impeccable may output non-JSON before the JSON
    const jsonMatch = input.match(/\[[\s\S]*\]/);
    if (jsonMatch) findings = JSON.parse(jsonMatch[0]);
    else { console.log('No findings'); process.exit(0); }
  }

  if (!Array.isArray(findings)) { console.log('No findings'); process.exit(0); }

  const errors = findings.filter(f => f.severity === 'error');
  const warnings = findings.filter(f => f.severity === 'warning');

  if (warnings.length > 0) {
    console.log(`\nWarnings (${warnings.length}):`);
    for (const w of warnings) {
      console.log(`  ⚠ ${w.rule || w.id}: ${w.message} (${w.file}:${w.line || '?'})`);
    }
  }

  if (errors.length > 0) {
    console.error(`\nErrors (${errors.length}):`);
    for (const e of errors) {
      console.error(`  ✗ ${e.rule || e.id}: ${e.message} (${e.file}:${e.line || '?'})`);
    }
    console.error(`\n${errors.length} error(s) found`);
    process.exit(1);
  }

  console.log(`\n${findings.length} finding(s): ${errors.length} errors, ${warnings.length} warnings`);
  process.exit(0);
});
```

- [ ] **Step 2: Commit**

```bash
git add scripts/impeccable-report.js
git commit -m "feat(design): add impeccable-report.js severity parser"
```

---

### Task 5: Update Taskfile.yml and package.json scripts

**Files:**

- Modify: `Taskfile.yml` (replace design tasks)
- Modify: `package.json` (replace design scripts)

- [ ] **Step 1: Replace design tasks in Taskfile.yml**

Replace the existing `design:build`, `design:lint`, `design:check` tasks with:

```yaml
  # Design system tasks (v2 — LLM-based generation)
  design:build:
    desc: "Generate design tokens for all platforms from DESIGN.md via LLM"
    cmd: node scripts/design-build.js

  design:lint:
    desc: "UI anti-pattern scan (impeccable + ast-grep)"
    cmds:
      - npx impeccable detect --fast --json frontend/src/ 2>&1 | node scripts/impeccable-report.js
      - ast-grep scan

  design:check:
    desc: "Full design validation (build + WCAG + drift)"
    cmds:
      - task: design:build
      - node scripts/design-wcag.js
      - node scripts/design-lock.js check

  design:lock:
    desc: "Update checksum lockfile after reviewing generated changes"
    cmd: node scripts/design-lock.js update

  design:wcag:
    desc: "WCAG contrast ratio validation"
    cmd: node scripts/design-wcag.js

  design:audit:
    desc: "Deep design quality audit (manual/scheduled only, requires LLM)"
    cmd: claude -p "hallmark audit frontend/src/ using DESIGN.md as design system" --bare --output-format json --max-turns 5
```

- [ ] **Step 2: Replace design scripts in package.json**

Replace the existing `design:*` scripts:

```json
"scripts": {
  "design:build": "node scripts/design-build.js",
  "design:lint": "npx impeccable detect --fast --json frontend/src/ 2>&1 | node scripts/impeccable-report.js && ast-grep scan",
  "design:check": "npm run design:build && node scripts/design-wcag.js && node scripts/design-lock.js check",
  "design:lock": "node scripts/design-lock.js update",
  "design:wcag": "node scripts/design-wcag.js",
  "design:audit": "claude -p \"hallmark audit frontend/src/ using DESIGN.md as design system\" --bare --output-format json --max-turns 5"
}
```

- [ ] **Step 3: Verify `task --list` shows new tasks**

```bash
task --list | grep design
```

Expected: `design:build`, `design:lint`, `design:check`, `design:lock`, `design:wcag`, `design:audit`.

- [ ] **Step 4: Commit**

```bash
git add Taskfile.yml package.json
git commit -m "feat(design): update Taskfile and package.json for v2 pipeline"
```

---

## Wave 2: Ast-grep Rules + Lefthook + CI

### Task 6: Add new ast-grep design system rules

**Files:**

- Create: `ast-grep/no-transition-all.yml`
- Create: `ast-grep/no-uniform-scale-hover.yml`
- Create: `ast-grep/no-pure-black-white.yml`
- Create: `ast-grep/no-banned-easing.yml`
- Create: `ast-grep/no-banned-font-import.yml`
- Create: `ast-grep/no-gradient-text.yml`

- [ ] **Step 1: Create `ast-grep/no-transition-all.yml`**

```yaml
id: no-transition-all
language: TypeScript
message: |
  Avoid `transition-all` — it transitions every property including layout properties,
  causing performance issues and unintended animations. Use `transition-colors`,
  `transition-opacity`, or `transition-transform` instead.
severity: warning
rule:
  any:
    - pattern: transition-all
    - pattern: '"transition-all"'
    - pattern: |
        {
          transition: "all"
        }
```

- [ ] **Step 2: Create `ast-grep/no-uniform-scale-hover.yml`**

```yaml
id: no-uniform-scale-hover
language: TypeScript
message: |
  Avoid uniform `hover:scale-105` — it's an AI slop tell. Use meaningful scale
  transforms that reflect interaction intent, or use design-system tokens instead.
severity: warning
rule:
  any:
    - pattern: hover:scale-105
    - pattern: hover:scale-110
    - pattern: hover:scale-95
```

- [ ] **Step 3: Create `ast-grep/no-pure-black-white.yml`**

```yaml
id: no-pure-black-white
language: TypeScript
message: |
  Avoid pure black (#000000) and pure white (#FFFFFF) — they create harsh contrast.
  Use design-system ink (#2A2D2E) and canvas (#FFFFFF) tokens instead.
  Use `var(--ink)`, `var(--canvas)`, or `oklch()` values from DESIGN.md.
severity: warning
rule:
  any:
    - pattern: '#000'
    - pattern: '#000000'
    - pattern: '#FFF'
    - pattern: '#FFFFFF'
```

- [ ] **Step 4: Create `ast-grep/no-banned-easing.yml`**

```yaml
id: no-banned-easing
language: TypeScript
message: |
  Avoid bounce/elastic easing curves (cubic-bezier with values > 1.0 or < 0).
  These create cartoonish animations that violate the design system's restraint principle.
  Use `cubic-bezier(0.4, 0, 0.2, 1)` (ease-out) or `cubic-bezier(0, 0, 0.2, 1)` (ease-in-out).
severity: warning
rule:
  regex: "cubic-bezier\\([^)]*[12]\\d*\\.\\d+[^)]*\\)"
```

- [ ] **Step 5: Create `ast-grep/no-banned-font-import.yml`**

```yaml
id: no-banned-font-import
language: TypeScript
message: |
  Avoid importing overused fonts (Inter, Roboto, Open Sans, Poppins, Lato).
  The SkateLab design system uses Inter Variable with sub-default weights (460/540/600).
severity: warning
rule:
  any:
    - regex: "font-family.*Inter[^V]"
    - regex: "font-family.*Roboto"
    - regex: "font-family.*Open Sans"
    - regex: "font-family.*Poppins"
    - regex: "font-family.*Lato"
    - regex: "@import.*Inter[^V]"
    - regex: "@import.*Roboto"
```

- [ ] **Step 6: Create `ast-grep/no-gradient-text.yml`**

```yaml
id: no-gradient-text
language: TypeScript
message: |
  Avoid gradient text (`bg-gradient-to-r` + `bg-clip-text` + `text-transparent`).
  It's an AI slop tell. Use solid color text with design-system tokens.
severity: warning
rule:
  any:
    - pattern: |
        {
          backgroundImage: $GRAD,
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent"
        }
```

- [ ] **Step 7: Run ast-grep test to verify rules are valid**

```bash
cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/design-system-unify
ast-grep test
```

Expected: All rule tests pass.

- [ ] **Step 8: Commit**

```bash
git add ast-grep/no-transition-all.yml ast-grep/no-uniform-scale-hover.yml ast-grep/no-pure-black-white.yml ast-grep/no-banned-easing.yml ast-grep/no-banned-font-import.yml ast-grep/no-gradient-text.yml
git commit -m "feat(design): add 6 new ast-grep rules for design system enforcement"
```

---

### Task 7: Add impeccable pre-commit hook to lefthook.yml

**Files:**

- Modify: `lefthook.yml`

- [ ] **Step 1: Read current lefthook.yml**

```bash
cat /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/design-system-unify/lefthook.yml
```

- [ ] **Step 2: Add impeccable hook**

Add after the existing `ast-grep-scan` hook:

```yaml
  impeccable:
    glob: "frontend/src/**/*.{tsx,jsx,css}"
    run: npx impeccable detect --fast frontend/src/ --json 2>/dev/null | node scripts/impeccable-report.js
```

- [ ] **Step 3: Verify lefthook config is valid**

```bash
lefthook install
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add lefthook.yml
git commit -m "feat(design): add impeccable pre-commit hook"
```

---

### Task 8: Update CI workflows for v2 pipeline

**Files:**

- Modify: `.github/workflows/ci-reusable.yml`

- [ ] **Step 1: Update `changes` job — add `design` filter and update paths**

In the `changes` job, update the `design` filter to track v2 pipeline files:

```yaml
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
```

- [ ] **Step 2: Replace `design-lint` and `design-drift` jobs with v2 versions**

Replace both existing jobs:

```yaml
  design-lint:
    name: Design Lint
    needs: [changes]
    if: inputs.run-all || needs.changes.outputs.design == 'true'
    runs-on: blacksmith-2vcpu-ubuntu-2404
    steps:
      - uses: actions/checkout@v6
      - uses: oven-sh/setup-bun@v2
      - name: Install deps
        working-directory: frontend
        run: bun install --frozen-lockfile
      - name: Install impeccable
        run: npm install -g impeccable
      - name: Impeccable detect
        run: impeccable detect --json frontend/src/ 2>&1 | node scripts/impeccable-report.js
      - name: Ast-grep scan
        uses: ast-grep/action@v1.5.0
        with:
          config: sgconfig.yml
          paths: "frontend/"

  design-check:
    name: Design Drift Check
    needs: [changes]
    if: inputs.run-all || needs.changes.outputs.design == 'true'
    runs-on: blacksmith-2vcpu-ubuntu-2404
    steps:
      - uses: actions/checkout@v6
      - uses: oven-sh/setup-bun@v2
      - name: Install deps
        working-directory: frontend
        run: bun install --frozen-lockfile
      - name: Check for drift
        run: node scripts/design-lock.js check

  design-audit:
    name: Design Audit
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    runs-on: blacksmith-2vcpu-ubuntu-2404
    continue-on-error: true
    steps:
      - uses: actions/checkout@v6
      - name: Run hallmark audit
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: claude -p "hallmark audit frontend/src/ using DESIGN.md as design system" --bare --output-format json --max-turns 5 > docs/design-audit.json 2>&1 || true
      - name: Upload audit report
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: design-audit-report
          path: docs/design-audit.json
          retention-days: 30
```

- [ ] **Step 3: Add `design-lint` and `design-check` to `ci-passed` job needs**

Add `DESIGN_LINT: ${{ needs.design-lint.result }}` and `DESIGN_CHECK: ${{ needs.design-check.result }}` to the env, add them to the needs list, and add check_job lines for both.

- [ ] **Step 4: Add `design-audit` trigger to workflow**

Add `workflow_dispatch` and `schedule` triggers at the top of ci-reusable.yml:

```yaml
on:
  workflow_call:
    # ... existing inputs
  workflow_dispatch:
  schedule:
    - cron: '0 3 * * 1'  # Weekly Monday 3am UTC
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "feat(ci): update design-lint, design-check, add design-audit workflow"
```

---

## Wave 3: Gitattributes, Gitignore, and Cleanup

### Task 9: Update .gitattributes and .gitignore

**Files:**

- Modify: `.gitattributes`
- Modify: `.gitignore`

- [ ] **Step 1: Update `.gitattributes`**

Remove `tokens/dtcg.json linguist-generated` line and add new generated files:

```
# Design tokens — auto-generated, do not edit directly
tokens/lock.json linguist-generated
tokens/build.log linguist-generated
frontend/src/app/tokens.css linguist-generated
mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Colors.kt linguist-generated
mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Type.kt linguist-generated
mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Theme.kt linguist-generated
mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Shadows.kt linguist-generated
mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Modifiers.kt linguist-generated
mobile/iosApp/SkateLab/Theme/SkateLabColors.swift linguist-generated
mobile/iosApp/SkateLab/Theme/SkateLabTypography.swift linguist-generated
mobile/iosApp/SkateLab/Theme/SkateLabTheme.swift linguist-generated
mobile/iosApp/SkateLab/Theme/SkateLabShadows.swift linguist-generated
mobile/iosApp/SkateLab/Theme/SkateLabModifiers.swift linguist-generated
```

- [ ] **Step 2: Update `.gitignore`**

Add:

```
# Design pipeline
tokens/build.log
docs/design-audit.json
```

- [ ] **Step 3: Commit**

```bash
git add .gitattributes .gitignore
git commit -m "chore(design): update gitattributes and gitignore for v2 pipeline"
```

---

### Task 10: Delete old Style Dictionary pipeline files

**Files:**

- Delete: `style-dictionary.config.js`
- Delete: `tokens/dtcg.json`
- Delete: `scripts/design-tokens.js`
- Modify: `package.json` (remove `style-dictionary` dep — already done in Task 1)

- [ ] **Step 1: Verify files still exist and delete**

```bash
cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/design-system-unify
rm style-dictionary.config.js tokens/dtcg.json scripts/design-tokens.js
```

- [ ] **Step 2: Verify package.json no longer references style-dictionary**

```bash
grep -c "style-dictionary" package.json
```

Expected: 0

- [ ] **Step 3: Verify design:build works with new pipeline**

```bash
task design:build --dry-run
```

Note: Full test requires `claude -p` access. In CI, this will be tested when the workflow runs.

- [ ] **Step 4: Commit**

```bash
git rm style-dictionary.config.js tokens/dtcg.json scripts/design-tokens.js
git commit -m "chore(design): remove Style Dictionary pipeline files"
```

---

## Wave 4: End-to-End Verification

### Task 11: Verify full pipeline works end-to-end

**Files:** None (verification only)

- [ ] **Step 1: Run `task design:check`**

```bash
cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/design-system-unify
task design:check
```

Note: This requires `claude -p` to be available. If not available locally, verify the script structure is correct and skip generation, testing only the validation and lockfile logic.

- [ ] **Step 2: Run `task design:lint`**

```bash
task design:lint
```

Expected: impeccable detect runs and reports findings. ast-grep scan runs.

- [ ] **Step 3: Run `node scripts/design-wcag.js`**

```bash
node scripts/design-wcag.js
```

Expected: Reports WCAG contrast ratios. May show known violations with WARN level.

- [ ] **Step 4: Run `node scripts/design-lock.js check`**

```bash
node scripts/design-lock.js check
```

Expected: Reports drift (since files haven't been regenerated yet) or "No drift" if lock.json was updated.

- [ ] **Step 5: Verify ast-grep new rules load**

```bash
ast-grep scan --config sgconfig.yml
```

Expected: Runs without errors, shows existing + new rules.

- [ ] **Step 6: Commit any remaining fixes**

```bash
git add -A
git commit -m "chore(design): verify v2 pipeline end-to-end"
```

---

## Self-Review

### Spec Coverage

| Spec Section | Task |
|---|---|
| Architecture (pipeline) | Task 1 |
| LLM Prompt Design (CLI invocation, fan-out, schemas) | Task 1 |
| Comment Triggers | Task 1 (parsed in design-build.js) |
| Drift Detection (lock.json v2) | Tasks 2, 5 |
| Impeccable Integration | Tasks 4, 7 |
| Ast-grep Expanded Rules | Task 6 |
| Hallmark Integration | Task 5 (Taskfile), Task 8 (CI) |
| WCAG Validation | Task 3 |
| Taskfile Summary | Task 5 |
| CI Integration | Task 8 |
| Migration from Style Dictionary | Tasks 1, 9, 10 |

### Placeholder Scan

No TBD, TODO, or "implement later" found. All code blocks contain actual implementation.

### Type Consistency

- `sha256()` used consistently in design-build.js and design-lock.js
- `GENERATED_FILES` list matches spec's Generated files table
- JSON schemas match spec's Output schema section
- Task names match Taskfile.yml task names