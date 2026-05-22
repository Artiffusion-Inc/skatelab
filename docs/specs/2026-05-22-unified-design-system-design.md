# Unified Design System: Gentle Sea Breeze

> **Status:** Revised (post-agent-review)
> **Date:** 2026-05-22
> **Scope:** Web (Next.js + Tailwind), Android (Kotlin Compose), iOS (SwiftUI)
> **Approach:** A — DESIGN.md → DTCG → Style Dictionary
> **Review:** See `2026-05-22-unified-design-system-review.md` for agent findings

## 1. Overview

Single source of truth: DESIGN.md. YAML frontmatter holds all tokens (hex canonical). Markdown body holds rationale and rules. All platform code (CSS, Kotlin, Swift) is generated from DESIGN.md via Style Dictionary. Manual edits to generated files are overwritten on next build.

### Canonical Color Source

**Hex values are canonical.** OKLCH values in DESIGN.md prose are approximations and will be regenerated from hex using `colorjs.io` during pipeline setup. All platform output derives from hex → OKLCH (CSS) or hex → sRGB float (Kotlin/Swift).

### Design Decisions

| Decision | Choice | Why |
|---|---|---|
| Single source of truth | DESIGN.md YAML frontmatter (hex canonical) | Human + AI readable; Google Stitch spec; rationale alongside tokens |
| Code generation | DESIGN.md → DTCG → Style Dictionary | SD mature, DTCG native since v4; custom templates for Kotlin/Swift |
| Fallback | Custom YAML parser (`scripts/design-tokens.js`) | `@google/design.md` CLI is alpha v0.1.1 — self-owned parser eliminates dependency |
| Color space | Hex canonical, OKLCH computed for CSS, sRGB for mobile | OKLCH values in prose were inaccurate; hex matches production |
| Typography | Inter Variable with sub-default weights (460/540/600) | Brand signature; 700 for buttons/body-strong only |
| Dark mode | Disabled until properly implemented | Per DESIGN.md rule |
| `@theme inline` bridge | Stays in `globals.css`; `tokens.css` generates only `:root { }` | Safest — no conflict with Tailwind v4 theme resolution; shadcn components unbroken |
| iOS minimum target | iOS 15 | sRGB `Color(red:green:blue:)` works on iOS 13+; no OKLCH API needed |
| Font weight fallback | Static Inter files (400/500/600/700) for Android API <28 and iOS | Variable font axes unreliable on older Android; SwiftUI `Font.Weight` is opaque |

## 2. Generation Pipeline

### Architecture

```
DESIGN.md (hex canonical)
  │
  ├── scripts/design-tokens.js parse → tokens/dtcg.json
  │   (fallback: npx @google/design.md@0.1.1 export --format dtcg)
  │
  └── npx style-dictionary@5.4.1 build
        └── tokens/dtcg.json
              │
              ├── css → frontend/src/app/tokens.css (:root { } block, OKLCH values)
              ├── android → mobile/.../theme/Colors.kt (hex Color(0xFF...))
              │              mobile/.../theme/Type.kt
              │              mobile/.../theme/Theme.kt
              └── ios → mobile/iosApp/.../Theme/SkateLabColors.swift (sRGB floats)
                        mobile/iosApp/.../Theme/SkateLabTypography.swift (CTFont approach)
                        mobile/iosApp/.../Theme/SkateLabTheme.swift
```

### Custom YAML Parser (`scripts/design-tokens.js`)

Primary path: ~80-line Node.js script using `yaml` + `colorjs.io`:
1. Parse DESIGN.md YAML frontmatter
2. Convert hex colors to DTCG format with computed OKLCH
3. Convert dimension strings (`"8px"`) to DTCG `{value, unit}` objects
4. Resolve `{colors.primary}` token references
5. Output `tokens/dtcg.json`

Fallback: `npx @google/design.md@0.1.1 export --format dtcg DESIGN.md > tokens/dtcg.json || true`
Note: CLI exits with code 1 on success; no `--output` flag; components section not exported; typography loses lineHeight. Custom parser avoids all these bugs.

### Style Dictionary Config

`style-dictionary.config.js` in repo root. `usesDtcg: true`.

Three platforms with **custom format templates** (built-in formats are inadequate):

