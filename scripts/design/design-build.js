#!/usr/bin/env node
/**
 * design-build.js — LLM-based design token generator
 *
 * Replaces Style Dictionary with a 2-phase pipeline:
 *   Phase 1: Architect call extracts shared vocabulary from DESIGN.md
 *   Phase 2: Platform fan-out generates CSS, Kotlin, Swift files in parallel
 *
 * Usage:
 *   node scripts/design-build.js [--trigger <all|tokens|components|shadows>] [--force]
 *
 * Flags:
 *   --trigger   Which sections to regenerate (default: all)
 *   --force     Skip hash check, always regenerate
 *
 * Hash check: Reads design.lock, computes SHA-256 of DESIGN.md.
 *   If unchanged, exits 0 (no-op). Use --force to override.
 *
 * Circuit breaker: After 5 consecutive failures, skips generation
 *   and requires manual review (clear tokens/build.log to reset).
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync, appendFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { execa, execaSync } from "execa";
import PQueue from "p-queue";

// ─── Paths ────────────────────────────────────────────────────────────────

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const DESIGN_MD = resolve(ROOT, "DESIGN.md");
const LOCK_FILE = resolve(ROOT, "design.lock");
const BUILD_LOG = resolve(ROOT, "scripts", "design", "build.log");
const GLOBALS_CSS = resolve(ROOT, "frontend", "src", "app", "globals.css");

const PLATFORM_FILES = {
  css: ["frontend/src/app/tokens.css"],
  kotlin: [
    "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabColors.kt",
    "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Type.kt",
    "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Theme.kt",
    "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabShadows.kt",
    "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabModifiers.kt",
  ],
  swift: [
    "mobile/iosApp/SkateLab/Theme/SkateLabColors.swift",
    "mobile/iosApp/SkateLab/Theme/SkateLabTypography.swift",
    "mobile/iosApp/SkateLab/Theme/SkateLabTheme.swift",
    "mobile/iosApp/SkateLab/Theme/SkateLabShadows.swift",
    "mobile/iosApp/SkateLab/Theme/SkateLabModifiers.swift",
  ],
};

// ─── Model Selection ─────────────────────────────────────────────────────────

const DESIGN_MODEL = process.env.DESIGN_MODEL || process.env.ANTHROPIC_DEFAULT_OPUS_MODEL || "opus";

// ─── Arg Parsing ───────────────────────────────────────────────────────────

if (process.argv.includes('--help') || process.argv.includes('-h')) {
  console.log(`Usage: design-build.js [options]

Options:
  --trigger <all|tokens|components|shadows>  Sections to regenerate (default: all)
  --force                                    Force regeneration even if DESIGN.md unchanged
  --help                                     Show this help`);
  process.exit(0);
}

const args = process.argv.slice(2);
let trigger = "all";
let force = false;

for (let i = 0; i < args.length; i++) {
  if (args[i] === "--trigger" && args[i + 1]) {
    trigger = args[i + 1];
    i++;
  }
  if (args[i] === "--force") {
    force = true;
  }
}

const VALID_TRIGGERS = ["all", "tokens", "components", "shadows"];
if (!VALID_TRIGGERS.includes(trigger)) {
  console.error(`Invalid trigger: ${trigger}. Valid: ${VALID_TRIGGERS.join(", ")}`);
  process.exit(1);
}

// ─── Hash Utilities ─────────────────────────────────────────────────────────

function sha256(content) {
  return "sha256:" + createHash("sha256").update(content).digest("hex");
}

function sectionHash(designContent, sectionName) {
  // Extract YAML section between markers or from frontmatter
  const yamlMatch = designContent.match(/^---\n([\s\S]*?)---/);
  if (!yamlMatch) return sha256(designContent);

  const yaml = yamlMatch[1];
  const sectionPattern = new RegExp(
    `^${sectionName}:\\s*\\n(\\s{2}[\\s\\S]*?)(?=^\\w|$(?!\\n))`,
    "m"
  );
  const sec = yaml.match(sectionPattern);
  return sha256(sec ? sec[0] : yaml);
}

// ─── Lock File ──────────────────────────────────────────────────────────────

function readLock() {
  if (!existsSync(LOCK_FILE)) return null;
  try {
    return JSON.parse(readFileSync(LOCK_FILE, "utf8"));
  } catch {
    return null;
  }
}

function writeLock(data) {
  const dir = dirname(LOCK_FILE);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  writeFileSync(LOCK_FILE, JSON.stringify(data, null, 2) + "\n");
}

function hashCheck(designContent) {
  if (force) {
    console.log("Force flag set — skipping hash check.");
    return false;
  }
  const lock = readLock();
  if (!lock) {
    console.log("No design.lock found — will generate.");
    return false;
  }
  if (lock.version !== 2) {
    console.log("Lock version mismatch — will regenerate.");
    return false;
  }
  const currentHash = sha256(designContent);
  if (lock.designMdHash === currentHash) {
    console.log("DESIGN.md unchanged — skipping generation.");
    return true;
  }
  console.log("DESIGN.md changed — will regenerate.");
  return false;
}

// ─── Circuit Breaker ────────────────────────────────────────────────────────

const MAX_CONSECUTIVE_FAILURES = 5;

function readConsecutiveFailures() {
  if (!existsSync(BUILD_LOG)) return 0;
  try {
    const log = readFileSync(BUILD_LOG, "utf8");
    const lines = log.trim().split("\n").filter(Boolean);
    let count = 0;
    for (let i = lines.length - 1; i >= 0; i--) {
      const entry = JSON.parse(lines[i]);
      if (entry.status === "failure") {
        count++;
      } else if (entry.status === "success") {
        break;
      }
    }
    return count;
  } catch {
    return 0;
  }
}

function appendBuildLog(entry) {
  const dir = dirname(BUILD_LOG);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  const line = JSON.stringify({ ...entry, timestamp: new Date().toISOString() }) + "\n";
  appendFileSync(BUILD_LOG, line);
}

function checkCircuitBreaker() {
  const failures = readConsecutiveFailures();
  if (failures >= MAX_CONSECUTIVE_FAILURES) {
    console.error(
      `Circuit breaker: ${failures} consecutive failures. Skipping generation. Clear ${BUILD_LOG} to reset.`
    );
    fallbackRestore(allPlatformFilePaths());
    process.exit(1);
  }
}

// ─── DESIGN.md Parsing ──────────────────────────────────────────────────────

function parseDesignMd() {
  const content = readFileSync(DESIGN_MD, "utf8");
  return content;
}

// ─── Trigger Sections ───────────────────────────────────────────────────────

function getTriggerSections(trigger) {
  switch (trigger) {
    case "tokens":
      return ["colors", "typography", "spacing", "rounded"];
    case "components":
      return ["components"];
    case "shadows":
      return ["shadows"];
    case "all":
    default:
      return ["colors", "typography", "spacing", "rounded", "shadows", "components"];
  }
}

// ─── Comment Trigger Extraction ──────────────────────────────────────────────
// Reserved for future use: extracting <!-- generate:tokens|components|shadows|all -->
// HTML comments from DESIGN.md to selectively regenerate only triggered sections.
// Currently unused — all generation uses --trigger flag or defaults to "all".

function extractCommentTriggers(content) {
  const triggers = [];
  const regex = /<!--\s*generate:(all|tokens|components|shadows)\s*-->/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    triggers.push(match[1]);
  }
  // If no comment triggers found, treat entire document as triggered
  if (triggers.length === 0) {
    triggers.push("all");
  }
  return triggers;
}

// ─── JSON Schemas ───────────────────────────────────────────────────────────

const ARCHITECT_SCHEMA = {
  type: "object",
  properties: {
    colors: {
      type: "array",
      items: {
        type: "object",
        properties: {
          name: { type: "string" },
          oklch: { type: "string" },
          hex: { type: "string" },
        },
        required: ["name", "oklch", "hex"],
      },
    },
    semanticAliases: {
      type: "array",
      items: {
        type: "object",
        properties: {
          alias: { type: "string" },
          token: { type: "string" },
        },
        required: ["alias", "token"],
      },
    },
    typeScale: {
      type: "array",
      items: {
        type: "object",
        properties: {
          name: { type: "string" },
          size: { type: "string" },
          weight: { type: "number" },
          lineHeight: { type: "number" },
          letterSpacing: { type: "string" },
        },
        required: ["name", "size", "weight", "lineHeight"],
      },
    },
    shadows: {
      type: "array",
      items: {
        type: "object",
        properties: {
          name: { type: "string" },
          value: { type: "string" },
        },
        required: ["name", "value"],
      },
    },
    components: {
      type: "array",
      items: {
        type: "object",
        properties: {
          name: { type: "string" },
          tokens: {
            type: "object",
            additionalProperties: { type: "string" },
          },
        },
        required: ["name", "tokens"],
      },
    },
  },
  required: ["colors", "semanticAliases", "typeScale", "shadows", "components"],
};

const CSS_PLATFORM_SCHEMA = {
  type: "object",
  properties: {
    files: {
      type: "object",
      properties: {
        "frontend/src/app/tokens.css": { type: "string" },
      },
      required: ["frontend/src/app/tokens.css"],
    },
    globalsCssPatch: { type: "string" },
    validation: {
      type: "object",
      properties: {
        colorCount: { type: "number" },
        typographyCount: { type: "number" },
        shadowsCount: { type: "number" },
        componentsCount: { type: "number" },
      },
      required: ["colorCount", "typographyCount", "shadowsCount", "componentsCount"],
    },
  },
  required: ["files", "globalsCssPatch", "validation"],
};

const KOTLIN_PLATFORM_SCHEMA = {
  type: "object",
  properties: {
    files: {
      type: "object",
      properties: {
        "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabColors.kt": {
          type: "string",
        },
        "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Type.kt": {
          type: "string",
        },
        "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Theme.kt": {
          type: "string",
        },
        "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabShadows.kt": {
          type: "string",
        },
        "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabModifiers.kt": {
          type: "string",
        },
      },
      required: [
        "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabColors.kt",
        "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Type.kt",
        "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Theme.kt",
        "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabShadows.kt",
        "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabModifiers.kt",
      ],
    },
    validation: {
      type: "object",
      properties: {
        colorCount: { type: "number" },
        typographyCount: { type: "number" },
        shadowsCount: { type: "number" },
        componentsCount: { type: "number" },
      },
      required: ["colorCount", "typographyCount", "shadowsCount", "componentsCount"],
    },
  },
  required: ["files", "validation"],
};

const SWIFT_PLATFORM_SCHEMA = {
  type: "object",
  properties: {
    files: {
      type: "object",
      properties: {
        "mobile/iosApp/SkateLab/Theme/SkateLabColors.swift": { type: "string" },
        "mobile/iosApp/SkateLab/Theme/SkateLabTypography.swift": {
          type: "string",
        },
        "mobile/iosApp/SkateLab/Theme/SkateLabTheme.swift": { type: "string" },
        "mobile/iosApp/SkateLab/Theme/SkateLabShadows.swift": { type: "string" },
        "mobile/iosApp/SkateLab/Theme/SkateLabModifiers.swift": { type: "string" },
      },
      required: [
        "mobile/iosApp/SkateLab/Theme/SkateLabColors.swift",
        "mobile/iosApp/SkateLab/Theme/SkateLabTypography.swift",
        "mobile/iosApp/SkateLab/Theme/SkateLabTheme.swift",
        "mobile/iosApp/SkateLab/Theme/SkateLabShadows.swift",
        "mobile/iosApp/SkateLab/Theme/SkateLabModifiers.swift",
      ],
    },
    validation: {
      type: "object",
      properties: {
        colorCount: { type: "number" },
        typographyCount: { type: "number" },
        shadowsCount: { type: "number" },
        componentsCount: { type: "number" },
      },
      required: ["colorCount", "typographyCount", "shadowsCount", "componentsCount"],
    },
  },
  required: ["files", "validation"],
};

// ─── Prompts ─────────────────────────────────────────────────────────────────

function buildArchitectPrompt(designContent, sections) {
  return `You are a design system architect. Extract a shared vocabulary from DESIGN.md for cross-platform token generation.

DESIGN.md content:
---
${designContent}
---

Sections to extract: ${sections.join(", ")}

Return a JSON object with:
- colors: array of {name, oklch, hex} — every color token from DESIGN.md (all 23+ named colors including primary, primary-deep, ink variants, surface variants, semantic colors)
- semanticAliases: array of {alias, token} — shadcn semantic mappings (background→canvas, foreground→ink, etc.)
- typeScale: array of {name, size, weight, lineHeight, letterSpacing?} — all typography tokens from DESIGN.md
- shadows: array of {name, value} — all shadow tokens (ambient-low, ambient-medium, ambient-high)
- components: array of {name, tokens} — all component definitions from DESIGN.md (buttons, cards, badge, inputs, etc.)

IMPORTANT:
- Extract EVERY color from the YAML frontmatter AND prose sections. There are 23+ colors.
- Color names must use kebab-case matching DESIGN.md exactly (e.g. "primary-deep", not "primaryDeep").
- OKLCH values must be in format "oklch(L C H)" without the semicolon.
- Include spacing and radius tokens in the typeScale if mentioned, or as separate entries if needed.
- Components must include ALL button variants, card variants, badge, inputs, pill-tab, etc. At least 14 component definitions.`;
}

function buildCSSPlatformPrompt(designContent, vocab) {
  return `You are a CSS design token generator. Given DESIGN.md and the shared vocabulary below, generate the complete tokens.css file.

DESIGN.md content:
---
${designContent}
---

Shared vocabulary:
${JSON.stringify(vocab, null, 2)}

Generate a JSON object with:
1. "files": { "frontend/src/app/tokens.css": "<complete CSS file content>" }
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Must contain a :root { ... } block with ALL color tokens as OKLCH custom properties
   - Must include spacing tokens (--spacing-*)
   - Must include radius tokens (--radius-*)
   - Must include shadcn semantic aliases (--background, --foreground, etc.)
   - Each color variable must have a comment with the hex equivalent: /* #155f73 */
   - Use exact OKLCH values from the vocabulary

