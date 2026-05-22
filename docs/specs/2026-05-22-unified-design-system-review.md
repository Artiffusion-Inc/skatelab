# Unified Design System: Agent Review Report

> **Date:** 2026-05-22
> **Scope:** Critical review of `docs/specs/2026-05-22-unified-design-system-design.md` by 5 specialized agents
> **Verdict:** Spec needs significant revisions before implementation

## Blocking Issues (Must Fix)

### B1. OKLCH/Hex Data Integrity — ALL OKLCH values are wrong

Every OKLCH value in DESIGN.md produces a different color than its paired hex value. Examples:

| Token | DESIGN.md OKLCH | Computed from hex | Hex | Delta |
|---|---|---|---|---|
| primary | oklch(0.52 0.08 205) | oklch(0.452 0.075 221) | #155f73 | Significant |
| primary-deep | oklch(0.2 0.04 220) | oklch(0.284 0.042 220) | #0e3340 | Significant |
| ink | oklch(0.278 0.003 220) | oklch(0.278 0.010 260) | #2a2d2e | Moderate |
| canvas-soft | oklch(0.985 0.005 133) | oklch(0.955 0.003 260) | #f5f7f8 | Significant |

**Decision needed:** Hex is canonical (matches current globals.css). OKLCH values must be regenerated from hex using `colorjs.io`. The DESIGN.md prose OKLCH values are approximate and must be replaced with computed values.

**Impact:** Without this, the Style Dictionary pipeline produces different colors than what developers see in DESIGN.md.

### B2. iOS Typography is Non-Functional

The spec's `Font.Weight` extension with custom `init(_ value: Int)` **does not compile**. SwiftUI's `Font.Weight` is an opaque struct with no public initializer for custom values.

**Fix:** Use `CTFont` descriptor approach:

```swift
@available(iOS 15, *)
extension Font {
    static func skateVariable(size: CGFloat, weight: Double) -> Font {
        let wghtAxis = Int(2003265652) // 'wght' as Int
        let descriptor = CTFontDescriptorCreateWithAttributes([
            kCTFontNameAttribute: "InterVariable" as CFString,
            kCTFontVariationAttribute: [wghtAxis: weight] as CFDictionary
        ] as CFDictionary)
        let ctFont = CTFontCreateWithFontDescriptor(descriptor, size, nil)
        return Font(ctFont)
    }
}
```

**Impact:** The entire iOS typography system as specified is broken and must be rewritten.

### B3. `@theme inline` Bridge Not Addressed

`globals.css` has three overlapping blocks: `@theme { }`, `@theme inline { }`, and `:root { }`. The `@theme inline` block bridges `:root` variables to Tailwind theme variables (e.g., `--color-foreground: var(--foreground)`). The spec says "move `@theme { }` and `:root { }` to `tokens.css`" but doesn't address what happens to `@theme inline`.

If both `tokens.css` (`@theme { --radius-md: 8px }`) and `globals.css` (`@theme inline { --radius-md: var(--radius) }`) define the same variable, the `inline` declaration wins — silently overriding generated tokens.

**Fix options:**
- **(A)** Keep `@theme inline` in `globals.css`, update `:root` values from DESIGN.md, don't put conflicting radius/color tokens in `tokens.css @theme { }`. Tokens.css only contains `:root { }` block.
- **(B)** Eliminate `@theme inline`, make `@theme { }` the sole source, update all shadcn components from `var(--foreground)` to `var(--color-foreground)`.
- **(C)** Keep `@theme inline` but make it reference `tokens.css` variables instead of `:root`.

**Recommendation:** Option (A) is safest. The `@theme inline` bridge stays, and `tokens.css` only generates `:root { }` variables. The `@theme { }` block remains in `globals.css` referencing `:root` vars (current pattern, just with corrected values).

### B4. Border-Radius Drift is a Visual Breaking Change

| Token | Current | Proposed | Usage count |
|---|---|---|---|
| `--radius-md` | 20px | 8px | 36 (including 9 shadcn components) |
| `--radius-lg` | 30px | 12px | 58 |
| `--radius-xl` | 30px | 16px | 55 |
| `--radius-2xl` | 36px | 30px | 40 |

Changing `--radius-md` from 20px to 8px turns every dropdown, button, and card from "gently rounded" to "nearly square." This is not a "fix" — it's a visual redesign.

**Fix:** Separate Phase 2 into:
- Phase 2a: Token extraction (no visual changes)
- Phase 2b: Visual refresh (radius + color drift fixes, with visual regression testing)

