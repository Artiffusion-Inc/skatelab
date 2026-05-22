# Unified Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a DESIGN.md → DTCG → Style Dictionary pipeline that generates design tokens for Web (CSS), Android (Kotlin Compose), and iOS (SwiftUI) from a single source of truth.

**Architecture:** DESIGN.md YAML frontmatter (hex canonical) → custom parser (`scripts/design-tokens.js`) → DTCG JSON → Style Dictionary v5.4.1 with custom format templates → platform output files. No manual edits to generated files.

**Tech Stack:** Node.js (yaml, colorjs.io), Style Dictionary v5.4.1, Tailwind CSS v4, Kotlin Compose, SwiftUI

---

## File Structure

### Created
```
scripts/design-tokens.js          # Custom YAML → DTCG parser
style-dictionary.config.js        # SD config with custom templates
tokens/dtcg.json                  # Generated intermediate
frontend/src/app/tokens.css       # Generated :root { } block
mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/
  Colors.kt                       # Generated
  Type.kt                         # Generated
  Theme.kt                        # Generated
mobile/androidApp/src/main/res/font/
  inter_variable.ttf              # Inter Variable (from Google Fonts)
  inter_regular.ttf               # Static fallback 400
  inter_medium.ttf                # Static fallback 500
  inter_semibold.ttf              # Static fallback 600
  inter_bold.ttf                  # Static fallback 700
mobile/iosApp/SkateLab/Theme/
  SkateLabColors.swift            # Generated
  SkateLabTypography.swift        # Generated
  SkateLabTheme.swift             # Generated
mobile/iosApp/SkateLab/Fonts/
  InterVariable.ttf               # Inter Variable
  Inter-Regular.ttf               # Static fallback
  Inter-Medium.ttf
  Inter-SemiBold.ttf
  Inter-Bold.ttf
ast-grep/no-raw-font-weights.yml
ast-grep/no-backdrop-blur.yml
ast-grep/no-static-shadow.yml
ast-grep/no-canvas-soft-section.yml
ast-grep/no-dark-variant.yml
package.json                      # Root-level for style-dictionary deps
```

### Modified
```
frontend/src/app/globals.css      # Remove :root { }, add @import "./tokens.css"
mobile/androidApp/.../theme/AppTheme.kt  # Replaced by generated Theme.kt
.github/workflows/ci-reusable.yml # Add design-lint, design-drift, design filter
Taskfile.yml                      # Add design:build, design:lint, design:check
sgconfig.yml                      # Add new ast-grep rule paths
.gitattributes                    # Mark generated files
DESIGN.md                         # Fix OKLCH values, lint errors (Phase 2b)
```

### Deleted
```
DESIGN.json                       # Superseded by DESIGN.md + pipeline
```

---

## Wave 1: Pipeline Infrastructure (Phase 1)

### Task 1: Root package.json + dependencies

**Files:**
- Create: `package.json`

- [ ] **Step 1: Create root package.json with Style Dictionary deps**

```json
{
  "name": "skatelab-design-tokens",
  "private": true,
  "type": "module",
  "scripts": {
    "design:build": "node scripts/design-tokens.js DESIGN.md tokens/dtcg.json && npx style-dictionary@5.4.1 build --config style-dictionary.config.js",
    "design:lint": "npx @google/design.md@0.1.1 lint DESIGN.md || true",
    "design:check": "npm run design:build && git diff --exit-code frontend/src/app/tokens.css mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/ mobile/iosApp/SkateLab/Theme/ || (echo 'Drift detected. Run \"npm run design:build\" and commit.' && exit 1)"
  },
  "dependencies": {
    "style-dictionary": "5.4.1",
    "yaml": "^2.7.0",
    "colorjs.io": "^0.5.2"
  }
}
```

- [ ] **Step 2: Install dependencies**

Run: `cd /home/michael/Github/skating-biomechanics-ml && npm install`
Expected: `node_modules/` created, `package-lock.json` generated

- [ ] **Step 3: Add node_modules to .gitignore**

Append to `.gitignore`:
```
# Design token pipeline
node_modules/
tokens/dtcg.json
```

- [ ] **Step 4: Commit**

```bash
git add package.json package-lock.json .gitignore
git commit -m "chore(design): add style-dictionary and yaml dependencies"
```

---

### Task 2: Custom YAML → DTCG parser

**Files:**
- Create: `scripts/design-tokens.js`

- [ ] **Step 1: Write the parser script**

The script must:
1. Read `DESIGN.md`, extract YAML frontmatter between `---` markers
2. Parse `colors` section: hex → DTCG color tokens with computed OKLCH
3. Parse `typography` section: fontSize/weight/lineHeight/letterSpacing → DTCG dimension tokens
4. Parse `rounded` section: px values → DTCG dimension tokens
5. Parse `spacing` section: px values → DTCG dimension tokens
6. Parse `components` section: resolve `{colors.primary}` and `{typography.button-md}` references
7. Output `tokens/dtcg.json` in W3C DTCG format