2. "globalsCssPatch": a string containing the COMPLETE content to replace between the "@layer base {" block and its closing "}" in globals.css. This includes:
   - All .sh-* typography utility classes (.sh-display-xxl, .sh-display-xl, etc.)
   - All .sh-* component classes (.sh-badge-opaque, .sh-badge-flat, .sh-teal-band, .sh-ice-backdrop)
   - The .sh-metric-pulse animation
   - The .scrollbar-hide class
   - The print media query rules
   - The prefers-reduced-motion media query
   - The html scroll-behavior rule
   - The section scroll-margin-top rule
   - The [data-sonner-toaster] bottom offset rule
   - The * border/outline rule
   - The body background/color rule
   - The html font-sans rule
   - The .sh-price class

3. "validation": { colorCount, typographyCount, shadowsCount, componentsCount }
   - colorCount: number of --color variables (must be >= 23)
   - typographyCount: number of .sh-* typography classes (must be >= 14)
   - shadowsCount: number of shadow definitions (must be >= 3)
   - componentsCount: number of .sh-* component classes (must be >= 14)`;
}

function buildKotlinPlatformPrompt(designContent, vocab) {
  return `You are an Android/Kotlin design token generator. Given DESIGN.md and the shared vocabulary below, generate Kotlin Compose theme files.