- **css**: Custom template → `:root { }` block with OKLCH values. The `@theme { }` and `@theme inline { }` blocks stay in `globals.css`.
- **android**: Custom template → Kotlin objects with `Color(0xFF...)`, `FontWeight()`, `FontVariation.Settings()`. Includes `@OptIn(ExperimentalTextApi::class)` and `toMaterialTypography()` extension.
- **ios**: Custom template → Swift `Color(red:green:blue:)` extensions, CTFont-based typography, `SkateLabColorScheme` struct.

### OKLCH → Platform Color Conversion

- **CSS**: Hex → OKLCH via `colorjs.io` in custom transformer. Output: `--color-primary: oklch(0.452 0.075 221)`
- **Android (Kotlin)**: Hex → `Color(0xFF155F73)` — direct from hex, no conversion needed
- **iOS (Swift)**: Hex → sRGB floats `Color(red: 0.082, green: 0.373, blue: 0.451)` — computed from hex

No `Color(oklch:)` on iOS — that API does not exist in SwiftUI.

### Generated File Headers

```
// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build
```

### Build Command

```yaml
# Taskfile.yaml
tasks:
  design:build:
    desc: "Generate design tokens for all platforms"
    cmds:
      - node scripts/design-tokens.js DESIGN.md tokens/dtcg.json
      - npx style-dictionary@5.4.1 build --config style-dictionary.config.js

  design:lint:
    desc: "Lint DESIGN.md with Google Stitch CLI"
    cmd: npx @google/design.md@0.1.1 lint DESIGN.md || true

  design:check:
    desc: "Check for drift between DESIGN.md and generated files"
    cmds:
      - task: design:build
      - git diff --exit-code frontend/src/app/tokens.css mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/ mobile/iosApp/SkateLab/Theme/ || (echo "Drift detected. Run 'task design:build' and commit." && exit 1)
```

## 3. Frontend Integration

### `@theme inline` Bridge Decision

**Decision: Option A — `@theme inline` stays in `globals.css`, `tokens.css` generates only `:root { }`.**

Rationale:
- shadcn components reference `var(--foreground)`, `var(--primary)`, etc. from `:root`
- `@theme inline` bridges `:root` vars → Tailwind theme vars (`--color-foreground: var(--foreground)`)
- Moving `@theme { }` to `tokens.css` while `@theme inline` defines the same variables causes conflicts
- Safest: `tokens.css` generates `:root { }`, `@theme { }` and `@theme inline { }` stay in `globals.css`

### globals.css After Refactor

```css
/* globals.css */
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "./tokens.css";   /* AUTO-GENERATED: :root { } block only */
@custom-variant dark (&:is(.dark *));

@theme {
  /* Design tokens — references :root vars from tokens.css */
  --radius-sm: 0.5rem;
  --radius-md: 1.25rem;
  --color-background: oklch(0.99 0.005 250);
  --color-foreground: oklch(var(--foreground-oklch));
  --color-primary: oklch(var(--primary-oklch));
  /* ... etc — hand-maintained, references :root OKLCH components */
}

@theme inline {
  /* shadcn bridge — unchanged */
  --font-heading: var(--font-sans);
  --font-sans: var(--font-inter), system-ui, sans-serif;
  --color-sidebar-ring: var(--sidebar-ring);
  /* ... etc */
}

@layer base {
  .sh-display-xxl { ... }
  .sh-body-md { ... }
  /* ... typography utilities, base styles, print, reduced-motion ... */
}
```

**`tokens.css`** (generated) contains only:
```css
/* AUTO-GENERATED — do not edit. Source: DESIGN.md */
/* Regenerate: task design:build */

:root {
  --primary: oklch(0.452 0.075 221);  /* #155F73 */
  --foreground: oklch(0.278 0.010 260);  /* #2A2D2E */
  --primary-oklch: 0.452 0.075 221;  /* for @theme references */
  --foreground-oklch: 0.278 0.010 260;
  /* ... all DESIGN.md color tokens as OKLCH + hex comment ... */
  --radius: 1.25rem;  /* base radius — updated in Phase 2b */
  --score-good: oklch(0.723 0.219 149);
  --score-mid: oklch(0.795 0.184 86);
  --score-bad: oklch(0.577 0.245 27);
  --accent-gold: oklch(0.795 0.184 86);
  /* sidebar, chart tokens — not in DESIGN.md, maintained here manually */
  --sidebar-ring: oklch(0.52 0.08 205);
  --sidebar-border: oklch(0.9 0.01 240);
  --chart-1: oklch(0.967 0 0);
  --chart-2: oklch(0.55 0 0);
  --chart-3: oklch(0.225 0 0);
  --chart-4: oklch(0.185 0 0);
  --chart-5: oklch(0.145 0 0);
}
```