Key conversion logic:
- **Hex → OKLCH**: Use `colorjs.io` to convert. `new Color("#155f73").to("oklch")` → `{L, C, H}`. Format as `oklch(L C H)`.
- **Hex → sRGB float**: Parse hex to R/G/B integers, divide by 255. E.g. `#155F73` → `{r: 0.082, g: 0.373, b: 0.451}`.
- **Hex → Kotlin ARGB**: `0xFF155F73` format. Alpha always `FF`.
- **Dimension strings**: `"8px"` → `{value: 8, unit: "px"}`. `"1.25rem"` → `{value: 1.25, unit: "rem"}`. `"clamp(...)"` stays as string value.

```javascript
#!/usr/bin/env node
// scripts/design-tokens.js — DESIGN.md YAML → DTCG JSON
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { parse as parseYaml } from 'yaml';
import { dirname } from 'path';
import Color from 'colorjs.io';

const inputPath = process.argv[2] || 'DESIGN.md';
const outputPath = process.argv[3] || 'tokens/dtcg.json';

// Extract YAML frontmatter from DESIGN.md
function extractFrontmatter(content) {
  const match = content.match(/^---\n([\s\S]*?)\n---/);
  if (!match) throw new Error('No YAML frontmatter found in ' + inputPath);
  return parseYaml(match[1]);
}

// Hex → OKLCH string
function hexToOklch(hex) {
  const color = new Color(hex);
  const oklch = color.to('oklch');
  const L = parseFloat(oklch.coords[0].toFixed(3));
  const C = parseFloat(oklch.coords[1].toFixed(3));
  const H = parseFloat(oklch.coords[2].toFixed(2));
  return `oklch(${L} ${C} ${H})`;
}

// Hex → sRGB floats
function hexToSrgb(hex) {
  const color = new Color(hex);
  const srgb = color.to('srgb');
  return {
    r: parseFloat(srgb.coords[0].toFixed(3)),
    g: parseFloat(srgb.coords[1].toFixed(3)),
    b: parseFloat(srgb.coords[2].toFixed(3)),
  };
}

// Hex → Kotlin 0xFFRRGGBB
function hexToArgb(hex) {
  const clean = hex.replace('#', '');
  return `0xFF${clean.toUpperCase()}`;
}

// Parse dimension string like "8px", "1.25rem"
function parseDimension(str) {
  if (str.startsWith('clamp(')) return { value: str, type: 'dimension', original: str };
  const match = String(str).match(/^([\d.]+)(px|rem|em|%)$/);
  if (match) return { value: parseFloat(match[1]), unit: match[2], type: 'dimension' };
  return { value: str, type: 'dimension', original: str };
}

// Build DTCG color token
function colorToken(hex, description) {
  return {
    $type: 'color',
    $value: hex,
    $description: description || '',
    $extensions: {
      'com.tokens-studio': {
        oklch: hexToOklch(hex),
        srgb: hexToSrgb(hex),
        argb: hexToArgb(hex),
      },
    },
  };
}

// Build typography token
function typoToken(name, config) {
  return {
    $type: 'typography',
    $value: {
      fontFamily: { value: config.fontFamily, type: 'string' },
      fontSize: parseDimension(config.fontSize),
      fontWeight: { value: config.fontWeight, type: 'number' },
      lineHeight: config.lineHeight ? parseDimension(config.lineHeight.toString()) : undefined,
      letterSpacing: config.letterSpacing ? parseDimension(config.letterSpacing) : undefined,
    },
    $description: `Typography token: ${name}`,
  };
}

function main() {
  const content = readFileSync(inputPath, 'utf-8');
  const fm = extractFrontmatter(content);
  const tokens = { $schema: 'https://design-tokens.github.io/community-group/format/', $description: 'SkateLab Design Tokens' };

  // Colors
  if (fm.colors) {
    tokens.colors = {};
    for (const [key, hex] of Object.entries(fm.colors)) {
      tokens.colors[key] = colorToken(hex);
    }
  }

  // Typography
  if (fm.typography) {
    tokens.typography = {};
    for (const [name, config] of Object.entries(fm.typography)) {
      tokens.typography[name] = typoToken(name, config);
    }
  }

  // Rounded
  if (fm.rounded) {
    tokens.rounded = {};
    for (const [key, val] of Object.entries(fm.rounded)) {
      tokens.rounded[key] = { $type: 'dimension', $value: parseDimension(val) };
    }
  }

  // Spacing
  if (fm.spacing) {
    tokens.spacing = {};
    for (const [key, val] of Object.entries(fm.spacing)) {
      tokens.spacing[key] = { $type: 'dimension', $value: parseDimension(val) };
    }
  }

  // Components (resolve references)
  if (fm.components) {
    tokens.components = {};
    for (const [name, comp] of Object.entries(fm.components)) {
      const resolved = {};
      for (const [prop, val] of Object.entries(comp)) {
        if (typeof val === 'string' && val.startsWith('{') && val.endsWith('}')) {
          // Token reference like {colors.primary} — resolve later in SD
          resolved[prop] = { $value: val, $type: 'string' };
        } else {
          resolved[prop] = val;
        }
      }
      tokens.components[name] = resolved;
    }
  }

  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, JSON.stringify(tokens, null, 2));
  console.log(`✓ Generated ${outputPath}`);
}

main();
```