DESIGN.md content:
---
${designContent}
---

Shared vocabulary:
${JSON.stringify(vocab, null, 2)}

Generate a JSON object with:
1. "files": object with these exact keys:
   - "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabColors.kt": SkateLabColors.kt content
   - "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Type.kt": Type.kt content
   - "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Theme.kt": Theme.kt content
   - "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabShadows.kt": SkateLabShadows.kt content
   - "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabModifiers.kt": SkateLabModifiers.kt content

SkateLabColors.kt requirements:
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Package: ru.skatelab.capture.presentation.theme
   - Object SkateLabColors with Color vals for ALL 23+ color tokens
   - Use ARGB hex format: Color(0xFF155F73)
   - Include semantic aliases section (background, foreground, card, etc.)
   - Use exact kebab-case → camelCase conversion: primary-deep → primaryDeep

Type.kt requirements:
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Package: ru.skatelab.capture.presentation.theme
   - InterVariable FontFamily with weights 460, 540, 600, 700
   - InterFallback FontFamily for API < 28
   - SkateLabTypography data class with ALL typography tokens
   - weightOrFallback helper function
   - SkateLabTypographyDefaults val

Theme.kt requirements:
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Package: ru.skatelab.capture.presentation.theme
   - SkateLabLightScheme using lightColorScheme() mapping to SkateLabColors
   - SkateLabTheme object with colors and typography accessors
   - AppTheme composable with status bar color setup
   - toMaterialTypography() mapping function