### Sidebar/Chart Tokens

Sidebar tokens (`--sidebar-*`) and chart colors (`--chart-*`) are **not in DESIGN.md** — they are shadcn-specific. They remain in `tokens.css` `:root { }` block as manually maintained entries, marked with a comment `/* shadcn-only — not in DESIGN.md */`.

### Phase 2a: Token Extraction (No Visual Changes)

1. Create `tokens.css` from current `:root { }` values (no value changes)
2. Add `@import "./tokens.css"` to `globals.css`
3. Remove `:root { }` block from `globals.css`
4. `@theme { }` and `@theme inline { }` stay in `globals.css`
5. Verify: frontend builds and renders **identically** to before

### Phase 2b: Visual Refresh (Separate, With Regression Testing)

1. Regenerate OKLCH values from hex via `colorjs.io` (fix B1)
2. Fix color drift (`--foreground`, `--color-ink-faint`, `--color-canvas-soft`)
3. Fix border-radius values — **use intermediate values**:
   - `--radius-sm`: 8px → **6px** (moderate change)
   - `--radius-md`: 20px → **12px** (not 8px — too aggressive)
   - `--radius-lg`: 30px → **16px** (not 12px)
   - `--radius-xl`: 30px → **20px**
   - `--radius-2xl`: 36px → **30px**
4. Audit all `rounded-*` usages (146 outside UI, 50+ inside UI)
5. Visual regression testing before merge
6. Verify: frontend builds and visual appearance is intentional

## 4. CI Enforcement

### Job: design-lint (Informational)

```yaml
design-lint:
  name: Design Lint
  needs: [changes]
  if: inputs.run-all || needs.changes.outputs.design == 'true'
  runs-on: blacksmith-2vcpu-ubuntu-2404
  steps:
    - uses: actions/checkout@v6
    - uses: actions/setup-node@v4
      with:
        node-version: "22"
    - uses: actions/cache@v4
      with:
        path: ~/.npm/_npx
        key: design-md-${{ runner.os }}-0.1.1
    - name: Lint DESIGN.md
      run: npx @google/design.md@0.1.1 lint DESIGN.md || true
      continue-on-error: true
```

### Job: design-drift (Informational)

```yaml
design-drift:
  name: Design Drift Check
  needs: [changes]
  if: inputs.run-all || needs.changes.outputs.design == 'true'
  runs-on: blacksmith-2vcpu-ubuntu-2404
  steps:
    - uses: actions/checkout@v6
    - uses: actions/setup-node@v4
      with:
        node-version: "22"
    - name: Install deps
      run: npm install
    - name: Generate tokens
      run: node scripts/design-tokens.js DESIGN.md tokens/dtcg.json && npx style-dictionary@5.4.1 build --config style-dictionary.config.js
    - name: Normalize JSON
      run: for f in tokens/dtcg.json; do jq -S . "$f" > "$f.tmp" && mv "$f.tmp" "$f"; done
    - name: Check for drift
      run: |
        git diff --exit-code \
          frontend/src/app/tokens.css \
          mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/ \
          mobile/iosApp/SkateLab/Theme/ \
          || (echo "Design tokens drifted. Run 'task design:build' and commit." && exit 1)
```

Both jobs: **informational** (not blocking), parallel (not sequential). Graduate to blocking after 30 days clean.

In `ci-passed` summary:
```yaml
echo "| :mag: design-lint | \`${DESIGN_LINT}\` (informational) |" >> "$GITHUB_STEP_SUMMARY"
echo "| :mag: design-drift | \`${DESIGN_DRIFT}\` (informational) |" >> "$GITHUB_STEP_SUMMARY"
```

### Changes Filter

```yaml
design:
  - "DESIGN.md"
  - "scripts/design-tokens.js"
  - "style-dictionary.config.js"
  - "tokens/**"
  - "frontend/src/app/tokens.css"
  - "mobile/androidApp/**/theme/**"
  - "mobile/iosApp/**/Theme/**"
  - "sgconfig.yml"
  - "ast-grep/*.yml"
  - "Taskfile.yml"
```

### ast-grep Rules (Revised)

#### `ast-grep/no-raw-font-weights.yml`