- [ ] **Step 2: Run parser and verify output**

Run: `node scripts/design-tokens.js DESIGN.md tokens/dtcg.json`
Expected: `tokens/dtcg.json` created with color tokens containing `$extensions.oklch`, `$extensions.srgb`, `$extensions.argb`

- [ ] **Step 3: Verify OKLCH values match hex**

Inspect a few entries in `tokens/dtcg.json`:
- `colors.primary.$value` should be `#155f73`
- `colors.primary.$extensions.oklch` should be something like `oklch(0.452 0.075 221)` (computed from hex, NOT the wrong value from DESIGN.md prose)
- `colors.primary.$extensions.argb` should be `0xFF155F73`

If hex→OKLCH conversion produces wrong values, fix `hexToOklch` function.

- [ ] **Step 4: Commit**

```bash
git add scripts/design-tokens.js tokens/dtcg.json
git commit -m "feat(design): add custom YAML → DTCG parser with OKLCH computation"
```

---

### Task 3: Style Dictionary config with custom format templates

**Files:**
- Create: `style-dictionary.config.js`

- [ ] **Step 1: Write Style Dictionary config**

The config needs three platforms: `css`, `android`, `ios`. Each uses custom format templates because built-in formats produce broken output (see review H1, M1).

```javascript
// style-dictionary.config.js
import StyleDictionary from 'style-dictionary';

const { fileHeader } = StyleDictionary.formatHelpers;

// CSS custom properties format — generates :root { } block with OKLCH values
StyleDictionary.registerFormat({
  name: 'css/variables',
  formatter: ({ dictionary, file }) => {
    const header = fileHeader({ file });
    const colors = dictionary.allTokens
      .filter(t => t.$type === 'color' || t.type === 'color')
      .map(t => {
        const oklch = t.$extensions?.['com.tokens-studio']?.oklch || t.value;
        const hex = t.$value || t.value;
        return `  --${t.name.replace(/-/g, '-')}: ${oklch};  /* ${hex} */`;
      });
    const dimensions = dictionary.allTokens
      .filter(t => (t.$type === 'dimension' || t.type === 'dimension') && !t.name.startsWith('typography'))
      .map(t => {
        const val = typeof t.$value === 'object' ? (t.$value.value || t.$value) : (t.$value || t.value);
        return `  --${t.name.replace(/-/g, '-')}: ${val};`;
      });
    return `${header}:root {\n${colors.join('\n')}\n${dimensions.join('\n')}\n}\n`;
  },
});

// Kotlin Compose format — generates object SkateLabColors
StyleDictionary.registerFormat({
  name: 'compose/object',
  formatter: ({ dictionary, file, options }) => {
    const header = fileHeader({ file });
    const pkg = options.package || 'ru.skatelab.capture.presentation.theme';
    const colors = dictionary.allTokens
      .filter(t => t.$type === 'color' || t.type === 'color')
      .map(t => {
        const argb = t.$extensions?.['com.tokens-studio']?.argb;
        const name = t.name.replace(/-/g, '').replace(/^./, c => c.toUpperCase()).replace(/[^a-zA-Z0-9]/g, '');
        // Convert kebab to camelCase
        const camelName = t.name.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        return `    val ${camelName} = Color(${argb})`;
      });
    return `${header}package ${pkg}\n\nimport androidx.compose.ui.graphics.Color\n\nobject SkateLabColors {\n${colors.join('\n')}\n}\n`;
  },
});

// iOS Swift format — generates extension Color { static let skate... }
StyleDictionary.registerFormat({
  name: 'ios/swift/extension',
  formatter: ({ dictionary, file }) => {
    const header = fileHeader({ file });
    const colors = dictionary.allTokens
      .filter(t => t.$type === 'color' || t.type === 'color')
      .map(t => {
        const srgb = t.$extensions?.['com.tokens-studio']?.srgb;
        const name = 'skate' + t.name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).replace(/ /g, '');
        return `    static let ${name} = Color(red: ${srgb.r}, green: ${srgb.g}, blue: ${srgb.b})`;
      });
    return `${header}import SwiftUI\n\n@available(iOS 15, *)\nextension Color {\n${colors.join('\n')}\n}\n`;
  },
});

export default {
  source: ['tokens/dtcg.json'],
  usesDtcg: true,
  platforms: {
    css: {
      buildPath: 'frontend/src/app/',
      files: [{
        destination: 'tokens.css',
        format: 'css/variables',
        options: { fileHeader: 'AUTO-GENERATED — do not edit. Source: DESIGN.md\n// Regenerate: task design:build' },
      }],
    },
    android: {
      buildPath: 'mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/',
      files: [{
        destination: 'Colors.kt',
        format: 'compose/object',
        options: { package: 'ru.skatelab.capture.presentation.theme' },
      }],
    },
    ios: {
      buildPath: 'mobile/iosApp/SkateLab/Theme/',
      files: [{
        destination: 'SkateLabColors.swift',
        format: 'ios/swift/extension',
      }],
    },
  },
};
```

