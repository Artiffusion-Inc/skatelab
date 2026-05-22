#!/usr/bin/env node

/**
 * WCAG contrast ratio validator for OKLCH design tokens.
 *
 * Reads `frontend/src/app/tokens.css`, parses OKLCH values, computes
 * contrast ratios for named pairs, and reports violations.
 *
 * Exit 0: all checks pass (known violations are WARN, not FAIL)
 * Exit 1: any unknown violations found
 */

import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TOKENS_PATH = resolve(__dirname, "../frontend/src/app/tokens.css");

const PAIRS = [
  { fg: "--ink", bg: "--canvas", label: "ink on canvas" },
  { fg: "--ink-mute", bg: "--canvas", label: "ink-mute on canvas" },
  { fg: "--primary-foreground", bg: "--primary", label: "on-primary on primary" },
  { fg: "--on-dark-mute", bg: "--primary-deep", label: "on-dark-mute on primary-deep" },
  { fg: "--on-dark-dim", bg: "--primary-deep", label: "on-dark-dim on primary-deep" },
  { fg: "--on-dark-faint", bg: "--surface-teal-deep", label: "on-dark-faint on teal-deep (known violation)" },
  { fg: "--ink", bg: "--canvas-soft", label: "ink on canvas-soft" },
  { fg: "--destructive", bg: "--canvas", label: "destructive on canvas" },
];

const KNOWN_VIOLATIONS = new Set([
  "on-dark-faint on teal-deep (known violation)",
]);

const WCAG_AA_NORMAL = 4.5;

// --- OKLCH → luminance ---

function oklchToLuminance(l, c, hDeg) {
  // CSS OKLCH hue is in degrees — convert to radians for trig
  const h = (hDeg * Math.PI) / 180;

  // OKLCH → OKLab
  const a = c * Math.cos(h);
  const b = c * Math.sin(h);

  // OKLab → LMS (cube root domain)
  const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = l + 0.0894841775 * a - 0.1918035471 * b;

  // Cube root → linear LMS
  const L = l_ * l_ * l_;
  const M = m_ * m_ * m_;
  const S = s_ * s_ * s_;

  // LMS → XYZ (M1 matrix, Björn Ottosson)
  const X = 0.4122214708 * L + 0.5363325363 * M + 0.0514459929 * S;
  const Y = 0.2119034921 * L + 0.6807047526 * M + 0.1074055771 * S;
  const Z = 0.0883024610 * L + 0.2817183730 * M + 0.6299787000 * S;

  // XYZ → linear sRGB (IEC 61966-2-1, D65)
  const r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z;
  const g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z;
  const bl = 0.0557 * X - 0.2040 * Y + 1.0570 * Z;

  // Clamp negatives (out-of-gamut)
  const rClamp = Math.max(0, r);
  const gClamp = Math.max(0, g);
  const bClamp = Math.max(0, bl);

  // Relative luminance (WCAG 2.x)
  return 0.2126 * rClamp + 0.7152 * gClamp + 0.0722 * bClamp;
}

function contrastRatio(l1, l2) {
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// --- Token parsing ---

function parseTokens(css) {
  const re = /--([\w-]+):\s*oklch\(([\d.]+)\s+([\d.]+)\s+([\d.]+)\)/g;
  const tokens = {};
  let match;
  while ((match = re.exec(css)) !== null) {
    const [, name, l, c, h] = match;
    tokens[`--${name}`] = {
      l: parseFloat(l),
      c: parseFloat(c),
      h: parseFloat(h),
    };
  }
  return tokens;
}

// --- Main ---

function main() {
  const css = readFileSync(TOKENS_PATH, "utf-8");
  const tokens = parseTokens(css);

  let hasUnknownViolation = false;

  for (const pair of PAIRS) {
    // Look up with fallback: --ink → --color-ink if --ink not found
    const lookup = (name) => tokens[name] || tokens[`--color-${name.replace(/^--/, "")}`];
    const fg = lookup(pair.fg);
    const bg = lookup(pair.bg);

    if (!fg) {
      console.error(`FAIL: ${pair.label} — token ${pair.fg} not found`);
      hasUnknownViolation = true;
      continue;
    }
    if (!bg) {
      console.error(`FAIL: ${pair.label} — token ${pair.bg} not found`);
      hasUnknownViolation = true;
      continue;
    }

    const lumFg = oklchToLuminance(fg.l, fg.c, fg.h);
    const lumBg = oklchToLuminance(bg.l, bg.c, bg.h);
    const ratio = contrastRatio(lumFg, lumBg);
    const ratioStr = ratio.toFixed(2);

    if (ratio >= WCAG_AA_NORMAL) {
      console.log(`PASS: ${pair.label} — ratio ${ratioStr}:1`);
    } else if (KNOWN_VIOLATIONS.has(pair.label)) {
      console.log(`WARN: ${pair.label} — ratio ${ratioStr}:1`);
    } else {
      console.log(
        `FAIL: ${pair.label} — ratio ${ratioStr}:1 (need ${WCAG_AA_NORMAL}:1)`,
      );
      hasUnknownViolation = true;
    }
  }

  process.exit(hasUnknownViolation ? 1 : 0);
}

main();