```yaml
id: no-raw-font-weights
language: tsx
message: |
  Use design-system typography tokens (.sh-display-xl, .sh-body-md, etc.)
  instead of raw Tailwind font-weight utilities.
  The Sub-Default Rule requires weights 460/540/600 instead of 400/500/700.
severity: warning
rule:
  kind: string_fragment
  regex: '(font-thin|font-extralight|font-light|font-normal|font-medium|font-semibold|font-bold|font-extrabold|font-black)'
ignores:
  - "frontend/src/components/ui/**"
```

#### `ast-grep/no-backdrop-blur.yml`

```yaml
id: no-backdrop-blur
language: tsx
message: |
  backdrop-filter: blur() violates the No-Frosted-Glass Rule.
  Use solid bg-background with opacity transition instead.
severity: error
rule:
  kind: string_fragment
  regex: 'backdrop-blur-(?!none)\w+'
ignores:
  - "frontend/src/app/tokens.css"
```

#### `ast-grep/no-static-shadow.yml`

```yaml
id: no-static-shadow
language: tsx
message: |
  Shadows on static elements violate the Flat-By-Default Rule.
  Only floating overlays (dropdowns, modals, popovers) may have shadows.
severity: warning
rule:
  kind: string_fragment
  regex: 'shadow-(xs|sm|md|lg|xl|2xl|\\[)'
ignores:
  - "frontend/src/components/ui/**"
```

Note: `shadow-inner` removed — inset shadows are a different pattern (input fields), not elevation.

#### `ast-grep/no-canvas-soft-section.yml`

```yaml
id: no-canvas-soft-section
language: tsx
message: |
  Canvas-soft should not be used as a section-level background (Three-Canvas Rule).
  Use canvas (white) or surface-teal-deep instead. Canvas-soft is for card bands only.
severity: hint
rule:
  kind: string_fragment
  regex: 'bg-canvas-soft'
```

Note: Reduced to `severity: hint` — ast-grep cannot distinguish section vs. card context.

#### `ast-grep/no-dark-variant.yml` (NEW)

```yaml
id: no-dark-variant
language: tsx
message: |
  Dark mode is disabled per DESIGN.md. Prefer light-only styling.
severity: hint
rule:
  kind: string_fragment
  regex: 'dark:'
ignores:
  - "frontend/src/components/ui/**"
```

Note: `no-pill-outside-hero` **dropped** — too many false positives (avatars, progress bars, badges, pill-tabs — which the spec itself defines with `rounded.full`).

## 5. Android Compose Theme

### Colors.kt

```kotlin
// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build

package ru.skatelab.capture.presentation.theme

import androidx.compose.ui.graphics.Color

object SkateLabColors {
    // Brand
    val primary = Color(0xFF155F73)
    val primaryDeep = Color(0xFF0E3340)
    val primaryForeground = Color(0xFFFFFFFF)

    // Text
    val ink = Color(0xFF2A2D2E)
    val inkMute = Color(0xFF6B7275)
    val inkFaint = Color(0xFF9BA0A3)

    // Surface
    val canvas = Color(0xFFFFFFFF)
    val canvasSoft = Color(0xFFF5F7F8)
    val surfaceIceSoft = Color(0xFFC8E6F0)
    val surfaceTealDeep = Color(0xFF0E3340)
    val surfaceTealMid = Color(0xFF155F73)

    // Border
    val hairline = Color(0xFFD5DDE0)
    val hairlineDark = Color(0xFF2A4A52)

    // On-dark text
    val onDarkMute = Color(0xFFC5D5DB)
    val onDarkDim = Color(0xFF8AABB8)
    val onDarkFaint = Color(0xFF5A7A85) // WCAG: fails 4.5:1 below 18px
    val onPrimary = Color(0xFFFFFFFF)

    // Semantic
    val destructive = Color(0xFFC0392B)
    val link = Color(0xFF155F73)
    val ring = Color(0xFF155F73)
    val scoreGood = Color(0xFF27AE60)
    val scoreMid = Color(0xFFF39C12)
    val scoreBad = Color(0xFFE74C3C)
    val accentGold = Color(0xFFF39C12)

    // Semantic aliases (light-only)
    val background = canvas
    val foreground = ink
    val card = canvas
    val cardForeground = ink
    val muted = canvasSoft
    val mutedForeground = inkMute
    val border = hairline
    val input = hairline
}
```

### Type.kt