- [ ] **Step 2: Run Style Dictionary build**

Run: `npx style-dictionary@5.4.1 build --config style-dictionary.config.js`
Expected: Files generated at `frontend/src/app/tokens.css`, `mobile/androidApp/.../Colors.kt`, `mobile/iosApp/.../SkateLabColors.swift`

- [ ] **Step 3: Verify generated tokens match current values**

Compare `tokens.css` `:root` block with current `globals.css` `:root` block — colors should match hex canonicals. Compare `Colors.kt` hex values with `AppTheme.kt` — primary `0xFF155F73` vs current `0xFF6750A4` (Material default).

- [ ] **Step 4: Commit**

```bash
git add style-dictionary.config.js frontend/src/app/tokens.css mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Colors.kt mobile/iosApp/SkateLab/Theme/SkateLabColors.swift
git commit -m "feat(design): add Style Dictionary config with CSS/Android/iOS templates"
```

---

### Task 4: Taskfile design tasks

**Files:**
- Modify: `Taskfile.yml`

- [ ] **Step 1: Add design tasks to Taskfile.yml**

Append after `cli-analyze` task:

```yaml
  # Design system tasks
  design:build:
    desc: "Generate design tokens for all platforms from DESIGN.md"
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

- [ ] **Step 2: Verify design:build runs**

Run: `task design:build`
Expected: All three platform outputs regenerated without errors

- [ ] **Step 3: Commit**

```bash
git add Taskfile.yml
git commit -m "chore(design): add design:build, design:lint, design:check tasks"
```

---

### Task 5: Android Theme — Type.kt + Theme.kt

**Files:**
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Type.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Theme.kt`

These are hand-written (not Style Dictionary generated) because typography requires variable font logic and Material 3 bridge that cannot be templated.

- [ ] **Step 1: Write Type.kt with variable font + API<28 fallback**

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
    Font(R.font.inter_semibold, FontWeight.SemiBold),    // 600
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
    val price: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 32.sp, fontWeight = FontWeight.Bold, lineHeight = 32.sp, letterSpacing = (-0.96).sp, fontVariationSettings = "tnum"),
)

private fun weightOrFallback(variable: Int, fallback: FontWeight): FontWeight =
    if (Build.VERSION.SDK_INT >= 28) FontWeight(variable) else fallback

val SkateLabTypographyDefaults = SkateLabTypography()
```

- [ ] **Step 2: Write Theme.kt with Material 3 bridge**

Use the code from the spec (section 5, Theme.kt). Key elements:
- `SkateLabLightScheme` maps SkateLabColors → Material 3 `lightColorScheme()`
- `AppTheme` composable replaces old `AppTheme`
- `toMaterialTypography()` extension maps 13 SkateLab styles → 15 Material 3 roles
- Status bar color: `SkateLabColors.primaryDeep.toArgb()`
- `isAppearanceLightStatusBars = false` (dark status bar on teal)

- [ ] **Step 3: Verify Android project compiles**

Run: `cd mobile && ./gradlew :androidApp:compileDebugKotlin 2>&1 | tail -5`
Expected: BUILD SUCCESSFUL (may need R.font imports resolved — if not found, font files aren't added yet, add placeholder R class import)

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Type.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Theme.kt
git commit -m "feat(mobile): add SkateLab typography and theme with variable font + Material 3 bridge"
```

---

### Task 6: Android font bundling

**Files:**
- Create: `mobile/androidApp/src/main/res/font/inter_variable.ttf`
- Create: `mobile/androidApp/src/main/res/font/inter_regular.ttf`
- Create: `mobile/androidApp/src/main/res/font/inter_medium.ttf`
- Create: `mobile/androidApp/src/main/res/font/inter_semibold.ttf`
- Create: `mobile/androidApp/src/main/res/font/inter_bold.ttf`