SkateLabShadows.kt requirements:
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Package: ru.skatelab.capture.presentation.theme
   - Object SkateLabShadows with Modifier vals for each shadow token (ambient-low, ambient-medium, ambient-high)
   - Use Modifier.shadow() with appropriate offsetX, offsetY, blur, color values
   - Map shadow names from vocabulary exactly

SkateLabModifiers.kt requirements:
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Package: ru.skatelab.capture.presentation.theme
   - Object SkateLabModifiers with common Modifier combinations used in components
   - Include convenience modifiers for card backgrounds, badge styles, input styles, etc.
   - Reference SkateLabColors and SkateLabShadows

2. "validation": { colorCount, typographyCount, shadowsCount, componentsCount }
   - colorCount: number of Color vals in SkateLabColors (must be >= 23)
   - typographyCount: number of TextStyle vals in SkateLabTypography (must be >= 14)
   - shadowsCount: number of shadow definitions (must be >= 3, can be 0 for Kotlin)
   - componentsCount: number of component token sets (must be >= 14)`;
}

function buildSwiftPlatformPrompt(designContent, vocab) {
  return `You are an iOS/SwiftUI design token generator. Given DESIGN.md and the shared vocabulary below, generate SwiftUI theme files.

DESIGN.md content:
---
${designContent}
---

Shared vocabulary:
${JSON.stringify(vocab, null, 2)}

Generate a JSON object with:
1. "files": object with these exact keys:
   - "mobile/iosApp/SkateLab/Theme/SkateLabColors.swift": Color extensions
   - "mobile/iosApp/SkateLab/Theme/SkateLabTypography.swift": Font extensions
   - "mobile/iosApp/SkateLab/Theme/SkateLabTheme.swift": ColorScheme + environment
   - "mobile/iosApp/SkateLab/Theme/SkateLabShadows.swift": Shadow extensions
   - "mobile/iosApp/SkateLab/Theme/SkateLabModifiers.swift": ViewModifier extensions

SkateLabColors.swift requirements:
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Import SwiftUI
   - @available(iOS 15, *)
   - Extension Color with static let for ALL 23+ color tokens
   - Use Color(red:green:blue:) with 0-1 range values
   - Prefix with "skate" (e.g. skatePrimary, skateInkMute)
   - Include skateOnPrimary alias

SkateLabTypography.swift requirements:
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Import SwiftUI, CoreText
   - @available(iOS 15, *)
   - Private skateVariable helper using CTFont variable axis
   - Private skateStatic fallback helper
   - Static Font extensions for ALL typography tokens (skateDisplayXxl, skateDisplayXl, etc.)
   - At least 14 font tokens