```kotlin
// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build

package ru.skatelab.capture.presentation.theme

import android.os.Build
import androidx.annotation.RequiresApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

@RequiresApi(Build.VERSION_CODES.O)
val InterVariable = FontFamily(
    Font(R.font.inter_variable, FontWeight(460), FontVariation.Settings(FontVariation.weight(460))),
    Font(R.font.inter_variable, FontWeight(540), FontVariation.Settings(FontVariation.weight(540))),
    Font(R.font.inter_variable, FontWeight(600), FontVariation.Settings(FontVariation.weight(600))),
    Font(R.font.inter_variable, FontWeight(700), FontVariation.Settings(FontVariation.weight(700))),
)

// Fallback for API < 28: static Inter weights
val InterFallback = FontFamily(
    Font(R.font.inter_regular, FontWeight.Normal),      // 400
    Font(R.font.inter_medium, FontWeight.Medium),       // 500
    Font(R.font.inter_semibold, FontWeight.SemiBold),   // 600
    Font(R.font.inter_bold, FontWeight.Bold),            // 700
)

val AppFontFamily = if (Build.VERSION.SDK_INT >= 28) InterVariable else InterFallback

data class SkateLabTypography(
    val displayXxl: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 36.sp, fontWeight = weightOrFallback(540, FontWeight.SemiBold), lineHeight = 34.56.sp),
    val displayXl: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 32.sp, fontWeight = weightOrFallback(460, FontWeight.Normal), lineHeight = 30.72.sp, letterSpacing = (-1.32).sp),
    val displayLg: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 28.sp, fontWeight = weightOrFallback(540, FontWeight.SemiBold), lineHeight = 31.92.sp, letterSpacing = (-0.63).sp),
    val displayMd: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 22.sp, fontWeight = weightOrFallback(460, FontWeight.Normal), lineHeight = 24.2.sp, letterSpacing = (-0.315).sp),
    val headingLg: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 20.sp, fontWeight = weightOrFallback(460, FontWeight.Normal), lineHeight = 24.sp, letterSpacing = (-0.4).sp),
    val bodyLg: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 18.sp, fontWeight = weightOrFallback(540, FontWeight.SemiBold), lineHeight = 27.sp, letterSpacing = (-0.135).sp),
    val bodyMd: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 16.sp, fontWeight = weightOrFallback(460, FontWeight.Normal), lineHeight = 24.sp),
    val bodyStrong: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 18.72.sp, fontWeight = FontWeight.Bold, lineHeight = 28.08.sp),
    val buttonMd: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 16.sp, fontWeight = FontWeight.Bold, lineHeight = 16.sp),
    val buttonCap: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, lineHeight = 14.sp),
    val caption: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 14.sp, fontWeight = weightOrFallback(460, FontWeight.Normal), lineHeight = 19.6.sp),
    val micro: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 12.sp, fontWeight = weightOrFallback(540, FontWeight.SemiBold), lineHeight = 16.8.sp),
    val legal: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 11.sp, fontWeight = weightOrFallback(460, FontWeight.Normal), lineHeight = 16.5.sp),
    val price: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 32.sp, fontWeight = FontWeight.Bold, lineHeight = 32.sp, letterSpacing = (-0.96).sp, fontFeatureSettings = "tnum"),
)

private fun weightOrFallback(variable: Int, fallback: FontWeight): FontWeight =
    if (Build.VERSION.SDK_INT >= 28) FontWeight(variable) else fallback

val SkateLabTypographyDefaults = SkateLabTypography()
```

### Font Bundling (Android)

```
mobile/androidApp/src/main/res/font/
├── inter_variable.ttf     # Inter Variable (API 28+)
├── inter_regular.ttf     # Inter Regular (fallback, 400)
├── inter_medium.ttf      # Inter Medium (fallback, 500)
├── inter_semibold.ttf    # Inter SemiBold (fallback, 600)
└── inter_bold.ttf        # Inter Bold (fallback, 700)
```

Weight mapping for API <28: 460→Medium(500), 540→SemiBold(600), 600→SemiBold(600), 700→Bold(700).

### Theme.kt