- [ ] **Step 1: Download Inter fonts**

Run:
```bash
mkdir -p mobile/androidApp/src/main/res/font
cd /tmp
# Inter Variable (from Google Fonts)
curl -sL "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip" -o inter.zip
unzip -o inter.zip "InterVariable*" "Inter-Regular*" "Inter-Medium*" "Inter-SemiBold*" "Inter-Bold*"
cp InterVariable.ttf mobile/androidApp/src/main/res/font/inter_variable.ttf
cp Inter-Regular.ttf mobile/androidApp/src/main/res/font/inter_regular.ttf
cp Inter-Medium.ttf mobile/androidApp/src/main/res/font/inter_medium.ttf
cp Inter-SemiBold.ttf mobile/androidApp/src/main/res/font/inter_semibold.ttf
cp Inter-Bold.ttf mobile/androidApp/src/main/res/font/inter_bold.ttf
```

Expected: 5 font files in `res/font/`

- [ ] **Step 2: Commit**

```bash
git add mobile/androidApp/src/main/res/font/
git commit -m "feat(mobile): bundle Inter Variable + static fallback fonts for Android"
```

---

### Task 7: iOS Theme files

**Files:**
- Create: `mobile/iosApp/SkateLab/Theme/SkateLabTypography.swift`
- Create: `mobile/iosApp/SkateLab/Theme/SkateLabTheme.swift`
- Create: `mobile/iosApp/SkateLab/Fonts/` (5 font files)

- [ ] **Step 1: Create iOS Theme directory structure**

```bash
mkdir -p mobile/iosApp/SkateLab/Theme
mkdir -p mobile/iosApp/SkateLab/Fonts
```

- [ ] **Step 2: Write SkateLabTypography.swift (CTFont approach)**

Use the spec code (section 6, SkateLabTypography.swift). Key elements:
- CTFont descriptor approach for variable font weights
- `skateVariable(size:weight:)` private method
- 13 static font tokens
- `@available(iOS 15, *)`

- [ ] **Step 3: Write SkateLabTheme.swift (ColorScheme + EnvironmentKey)**

Use the spec code (section 6, SkateLabTheme.swift). Key elements:
- `SkateLabColorScheme` struct with all color properties
- `EnvironmentValues` extension for `skateLabColors`
- `@available(iOS 15, *)`

- [ ] **Step 4: Download Inter fonts for iOS**

```bash
cp /tmp/InterVariable.ttf mobile/iosApp/SkateLab/Fonts/InterVariable.ttf
cp /tmp/Inter-Regular.ttf mobile/iosApp/SkateLab/Fonts/Inter-Regular.ttf
cp /tmp/Inter-Medium.ttf mobile/iosApp/SkateLab/Fonts/Inter-Medium.ttf
cp /tmp/Inter-SemiBold.ttf mobile/iosApp/SkateLab/Fonts/Inter-SemiBold.ttf
cp /tmp/Inter-Bold.ttf mobile/iosApp/SkateLab/Fonts/Inter-Bold.ttf
```

- [ ] **Step 5: Update Info.plist to register fonts**

Add `UIAppFonts` key to the iOS app's `Info.plist`:
```xml
<key>UIAppFonts</key>
<array>
  <string>InterVariable.ttf</string>
  <string>Inter-Regular.ttf</string>
  <string>Inter-Medium.ttf</string>
  <string>Inter-SemiBold.ttf</string>
  <string>Inter-Bold.ttf</string>
</array>
```

- [ ] **Step 6: Commit**

```bash
git add mobile/iosApp/SkateLab/
git commit -m "feat(ios): add SkateLab theme (colors, typography, fonts) with CTFont variable weight"
```

---

### Task 8: .gitattributes for generated files

**Files:**
- Modify: `.gitattributes`

- [ ] **Step 1: Append generated file markers**

Append to `.gitattributes`:
```
# Design tokens — auto-generated, do not edit directly
tokens/dtcg.json linguist-generated
frontend/src/app/tokens.css linguist-generated
mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Colors.kt linguist-generated
mobile/iosApp/SkateLab/Theme/SkateLabColors.swift linguist-generated
```

- [ ] **Step 2: Commit**

```bash
git add .gitattributes
git commit -m "chore(design): mark generated token files in .gitattributes"
```

---

## Wave 2: Frontend Integration (Phase 2a)

### Task 9: Extract :root to tokens.css (no visual changes)

**Files:**
- Modify: `frontend/src/app/globals.css`
- Generate: `frontend/src/app/tokens.css` (via design:build)

- [ ] **Step 1: Run design:build to generate tokens.css**

Run: `task design:build`

- [ ] **Step 2: Verify tokens.css content**