Consider intermediate values: `--radius-md: 12px` (not 8px), `--radius-lg: 16px` (not 12px).

### B5. `toMaterialTypography()` Not Defined

Theme.kt calls `SkateLabTypographyDefaults.toMaterialTypography()` but this extension function is never defined. The file won't compile.

**Fix:** Define the mapping (13 SkateLab styles → 15 Material 3 roles, with defaults for headlineSmall, titleSmall, bodySmall).

## High-Severity Issues

### H1. `@google/design.md` CLI is Alpha (v0.1.1)

- **Exit code 1 on success** — breaks `set -e` pipelines. Must redirect stdout and ignore exit code.
- **No `--output` flag** — spec proposes `--output tokens/dtcg.json` but CLI only supports stdout. Must use shell redirect: `npx @google/design.md@0.1.1 export --format dtcg DESIGN.md > tokens/dtcg.json || true`
- **Components section not exported** — `export --format dtcg` drops the entire `components` block. Component tokens must be handled separately.
- **Typography loses lineHeight** — DTCG export omits `lineHeight` for all typography tokens. Must be added back manually or via custom post-processing.

### H2. Design Jobs Should Be Informational (Not Blocking)

Both `design-lint` and `design-drift` should start as informational (like `ast-grep`), not blocking. Graduate to blocking after 30 days of clean runs.

They should run **in parallel** (not sequentially) since `design-drift` will fail anyway if `design-lint` fails (build step will error out).

### H3. `no-pill-outside-hero` Contradicts Spec's Own Components

The rule catches ALL `rounded-full` usage, but the spec defines `pill-tab-light` with `rounded: "{rounded.full}"` and `button-on-dark-pill` with `rounded: "{rounded.full}"`. Avatars, progress bars, and badges also use `rounded-full` legitimately.

**Fix:** Drop this rule or reduce to `severity: hint`. Signal-to-noise ratio is too poor.

### H4. `no-canvas-soft-section` Has Too Many False Positives

The rule catches `bg-canvas-soft` on cards, buttons, and cookie banners — not just section backgrounds. ast-grep cannot determine DOM hierarchy.

**Fix:** Reduce to `severity: hint`. Pair with code review guidelines.

### H5. Material 3 Color Mapping Semantic Errors

Several mappings violate Material 3 semantics:
- `tertiary = surfaceIceSoft` — surface color used as accent fill
- `onSecondary = canvas` (white on inkMute) — fails WCAG AA
- `onPrimaryContainer = onPrimary` (white on surfaceTealMid) — 3.4:1 contrast ratio, fails WCAG AA
- `surfaceVariant = canvasSoft`, `onSurfaceVariant = inkMute` — 3.7:1 contrast ratio, fails WCAG AA

**Fix:** Document that SkateLab components should use `SkateLabTheme.colors.*` directly, not Material 3 color roles. The `lightColorScheme` is a best-effort bridge for standard Material 3 components.

### H6. Android Variable Font Fallback Missing

`FontVariation.Settings` requires API 28+. On API 26-27, variable fonts load but axes are ignored. Below API 26, variable fonts don't load at all.

**Fix:** Bundle static Inter font files (Regular 400, Medium 500, SemiBold 600, Bold 700) as fallback. Map 460→Medium, 540→SemiBold on API <28.

### H7. Missing Considerations in Spec

- `.impeccable/design.json` — The `impeccable` tool reads this file. If deleted, impeccable loses design system knowledge. Must either regenerate from DESIGN.md or keep and update.
- `@theme inline` contains sidebar tokens (`--color-sidebar-*`), chart colors (`--color-chart-*`), and semantic bridges that have no home in DESIGN.md.
- `@OptIn(ExperimentalTextApi::class)` missing from Android Type.kt for `FontVariation.Settings`.
- iOS minimum target should be iOS 15, not iOS 16 (no OKLCH API needed; sRGB works on iOS 13+).
- `bodyStrong` fontSize of 18.72sp is unusual and looks like a conversion artifact.

## Medium-Severity Issues

### M1. Style Dictionary Built-in Formats Inadequate

- Kotlin `compose/object`: outputs `object {` not `object SkateLabColors {`, `9999px → 159984dp`, typography as `[object Object]`
- Swift `ios-swift/class.swift`: same dimension/typography issues, uses `UIColor` not `Color`
- CSS: typography tokens lose `letterSpacing`, `lineHeight`, `fontVariantNumeric`