```kotlin
// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build

package ru.skatelab.capture.presentation.theme

import android.app.Activity
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

// Material 3 bridge — best-effort mapping for standard Material components.
// Custom SkateLab components should use SkateLabTheme.colors.* directly.
private val SkateLabLightScheme = lightColorScheme(
    primary = SkateLabColors.primary,
    onPrimary = SkateLabColors.primaryForeground,
    primaryContainer = SkateLabColors.surfaceTealDeep,
    onPrimaryContainer = SkateLabColors.surfaceIceSoft,
    secondary = SkateLabColors.inkMute,
    onSecondary = SkateLabColors.onPrimary,
    tertiary = SkateLabColors.surfaceIceSoft,
    background = SkateLabColors.canvas,
    onBackground = SkateLabColors.ink,
    surface = SkateLabColors.canvas,
    onSurface = SkateLabColors.ink,
    surfaceVariant = SkateLabColors.canvasSoft,
    onSurfaceVariant = SkateLabColors.inkMute,
    outline = SkateLabColors.hairline,
    outlineVariant = SkateLabColors.hairlineDark,
    error = SkateLabColors.destructive,
    onError = SkateLabColors.onPrimary,
)

object SkateLabTheme {
    val colors: SkateLabColors
        @Composable get() = SkateLabColors

    val typography: SkateLabTypography
        @Composable get() = SkateLabTypographyDefaults
}

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            @Suppress("DEPRECATION")
            window.statusBarColor = SkateLabColors.primaryDeep.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(
        colorScheme = SkateLabLightScheme,
        typography = SkateLabTypographyDefaults.toMaterialTypography(),
        content = content,
    )
}

private fun SkateLabTypography.toMaterialTypography(): Typography = Typography(
    displayLarge = displayXxl,
    displayMedium = displayXl,
    displaySmall = displayLg,
    headlineLarge = displayMd,
    headlineMedium = headingLg,
    headlineSmall = headingLg,
    titleLarge = bodyLg,
    titleMedium = bodyStrong,
    titleSmall = bodyMd,
    bodyLarge = bodyLg,
    bodyMedium = bodyMd,
    bodySmall = caption,
    labelLarge = buttonMd,
    labelMedium = buttonCap,
    labelSmall = micro,
)
```

## 6. iOS SwiftUI Theme

### SkateLabColors.swift

```swift
// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build

import SwiftUI

@available(iOS 15, *)
extension Color {
    // Brand
    static let skatePrimary = Color(red: 0.082, green: 0.373, blue: 0.451)
    static let skatePrimaryDeep = Color(red: 0.055, green: 0.200, blue: 0.251)
    static let skatePrimaryForeground = Color.white

    // Text
    static let skateInk = Color(red: 0.165, green: 0.176, blue: 0.180)
    static let skateInkMute = Color(red: 0.420, green: 0.447, blue: 0.459)
    static let skateInkFaint = Color(red: 0.608, green: 0.627, blue: 0.639)

    // Surface
    static let skateCanvas = Color.white
    static let skateCanvasSoft = Color(red: 0.961, green: 0.969, blue: 0.973)
    static let skateSurfaceIceSoft = Color(red: 0.784, green: 0.902, blue: 0.941)
    static let skateSurfaceTealDeep = Color(red: 0.055, green: 0.200, blue: 0.251)
    static let skateSurfaceTealMid = Color(red: 0.082, green: 0.373, blue: 0.451)

    // Border
    static let skateHairline = Color(red: 0.835, green: 0.867, blue: 0.878)
    static let skateHairlineDark = Color(red: 0.165, green: 0.290, blue: 0.322)

    // On-dark text
    static let skateOnDarkMute = Color(red: 0.773, green: 0.835, blue: 0.859)
    static let skateOnDarkDim = Color(red: 0.541, green: 0.671, blue: 0.722)
    static let skateOnDarkFaint = Color(red: 0.353, green: 0.478, blue: 0.522)
    static let skateOnPrimary = Color.white

    // Semantic
    static let skateDestructive = Color(red: 0.753, green: 0.224, blue: 0.169)
    static let skateLink = Color(red: 0.082, green: 0.373, blue: 0.451)
    static let skateRing = Color(red: 0.082, green: 0.373, blue: 0.451)
    static let skateScoreGood = Color(red: 0.153, green: 0.682, blue: 0.376)
    static let skateScoreMid = Color(red: 0.953, green: 0.612, blue: 0.071)
    static let skateScoreBad = Color(red: 0.906, green: 0.298, blue: 0.235)
    static let skateAccentGold = Color(red: 0.953, green: 0.612, blue: 0.071)
}
```

### SkateLabTypography.swift