SkateLabTheme.swift requirements:
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Import SwiftUI
   - @available(iOS 15, *)
   - SkateLabColorScheme struct with ALL color properties referencing Color.skate* extensions
   - EnvironmentValues extension for skateLabColors

SkateLabShadows.swift requirements:
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Import SwiftUI
   - @available(iOS 15, *)
   - Extension View with shadow modifier methods for each shadow token (ambient-low, ambient-medium, ambient-high)
   - Use .shadow() with appropriate radius, x, y, and color values
   - Map shadow names from vocabulary exactly

SkateLabModifiers.swift requirements:
   - Must start with comment: "AUTO-GENERATED — do not edit. Source: DESIGN.md"
   - Import SwiftUI
   - @available(iOS 15, *)
   - SkateLabCardModifier, SkateLabBadgeModifier, and other common ViewModifiers
   - Convenience View extensions referencing SkateLabColors and SkateLabShadows

2. "validation": { colorCount, typographyCount, shadowsCount, componentsCount }
   - colorCount: number of Color static lets (must be >= 23)
   - typographyCount: number of Font static lets (must be >= 14)
   - shadowsCount: number of shadow definitions (must be >= 3, can be 0 for Swift)
   - componentsCount: number of component token sets (must be >= 14)`;
}

// ─── Validation ──────────────────────────────────────────────────────────────

const MIN_COUNTS = {
  colorCount: 23,
  typographyCount: 14,
  shadowsCount: 3,
  componentsCount: 14,
};

function validateResponse(response, platform, architectVocab) {
  const errors = [];

  // Structural check — required keys
  if (!response.files || typeof response.files !== "object") {
    errors.push("Missing or invalid 'files' key");
    return errors;
  }

  if (!response.validation || typeof response.validation !== "object") {
    errors.push("Missing or invalid 'validation' key");
    return errors;
  }

  // Required file keys per platform (from PLATFORM_FILES single source of truth)
  const requiredFiles = PLATFORM_FILES[platform];

  for (const key of requiredFiles) {
    if (!response.files[key] || typeof response.files[key] !== "string") {
      errors.push(`Missing file key: ${key}`);
    }
  }

  // Count checks
  const v = response.validation;
  for (const [key, min] of Object.entries(MIN_COUNTS)) {
    if (typeof v[key] !== "number") {
      errors.push(`validation.${key} missing or not a number`);
    } else if (v[key] < min) {
      errors.push(
        `validation.${key}=${v[key]} is below minimum ${min}`
      );
    }
  }

  // Format-specific checks
  if (platform === "css") {
    const css = response.files["frontend/src/app/tokens.css"] || "";
    if (!css.includes(":root {")) {
      errors.push("CSS missing ':root {' block");
    }
    if (css.includes("undefined") || css.includes("null")) {
      errors.push("CSS contains undefined/null values");
    }
    // Cross-platform name consistency
    if (architectVocab && architectVocab.colors) {
      for (const c of architectVocab.colors) {
        const cssVar = `--${c.name.replace(/-/g, "-")}`;
        // Just check that the name pattern exists
        if (!css.includes(`--${c.name}`) && !css.includes(`--color-${c.name}`)) {
          // Colors in CSS might be mapped differently — only warn
        }
      }
    }
    // globalsCssPatch check for CSS platform
    if (!response.globalsCssPatch || typeof response.globalsCssPatch !== "string") {
      errors.push("Missing globalsCssPatch string for CSS platform");
    } else if (!response.globalsCssPatch.includes(".sh-")) {
      errors.push("globalsCssPatch missing .sh-* utility classes");
    }
  }

  if (platform === "kotlin") {
    const colors = response.files["mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/SkateLabColors.kt"] || "";
    if (!colors.includes("package ru.skatelab.capture.presentation.theme")) {
      errors.push("Kotlin Colors.kt missing package declaration");
    }
    if (!colors.includes("object SkateLabColors")) {
      errors.push("Kotlin Colors.kt missing SkateLabColors object");
    }
  }

  if (platform === "swift") {
    const colors = response.files["mobile/iosApp/SkateLab/Theme/SkateLabColors.swift"] || "";
    if (!colors.includes("import SwiftUI")) {
      errors.push("Swift file missing 'import SwiftUI'");
    }
    if (!colors.includes("extension Color")) {
      errors.push("Swift SkateLabColors.swift missing 'extension Color'");
    }
  }

  return errors;
}

// ─── Claude CLI Runner ──────────────────────────────────────────────────────

const MAX_RETRIES = 3;
const API_TIMEOUT_MS = 600_000; // 10 minutes (large outputs via proxy can be slow)

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getBackoffDelay(attempt) {
  // Exponential backoff with jitter: 1s, 2s, 4s base + random 0-500ms
  const base = Math.pow(2, attempt) * 1000;
  const jitter = Math.random() * 500;
  return base + jitter;
}

async function runClaude(prompt, schema, label, retryErrors = []) {
  let lastError = null;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      const delay = getBackoffDelay(attempt - 1);
      console.log(`  Retry ${attempt}/${MAX_RETRIES} for ${label} after ${Math.round(delay)}ms...`);
      await sleep(delay);
    }

    // Augment prompt with retry error context
    let augmentedPrompt = prompt;
    if (retryErrors.length > 0) {
      augmentedPrompt += `\n\nPrevious attempts failed validation with these errors:\n${retryErrors.join("\n")}\n\nPlease fix these issues in your response.`;
    }

    try {
      const result = await execa("claude", ["-p", augmentedPrompt, "--bare", "--output-format", "json", "--json-schema", JSON.stringify(schema), "--model", DESIGN_MODEL, "--tools", ""], {
        timeout: API_TIMEOUT_MS,
        reject: false,
        input: "",
      });

      if (result.failed) {
        const exitCode = result.exitCode;
        // 429 rate limit — retryable
        if (exitCode === 429 || result.stderr?.includes("429") || result.stderr?.includes("rate limit")) {
          lastError = new Error(`Rate limited (429): ${result.stderr}`);
          continue;
        }
        // 5xx server errors — retryable
        if (exitCode >= 500 && exitCode < 600) {
          lastError = new Error(`Server error (${exitCode}): ${result.stderr}`);
          continue;
        }
        // Other errors — check stderr for retryable patterns
        if (result.stderr?.includes("overloaded") || result.stderr?.includes("capacity")) {
          lastError = new Error(`Overloaded: ${result.stderr}`);
          continue;
        }
        // Non-retryable 4xx — immediate fallback
        throw new Error(`Claude CLI error (exit ${exitCode}): ${result.stderr || result.stdout}`);
      }

      // Parse JSON response — claude -p --output-format json wraps output in an envelope:
      // { "result": "<text>", "structured_output": {<json-schema output>}, "session_id": "..." }
      // With --json-schema, the actual data is in structured_output.
      let parsed;
      let envelope;
      try {
        envelope = JSON.parse(result.stdout);
        // Extract structured_output if present (from --json-schema), otherwise use result
        if (envelope.structured_output && typeof envelope.structured_output === "object") {
          parsed = envelope.structured_output;
        } else if (envelope.result && typeof envelope.result === "string") {
          // Try to extract JSON from result (may be wrapped in ```json...```)
          let resultText = envelope.result;
          const jsonMatch = resultText.match(/```json\s*([\s\S]*?)```/);
          if (jsonMatch) resultText = jsonMatch[1].trim();
          try {
            parsed = JSON.parse(resultText);
          } catch {
            parsed = envelope;
          }
        } else {
          parsed = envelope;
        }
        if (process.env.DEBUG_DESIGN_BUILD) {
          console.log(`  [DEBUG] ${label} envelope keys: ${Object.keys(envelope).join(", ")}`);
          console.log(`  [DEBUG] ${label} structured_output: ${JSON.stringify(envelope.structured_output)?.substring(0, 200)}`);
          console.log(`  [DEBUG] ${label} parsed keys: ${Object.keys(parsed).join(", ")}`);
        }
      } catch (parseErr) {
        lastError = new Error(`JSON parse error: ${parseErr.message}. Output: ${result.stdout.substring(0, 500)}`);
        continue;
      }

      // Check for truncation in envelope
      if (envelope.stop_reason === 'length' || envelope.finish_reason === 'length') {
        throw new Error('LLM response was truncated (stop_reason=length). Consider simplifying the prompt or increasing max output length.');
      }

      return parsed;
    } catch (err) {
      if (err.message?.includes("Timed out")) {
        lastError = new Error(`Timeout after ${API_TIMEOUT_MS / 1000}s for ${label}`);
        continue;
      }
      // Non-retryable error — rethrow
      throw err;
    }
  }

  throw lastError || new Error(`All ${MAX_RETRIES} retries exhausted for ${label}`);
}

// ─── File Writing ─────────────────────────────────────────────────────────────

function writePlatformFiles(files) {
  for (const [relPath, content] of Object.entries(files)) {
    const absPath = resolve(ROOT, relPath);
    if (!absPath.startsWith(ROOT + sep)) {
      throw new Error(`Refusing to write outside project root: ${relPath}`);
    }
    const dir = dirname(absPath);
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    writeFileSync(absPath, content, "utf8");
    console.log(`  Written: ${relPath}`);
  }
}

// ─── Git Fallback Restore ──────────────────────────────────────────────────────

function fallbackRestore(files) {
  const existingFiles = files.filter(f => existsSync(resolve(ROOT, f)));
  if (existingFiles.length === 0) return;
  try {
    execaSync("git", ["checkout", "HEAD", "--", ...existingFiles], { cwd: ROOT });
    console.log("Restored last committed versions of generated files");
  } catch {
    console.error("Failed to restore files via git checkout");
  }
}

/** Collect all generated file paths from PLATFORM_FILES for fallback restore */
function allPlatformFilePaths() {
  const paths = [];
  for (const files of Object.values(PLATFORM_FILES)) {
    if (Array.isArray(files)) {
      paths.push(...files);
    }
  }
  return paths;
}

// ─── globals.css Patching ────────────────────────────────────────────────────

function patchGlobalsCss(patch) {
  if (!existsSync(GLOBALS_CSS)) {
    console.warn(`  Warning: ${GLOBALS_CSS} not found, skipping globals.css patch.`);
    return;
  }

  let content = readFileSync(GLOBALS_CSS, "utf8");

  // Replace the @layer base { ... } block
  // We need to find the block starting from "@layer base {" to its closing "}"
  // But we must be careful about nested braces
  const layerBaseStart = content.indexOf("@layer base {");
  if (layerBaseStart === -1) {
    console.warn("  Warning: @layer base { not found in globals.css, skipping patch.");
    return;
  }

  // Find the matching closing brace
  let depth = 0;
  let inLayer = false;
  let layerEnd = -1;
  for (let i = layerBaseStart; i < content.length; i++) {
    if (content[i] === "{") {
      depth++;
      inLayer = true;
    } else if (content[i] === "}" && inLayer) {
      depth--;
      if (depth === 0) {
        layerEnd = i + 1;
        break;
      }
    }
  }

  if (layerEnd === -1) {
    console.warn("  Warning: Could not find @layer base closing brace, skipping patch.");
    return;
  }

  // Replace the @layer base block
  const newLayerBase = `@layer base {\n${patch}\n}`;
  content = content.substring(0, layerBaseStart) + newLayerBase + content.substring(layerEnd);

  writeFileSync(GLOBALS_CSS, content, "utf8");
  console.log("  Patched: frontend/src/app/globals.css");
}

// ─── Lock File Update ────────────────────────────────────────────────────────

function computeSectionHashes(designContent) {
  return {
    colors: sectionHash(designContent, "colors"),
    typography: sectionHash(designContent, "typography"),
    shadows: sectionHash(designContent, "shadows"),
    components: sectionHash(designContent, "components"),
  };
}

function updateLock(designContent, platformResults) {
  const files = {};
  for (const [platform, result] of Object.entries(platformResults)) {
    if (result.files) {
      for (const [relPath, content] of Object.entries(result.files)) {
        files[relPath] = sha256(content);
      }
    }
  }

  const lock = {
    version: 2,
    designMdHash: sha256(designContent),
    sectionHashes: computeSectionHashes(designContent),
    files,
    platformHashes: {},
    generatedAt: new Date().toISOString(),
  };

  // Compute per-platform file content hashes
  for (const [platform, result] of Object.entries(platformResults)) {
    if (result.files) {
      const hashes = {};
      for (const [path, content] of Object.entries(result.files)) {
        hashes[path] = sha256(content);
      }
      lock.platformHashes[platform] = hashes;
    }
  }

  writeLock(lock);
  console.log("  Updated: design.lock");
}

// ─── Main Pipeline ──────────────────────────────────────────────────────────

async function main() {
  console.log("=== design-build.js — LLM Token Generator ===");
  console.log(`Trigger: ${trigger}`);

  // Read DESIGN.md
  const designContent = parseDesignMd();
  console.log(`Read DESIGN.md (${designContent.length} bytes)`);

  // Hash check — skip if unchanged
  if (hashCheck(designContent)) {
    process.exit(0);
  }

  // Circuit breaker check
  checkCircuitBreaker();

  // Determine sections to extract
  const sections = getTriggerSections(trigger);
  const commentTriggers = extractCommentTriggers(designContent);
  console.log(`Sections: ${sections.join(", ")}`);
  console.log(`Comment triggers: ${commentTriggers.join(", ")}`);

  // ─── Phase 1: Architect Call ─────────────────────────────────────────────

  console.log("\n--- Phase 1: Architect ---");
  let architectVocab;
  let architectErrors = [];

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      architectVocab = await runClaude(
        buildArchitectPrompt(designContent, sections),
        ARCHITECT_SCHEMA,
        "architect",
        architectErrors
      );

      // Validate architect response
      if (!architectVocab.colors || architectVocab.colors.length < MIN_COUNTS.colorCount) {
        architectErrors.push(
          `Architect returned ${architectVocab.colors?.length || 0} colors, need >= ${MIN_COUNTS.colorCount}`
        );
        continue;
      }
      if (!architectVocab.typeScale || architectVocab.typeScale.length < MIN_COUNTS.typographyCount) {
        architectErrors.push(
          `Architect returned ${architectVocab.typeScale?.length || 0} type tokens, need >= ${MIN_COUNTS.typographyCount}`
        );
        continue;
      }
      if (!architectVocab.shadows || architectVocab.shadows.length < MIN_COUNTS.shadowsCount) {
        architectErrors.push(
          `Architect returned ${architectVocab.shadows?.length || 0} shadows, need >= ${MIN_COUNTS.shadowsCount}`
        );
        continue;
      }
      if (!architectVocab.components || architectVocab.components.length < MIN_COUNTS.componentsCount) {
        architectErrors.push(
          `Architect returned ${architectVocab.components?.length || 0} components, need >= ${MIN_COUNTS.componentsCount}`
        );
        continue;
      }

      console.log(
        `  Architect: ${architectVocab.colors.length} colors, ${architectVocab.typeScale.length} type tokens, ${architectVocab.shadows.length} shadows, ${architectVocab.components.length} components`
      );
      break;
    } catch (err) {
      architectErrors.push(err.message);
      if (attempt === MAX_RETRIES) {
        console.error(`  Architect failed after ${MAX_RETRIES} retries: ${err.message}`);
        appendBuildLog({ phase: "architect", status: "failure", error: err.message });
        fallbackRestore(allPlatformFilePaths());
        process.exit(1);
      }
      console.log(`  Architect attempt ${attempt + 1} failed: ${err.message}`);
    }
  }

  // ─── Phase 2: Platform Fan-out ───────────────────────────────────────────

  console.log("\n--- Phase 2: Platform Fan-out (CSS, Kotlin, Swift) ---");
  const queue = new PQueue({ concurrency: 3 });

  const platformPromises = {
    css: queue.add(() =>
      runPlatformGeneration("css", designContent, architectVocab)
    ),
    kotlin: queue.add(() =>
      runPlatformGeneration("kotlin", designContent, architectVocab)
    ),
    swift: queue.add(() =>
      runPlatformGeneration("swift", designContent, architectVocab)
    ),
  };

  const platformResults = {};
  let hasFailure = false;

  for (const [platform, promise] of Object.entries(platformPromises)) {
    try {
      platformResults[platform] = await promise;
    } catch (err) {
      console.error(`  ${platform} generation failed: ${err.message}`);
      appendBuildLog({ phase: platform, status: "failure", error: err.message });
      hasFailure = true;
    }
  }

  if (hasFailure) {
    console.error("\nSome platform generations failed. See errors above.");
    fallbackRestore(allPlatformFilePaths());
    process.exit(1);
  }

  // ─── Write Files ──────────────────────────────────────────────────────────

  console.log("\n--- Writing Files ---");
  for (const [platform, result] of Object.entries(platformResults)) {
    console.log(`\n  [${platform.toUpperCase()}]`);
    writePlatformFiles(result.files);

    // Patch globals.css from CSS result
    if (platform === "css" && result.globalsCssPatch) {
      patchGlobalsCss(result.globalsCssPatch);
    }
  }

  // ─── Update Lock ──────────────────────────────────────────────────────────

  updateLock(designContent, platformResults);

  // ─── Success ──────────────────────────────────────────────────────────────

  appendBuildLog({ phase: "all", status: "success", trigger });
  console.log("\n=== Generation Complete ===");
}

async function runPlatformGeneration(platform, designContent, architectVocab) {
  const prompts = {
    css: buildCSSPlatformPrompt,
    kotlin: buildKotlinPlatformPrompt,
    swift: buildSwiftPlatformPrompt,
  };

  const schemas = {
    css: CSS_PLATFORM_SCHEMA,
    kotlin: KOTLIN_PLATFORM_SCHEMA,
    swift: SWIFT_PLATFORM_SCHEMA,
  };

  let retryErrors = [];
  let result;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      result = await runClaude(
        prompts[platform](designContent, architectVocab),
        schemas[platform],
        platform,
        retryErrors
      );

      // Validate
      const errors = validateResponse(result, platform, architectVocab);
      if (errors.length > 0) {
        retryErrors = errors;
        console.log(`  [${platform.toUpperCase()}] Validation failed (attempt ${attempt + 1}):`);
        for (const e of errors) {
          console.log(`    - ${e}`);
        }
        continue;
      }

      console.log(
        `  [${platform.toUpperCase()}] OK — colors: ${result.validation.colorCount}, type: ${result.validation.typographyCount}, shadows: ${result.validation.shadowsCount}, components: ${result.validation.componentsCount}`
      );
      return result;
    } catch (err) {
      retryErrors.push(err.message);
      if (attempt === MAX_RETRIES) {
        throw new Error(`${platform} generation failed: ${err.message}`);
      }
      console.log(`  [${platform.toUpperCase()}] Attempt ${attempt + 1} failed: ${err.message}`);
    }
  }

  throw new Error(`${platform} generation failed after ${MAX_RETRIES} retries`);
}

// ─── Run ──────────────────────────────────────────────────────────────────────

main().catch((err) => {
  console.error(`Fatal error: ${err.message}`);
  appendBuildLog({ phase: "main", status: "failure", error: err.message });
  fallbackRestore(allPlatformFilePaths());
  process.exit(1);
});