**Fix:** Custom format templates are mandatory. This is more work than the spec implies — estimate 2-3 focused sessions for Kotlin and Swift templates.

### M2. CI Drift Check Needs Hardening

- Pin `@google/design.md@0.1.1` and `style-dictionary` versions
- Pin Node.js version in drift job
- Normalize JSON with `jq -S` before diffing
- Add `.gitattributes` for generated files with `linguist-generated`
- `design-drift` needs `setup-node` step (missing from spec)
- Consider running on push-to-master only initially, not on every PR

### M3. ast-grep Rule Improvements

- `no-raw-font-weights`: Add `font-thin`, `font-extralight`, `font-light`, `font-normal`
- `no-backdrop-blur`: Add negative lookahead for `-none`, ignore config files
- `no-static-shadow`: Remove `inner` from regex (inset shadows are different), add ignores for `frontend/src/components/ui/**`
- `no-pill-outside-hero`: Drop or reduce to `severity: hint`
- `no-canvas-soft-section`: Reduce to `severity: hint`

### M4. Design Filter Needs Broader Coverage

Add to `design` changes filter:
- `sgconfig.yml` and `ast-grep/*.yml`
- `Taskfile.yaml` (contains `design:build` task)
- Generated output files (to catch manual edits)
- `frontend/src/app/tokens.css`

## Low-Severity Issues

### L1. DESIGN.md Lint Errors

Current DESIGN.md has 6 lint errors:
- `clamp()` not valid dimension (display-xxl, display-xl, price)
- `{colors.on-primary}` reference doesn't resolve (should be `{colors.primary-foreground}`)

Must fix before `design.md lint` can pass in CI.

### L2. Design Jobs Should Use `npx`, Not `npm install -g`

Use `npx @google/design.md@0.1.1 lint DESIGN.md` with cached npx directory. Add cache step for `~/.npm/_npx`.

### L3. Consider `no-dark-variant` ast-grep Rule

Since DESIGN.md says "dark mode disabled," add a `severity: hint` rule catching `dark:` Tailwind variants outside `frontend/src/components/ui/**`.

## Revised Phase Plan

### Phase 1: Foundation (no visual changes)
1. Fix OKLCH values in DESIGN.md (regenerate from hex using colorjs.io)
2. Fix DESIGN.md lint errors (`clamp()` refs, `{colors.on-primary}`)
3. Restructure DESIGN.md YAML frontmatter to Google Stitch spec
4. Add `style-dictionary.config.js` with custom format templates
5. Add `task design:build` to Taskfile.yaml
6. Write custom Python/YAML parser as fallback for DESIGN.md CLI
7. Generate all platform tokens, verify values match hex canonicals

### Phase 2a: Frontend extraction (no visual changes)
1. Extract `:root { }` to `tokens.css` (generated)
2. Keep `@theme { }` and `@theme inline { }` in `globals.css`
3. Keep all current visual values unchanged
4. Add `@import "./tokens.css"` to `globals.css`
5. Verify frontend builds and renders identically

### Phase 2b: Visual refresh (separate, with regression testing)
1. Fix border-radius values (consider intermediate: md=12px, lg=16px)
2. Fix color drift (foreground, ink-faint, canvas-soft)
3. Visual regression testing before/after
4. Update shadcn components affected by radius changes

### Phase 3: Mobile integration
1. Replace AppTheme.kt with generated SkateLabColors/Type/Theme
2. Bundle Inter Variable font + static fallbacks in Android res/font/
3. Use CTFont descriptor approach for iOS typography
4. Bundle Inter Variable font in iOS Assets.xcassets/
5. Add `@OptIn(ExperimentalTextApi::class)` to Android Type.kt
6. Define `toMaterialTypography()` extension function
7. Document that SkateLab theme colors should be used directly, not Material 3 roles

### Phase 4: CI enforcement
1. Add `design-lint` job (informational, parallel to lint)
2. Add `design-drift` job (informational, parallel, not dependent on design-lint)
3. Add 5 ast-grep rules with corrected patterns and severity levels
4. Add `design` filter with broad coverage
5. Graduate to blocking after 30 days clean

### Phase 5: Cleanup
1. Update or delete `.impeccable/design.json`
2. Handle sidebar/chart tokens not in DESIGN.md (add to DESIGN.md or document as shadcn-only)
3. Update CLAUDE.md with design system workflow