```swift
// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build

import SwiftUI
import CoreText

@available(iOS 15, *)
extension Font {
    private static func skateVariable(size: CGFloat, weight: Double) -> Font {
        let wghtTag = Int(2003265652) // 'wght' FourCharCode as Int
        let variation: [Int: Double] = [wghtTag: weight]
        let attrs: [CFString: Any] = [
            kCTFontNameAttribute: "InterVariable" as CFString,
            kCTFontVariationAttribute: variation as CFDictionary
        ]
        let descriptor = CTFontDescriptorCreateWithAttributes(attrs as CFDictionary)
        let ctFont = CTFontCreateWithFontDescriptor(descriptor, size, nil)
        return Font(ctFont)
    }

    // Fallback for platforms without variable font axis support
    private static func skateStatic(size: CGFloat, weight: Font.Weight) -> Font {
        switch weight {
        case .regular: return Font.custom("Inter-Regular", size: size)
        case .medium: return Font.custom("Inter-Medium", size: size)
        case .semibold: return Font.custom("Inter-SemiBold", size: size)
        case .bold: return Font.custom("Inter-Bold", size: size)
        default: return Font.custom("Inter-Medium", size: size)
        }
    }

    // Public typography tokens — uses CTFont variable axes when available
    static let skateDisplayXxl = skateVariable(size: 36, weight: 540)
    static let skateDisplayXl = skateVariable(size: 32, weight: 460)
    static let skateDisplayLg = skateVariable(size: 28, weight: 540)
    static let skateDisplayMd = skateVariable(size: 22, weight: 460)
    static let skateHeadingLg = skateVariable(size: 20, weight: 460)
    static let skateBodyLg = skateVariable(size: 18, weight: 540)
    static let skateBodyMd = skateVariable(size: 16, weight: 460)
    static let skateBodyStrong = skateVariable(size: 18.72, weight: 700)
    static let skateButtonMd = skateVariable(size: 16, weight: 700)
    static let skateButtonCap = skateVariable(size: 14, weight: 600)
    static let skateCaption = skateVariable(size: 14, weight: 460)
    static let skateMicro = skateVariable(size: 12, weight: 540)
    static let skateLegal = skateVariable(size: 11, weight: 460)
    static let skatePrice = skateVariable(size: 32, weight: 700)
}
```

### SkateLabTheme.swift

```swift
// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build

import SwiftUI

@available(iOS 15, *)
struct SkateLabColorScheme {
    let primary = Color.skatePrimary
    let primaryDeep = Color.skatePrimaryDeep
    let primaryForeground = Color.skatePrimaryForeground
    let ink = Color.skateInk
    let inkMute = Color.skateInkMute
    let inkFaint = Color.skateInkFaint
    let canvas = Color.skateCanvas
    let canvasSoft = Color.skateCanvasSoft
    let surfaceIceSoft = Color.skateSurfaceIceSoft
    let surfaceTealDeep = Color.skateSurfaceTealDeep
    let surfaceTealMid = Color.skateSurfaceTealMid
    let hairline = Color.skateHairline
    let hairlineDark = Color.skateHairlineDark
    let onDarkMute = Color.skateOnDarkMute
    let onDarkDim = Color.skateOnDarkDim
    let onDarkFaint = Color.skateOnDarkFaint
    let onPrimary = Color.skateOnPrimary
    let destructive = Color.skateDestructive
    let link = Color.skateLink
    let ring = Color.skateRing
    let scoreGood = Color.skateScoreGood
    let scoreMid = Color.skateScoreMid
    let scoreBad = Color.skateScoreBad
    let accentGold = Color.skateAccentGold
    let background = Color.skateCanvas
    let foreground = Color.skateInk
}

@available(iOS 15, *)
private struct SkateLabColorSchemeKey: EnvironmentKey {
    static let defaultValue = SkateLabColorScheme()
}

@available(iOS 15, *)
extension EnvironmentValues {
    var skateLabColors: SkateLabColorScheme {
        get { self[SkateLabColorSchemeKey.self] }
        set { self[SkateLabColorSchemeKey.self] = newValue }
    }
}
```

### Font Bundling (iOS)

```
mobile/iosApp/SkateLab/Fonts/
├── InterVariable.ttf     # Inter Variable (primary)
├── Inter-Regular.ttf     # Static fallback
├── Inter-Medium.ttf      # 460≈500 fallback
├── Inter-SemiBold.ttf    # 540/600≈600 fallback
└── Inter-Bold.ttf        # 700
```