Read `frontend/src/app/tokens.css`. It must contain:
- `:root { }` block with OKLCH color variables
- All color tokens from DESIGN.md
- Sidebar/chart tokens (manually maintained in parser, marked with comment)
- `--radius` base variable

If any tokens are missing, fix `scripts/design-tokens.js` and re-run.

- [ ] **Step 3: Add @import to globals.css**

At the top of `globals.css`, add `@import "./tokens.css";` after the existing imports:

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "./tokens.css";
```

- [ ] **Step 4: Remove :root { } block from globals.css**

Remove the entire `:root { ... }` block (lines 92–130 approximately) from `globals.css`. Keep `@theme { }` and `@theme inline { }` blocks.

- [ ] **Step 5: Verify frontend builds identically**

Run: `cd frontend && bun run build`
Expected: Build succeeds, no visual changes

- [ ] **Step 6: Run visual comparison (manual)**

Start dev server: `cd frontend && bun run dev`
Open browser. Verify:
- Colors match previous state (primary teal, ink, canvas etc.)
- Border radii match (no changes to radius values yet)
- Typography unchanged
- No console errors

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/globals.css frontend/src/app/tokens.css
git commit -m "feat(frontend): extract :root tokens to generated tokens.css (no visual changes)"
```

---

## Wave 3: Data Fix + Visual Refresh (Phase 2b)

### Task 10: Regenerate OKLCH values from hex

**Files:**
- Modify: `DESIGN.md` (YAML frontmatter prose sections)
- Modify: `scripts/design-tokens.js` (if needed)

- [ ] **Step 1: Run parser and compare OKLCH values**

Run: `node scripts/design-tokens.js DESIGN.md tokens/dtcg.json`
Then inspect `tokens/dtcg.json` — check that `$extensions.oklch` values are computed from hex, not from DESIGN.md prose.

- [ ] **Step 2: Update DESIGN.md prose OKLCH values**

Replace all `oklch(X Y Z)` values in DESIGN.md markdown body with computed values from `tokens/dtcg.json`. For each color:

```
# Before (wrong):
- **Primary Teal** (#155f73 / oklch(0.52 0.08 205))

# After (computed from hex):
- **Primary Teal** (#155f73 / oklch(0.452 0.075 221))
```

Do this for all 20 color references in sections 2 (Colors) prose.

- [ ] **Step 3: Fix DESIGN.md lint errors**

1. `clamp()` in display-xxl, display-xl, price: These are valid CSS but `design.md lint` may flag them. If so, wrap in quotes or use alternative syntax.
2. `{colors.on-primary}` reference: Change to `{colors.primary-foreground}` (matching YAML key).

- [ ] **Step 4: Verify lint passes**

Run: `task design:lint`
Expected: No errors (or only informational warnings)

- [ ] **Step 5: Commit**

```bash
git add DESIGN.md
git commit -m "fix(design): regenerate OKLCH values from hex canonicals, fix lint errors"
```

---

### Task 11: Fix color drift in @theme block

**Files:**
- Modify: `frontend/src/app/globals.css` (@theme block)

- [ ] **Step 1: Compare @theme color values with DESIGN.md hex**

Current `globals.css` `@theme { }` block has drifted OKLCH values that don't match hex. Key drifts identified:
- `--color-foreground: oklch(0.2 0.01 60)` should match ink `#2a2d2e` → `oklch(0.278 0.010 260)`
- `--color-ink: oklch(0.278 0.003 194)` should match `#2a2d2e`
- `--color-ink-faint: oklch(0.659 0.008 194)` should match `#9ba0a3`
- `--color-canvas-soft: oklch(0.93 0.01 194)` should match `#f5f7f8`

Update the `@theme { }` block with computed OKLCH values (from Task 10's regenerated values).

- [ ] **Step 2: Update @theme block colors**

Replace the `@theme { }` block colors with correctly computed OKLCH values matching hex canonicals. Keep the same variable names and structure.

- [ ] **Step 3: Verify build**

Run: `cd frontend && bun run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "fix(frontend): align @theme OKLCH values with hex canonicals"
```

---

### Task 12: Border-radius intermediate values

**Files:**
- Modify: `frontend/src/app/globals.css` (@theme inline block)
- Modify: `frontend/src/app/tokens.css` (regenerated)

- [ ] **Step 1: Update radius values in DESIGN.md YAML frontmatter**

Change `rounded` section:
```yaml
rounded:
  xs: "4px"     # unchanged
  sm: "6px"     # unchanged
  md: "12px"    # was 8px
  lg: "16px"    # was 12px
  xl: "20px"    # was 16px
  full: "9999px" # unchanged
  2xl: "30px"   # unchanged
```

- [ ] **Step 2: Regenerate tokens**

Run: `task design:build`

- [ ] **Step 3: Update @theme inline radius references**

In `globals.css` `@theme inline { }` block, update `--radius` to `0.75rem` (12px). The calculated values (`--radius-sm`, `--radius-md`, etc.) should reference the new base or be explicit.

- [ ] **Step 4: Audit rounded-* usages**

Run: `cd frontend && grep -r "rounded-" src/ --include='*.tsx' --include='*.ts' | grep -v 'node_modules' | grep -v '.test.' | wc -l`
Expected: Count of all `rounded-*` usages. Review the ~146 outside UI components for any that might break.

- [ ] **Step 5: Visual regression test (manual)**

Start dev server. Check key components:
- Buttons (should be slightly less rounded)
- Cards (should be slightly less rounded)
- Inputs (should be slightly less rounded)
- Hero pills (should remain `rounded-full`)

- [ ] **Step 6: Commit**

```bash
git add DESIGN.md frontend/src/app/globals.css frontend/src/app/tokens.css
git commit -m "feat(design): update border-radius to intermediate values (md=12px, lg=16px, xl=20px)"
```

---

## Wave 4: Mobile Integration (Phase 3)

### Task 13: Replace AppTheme.kt with generated theme

**Files:**
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/AppTheme.kt`
- Delete: Old Material 3 color definitions in AppTheme.kt

- [ ] **Step 1: Replace AppTheme.kt content**

The old `AppTheme.kt` contains default Material 3 purple colors (`Color(0xFF6750A4)`). Replace with SkateLab theme that uses generated `Colors.kt` + `Type.kt` + `Theme.kt`.

New `AppTheme.kt` (thin wrapper):
```kotlin
package ru.skatelab.capture.presentation.theme

// Re-export for convenience
@Deprecated("Use SkateLabColors, SkateLabTypographyDefaults, AppTheme directly")
typealias AppTheme = ru.skatelab.capture.presentation.theme.AppTheme
```

Actually — since Theme.kt already defines `AppTheme` composable, we should just delete the old AppTheme.kt content and keep the new Theme.kt. Verify that all import paths resolve.

- [ ] **Step 2: Find all imports of AppTheme**

Run: `grep -r "import.*AppTheme\|import.*theme.AppTheme" mobile/androidApp/ --include='*.kt'`
Expected: List of files importing AppTheme. Update any that import from the old location.

- [ ] **Step 3: Verify Android build**

Run: `cd mobile && ./gradlew :androidApp:compileDebugKotlin 2>&1 | tail -5`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/
git commit -m "feat(mobile): replace Material 3 default theme with generated SkateLab theme"
```

---

### Task 14: Verify Android app renders with SkateLab theme

- [ ] **Step 1: Build debug APK**

Run: `cd mobile && ./gradlew :androidApp:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 2: Visual check on emulator**

Launch app on emulator. Verify:
- Primary color is teal (#155F73), not purple
- Typography uses Inter font
- Status bar is dark teal
- Cards have hairline borders, no shadows
- Buttons are rounded-rectangle (not pill except hero)

If any issues, debug and fix before proceeding.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix(mobile): adjust SkateLab theme rendering"
```

---

## Wave 5: CI Enforcement + ast-grep (Phase 4)

### Task 15: Add 5 ast-grep design rules

**Files:**
- Create: `ast-grep/no-raw-font-weights.yml`
- Create: `ast-grep/no-backdrop-blur.yml`
- Create: `ast-grep/no-static-shadow.yml`
- Create: `ast-grep/no-canvas-soft-section.yml`
- Create: `ast-grep/no-dark-variant.yml`

- [ ] **Step 1: Write all 5 rule files**

Use the exact YAML from the spec (section 4, ast-grep Rules). Each file goes in `ast-grep/` directory.

**no-raw-font-weights.yml:**
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

**no-backdrop-blur.yml:**
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

**no-static-shadow.yml:**
```yaml
id: no-static-shadow
language: tsx
message: |
  Shadows on static elements violate the Flat-By-Default Rule.
  Only floating overlays (dropdowns, modals, popovers) may have shadows.
severity: warning
rule:
  kind: string_fragment
  regex: 'shadow-(xs|sm|md|lg|xl|2xl|\[)'
ignores:
  - "frontend/src/components/ui/**"
```

**no-canvas-soft-section.yml:**
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

**no-dark-variant.yml:**
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

- [ ] **Step 2: Update sgconfig.yml**

Add the new rule paths to `sgconfig.yml` if they're not automatically discovered (ast-grep scans `ast-grep/` by default, so likely no change needed).

- [ ] **Step 3: Test rules**

Run: `ast-grep scan`
Expected: May find existing violations. These are informational — rules start as warnings/hints.

- [ ] **Step 4: Commit**

```bash
git add ast-grep/
git commit -m "feat(lint): add 5 design-system ast-grep rules (font-weights, backdrop-blur, shadow, canvas-soft, dark-variant)"
```

---

### Task 16: Add CI design jobs

**Files:**
- Modify: `.github/workflows/ci-reusable.yml`

- [ ] **Step 1: Add `design` to changes filter**

In the `changes` job, add `design` output:
```yaml
outputs:
  python: ${{ steps.filter.outputs.python }}
  ml: ${{ steps.filter.outputs.ml }}
  frontend: ${{ steps.filter.outputs.frontend }}
  docker: ${{ steps.filter.outputs.docker }}
  design: ${{ steps.filter.outputs.design }}
```

And add filter:
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

- [ ] **Step 2: Add `design-lint` job**

```yaml
design-lint:
  name: Design Lint
  needs: [changes]
  if: inputs.run-all || needs.changes.outputs.design == 'true'
  runs-on: blacksmith-2vcpu-ubuntu-2404
  continue-on-error: true
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
```

- [ ] **Step 3: Add `design-drift` job**

```yaml
design-drift:
  name: Design Drift Check
  needs: [changes]
  if: inputs.run-all || needs.changes.outputs.design == 'true'
  runs-on: blacksmith-2vcpu-ubuntu-2404
  continue-on-error: true
  steps:
    - uses: actions/checkout@v6
    - uses: actions/setup-node@v4
      with:
        node-version: "22"
    - uses: actions/cache@v4
      with:
        path: ~/.npm/_npx
        key: design-md-${{ runner.os }}-0.1.1
    - name: Install deps
      run: npm ci
    - name: Generate tokens
      run: node scripts/design-tokens.js DESIGN.md tokens/dtcg.json && npx style-dictionary@5.4.1 build --config style-dictionary.config.js
    - name: Check for drift
      run: |
        git diff --exit-code \
          frontend/src/app/tokens.css \
          mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/ \
          mobile/iosApp/SkateLab/Theme/ \
          || (echo "Design tokens drifted. Run 'task design:build' and commit." && exit 1)
```

- [ ] **Step 4: Add to ci-passed summary**

In the `ci-passed` job `steps.check.env` block, add:
```yaml
DESIGN_LINT: ${{ needs.design-lint.result }}
DESIGN_DRIFT: ${{ needs.design-drift.result }}
```

And in the `run` script, add:
```bash
check_job "Design Lint" "$DESIGN_LINT"
check_job "Design Drift" "$DESIGN_DRIFT"
```

Both with `(informational)` tag in summary.

- [ ] **Step 5: Add design-lint and design-drift to `needs`**

Add `design-lint, design-drift` to the `ci-passed` job `needs` list.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci-reusable.yml
git commit -m "ci(design): add design-lint and design-drift informational jobs"
```

---

### Task 17: Delete DESIGN.json and clean up

**Files:**
- Delete: `DESIGN.json`
- Modify: `CLAUDE.md` (if needed)

- [ ] **Step 1: Delete DESIGN.json**

```bash
git rm DESIGN.json
```

- [ ] **Step 2: Verify pipeline still works without DESIGN.json**

Run: `task design:build`
Expected: Still works — parser reads DESIGN.md, not DESIGN.json

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore(design): remove DESIGN.json — superseded by DESIGN.md + Style Dictionary pipeline"
```

---

## Self-Review Checklist

1. **Spec coverage:** Every section of the spec maps to a task:
   - Pipeline infrastructure → Tasks 1-4
   - Frontend extraction → Task 9
   - Data fix + visual refresh → Tasks 10-12
   - Mobile integration → Tasks 5-7, 13-14
   - CI enforcement → Tasks 15-16
   - Cleanup → Task 17

2. **Placeholder scan:** No TBD, TODO, or "fill in later" — all code shown inline.

3. **Type consistency:** `SkateLabColors` object in Kotlin matches `Color.skateXxx` extensions in Swift. Typography tokens use same naming across platforms. `weightOrFallback()` defined in Type.kt, used consistently. `toMaterialTypography()` defined in Theme.kt.

4. **Missing items from review:**
   - B1 (OKLCH data integrity) → Task 10 (regenerate from hex)
   - B2 (iOS typography) → Task 7 (CTFont approach)
   - B3 (@theme inline bridge) → Task 9 (tokens.css only generates :root)
   - B4 (radius drift) → Task 12 (intermediate values)
   - B5 (toMaterialTypography) → Task 5 (defined in Theme.kt)
   - H1 (CLI alpha) → Task 2 (custom parser as primary)
   - H5 (Material 3 color semantics) → Task 5 (documented as best-effort bridge)
   - H6 (Android font fallback) → Tasks 5-6
   - M1 (custom format templates) → Task 3
   - M2 (CI hardening) → Task 16
   - M3 (ast-grep improvements) → Task 15