`Info.plist` `UIAppFonts` key lists all 5 files. PostScript name `InterVariable` verified.

## 7. Migration Plan (Revised)

### Phase 1: Pipeline Infrastructure

1. Create `scripts/design-tokens.js` — custom YAML parser + DTCG generator
2. Create `style-dictionary.config.js` with custom format templates
3. Add `task design:build`, `design:lint`, `design:check` to Taskfile.yaml
4. Install deps: `npm install style-dictionary@5.4.1 yaml colorjs.io`
5. Generate tokens from **current** DESIGN.md (with all current values, no drift fixes)
6. Verify generated `tokens.css`, `Colors.kt`, `SkateLabColors.swift` match current values
7. Add `.gitattributes` for generated files
8. Add `design-lint` and `design-drift` CI jobs (informational)

### Phase 2a: Frontend Token Extraction (No Visual Changes)

1. Generate `tokens.css` with current `:root { }` values
2. Add `@import "./tokens.css"` to `globals.css`
3. Remove `:root { }` from `globals.css`
4. `@theme { }` and `@theme inline { }` stay in `globals.css`
5. Verify: `bun run build` succeeds, no visual changes

### Phase 2b: Data Fix + Visual Refresh

1. Regenerate all OKLCH values from hex via `colorjs.io`
2. Update DESIGN.md prose with computed OKLCH values
3. Fix DESIGN.md lint errors (`clamp()` refs, `{colors.on-primary}`)
4. Fix color drift (`--foreground`, `--color-ink-faint`, `--color-canvas-soft`)
5. Update border-radius to intermediate values (md=12px, lg=16px, xl=20px)
6. Audit all `rounded-*` usages
7. Visual regression testing
8. Verify: `bun run build` + visual check

### Phase 3: Mobile Integration

1. Replace `AppTheme.kt` with generated `Colors.kt` + `Type.kt` + `Theme.kt`
2. Bundle Inter Variable + static fallbacks in Android `res/font/`
3. Create iOS Theme directory with generated Swift files
4. Bundle Inter Variable + static fallbacks in iOS `Fonts/`
5. Add `@OptIn(ExperimentalTextApi::class)` to Android Type.kt
6. Verify: both apps build and render with Gentle Sea Breeze theme

### Phase 4: CI Enforcement + ast-grep

1. Add 5 revised ast-grep rules
2. Add `design` changes filter
3. Graduate design jobs from informational to blocking (after 30 days clean)
4. Delete `DESIGN.json` (superseded by DESIGN.md YAML)
5. Update `.impeccable/design.json` or document impeccable integration
6. Update CLAUDE.md with `task design:build` workflow

## 8. Files Summary

### Files to Delete

- `DESIGN.json` — superseded by DESIGN.md YAML + Style Dictionary pipeline

### Files to Create

- `scripts/design-tokens.js` — custom YAML → DTCG parser
- `style-dictionary.config.js` — SD configuration with custom templates
- `tokens/dtcg.json` — generated (git-tracked)
- `frontend/src/app/tokens.css` — generated `:root { }` block
- `mobile/.../theme/Colors.kt` — generated
- `mobile/.../theme/Type.kt` — generated
- `mobile/.../theme/Theme.kt` — generated
- `mobile/iosApp/.../Theme/SkateLabColors.swift` — generated
- `mobile/iosApp/.../Theme/SkateLabTypography.swift` — generated
- `mobile/iosApp/.../Theme/SkateLabTheme.swift` — generated
- `ast-grep/no-raw-font-weights.yml`
- `ast-grep/no-backdrop-blur.yml`
- `ast-grep/no-static-shadow.yml`
- `ast-grep/no-canvas-soft-section.yml`
- `ast-grep/no-dark-variant.yml`

### Files to Modify

- `DESIGN.md` — restructure YAML frontmatter, fix OKLCH values (Phase 2b)
- `frontend/src/app/globals.css` — remove `:root { }`, add `@import "./tokens.css"` (Phase 2a)
- `mobile/.../AppTheme.kt` — replaced by generated Theme.kt (Phase 3)
- `ci-reusable.yml` — add design-lint, design-drift, design filter (Phase 1+4)
- `sgconfig.yml` — add new ast-grep rules (Phase 4)
- `Taskfile.yaml` — add design:build, design:lint, design:check (Phase 1)
- `.gitattributes` — mark generated files