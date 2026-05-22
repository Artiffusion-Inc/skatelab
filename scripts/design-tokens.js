#!/usr/bin/env node
// scripts/design-tokens.js — DESIGN.md YAML → DTCG JSON

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { parse as parseYaml } from 'yaml';
import { dirname } from 'path';
import Color from 'colorjs.io';

// ── Extract YAML frontmatter between --- markers ──────────────────────
function extractFrontmatter(content) {
  const match = content.match(/^---\n([\s\S]*?)\n---/);
  if (!match) throw new Error('No YAML frontmatter found');
  return parseYaml(match[1]);
}

// ── Color conversion helpers ──────────────────────────────────────────
function hexToOklch(hex) {
  const c = new Color(hex);
  const oklch = c.to('oklch');
  const L = oklch.coords[0].toFixed(3);
  const C = oklch.coords[1].toFixed(3);
  const H = isNaN(oklch.coords[2]) ? 0 : Math.round(oklch.coords[2]);
  return `oklch(${L} ${C} ${H})`;
}

function hexToSrgb(hex) {
  const c = new Color(hex);
  const srgb = c.to('srgb');
  return {
    r: parseFloat(srgb.coords[0].toFixed(3)),
    g: parseFloat(srgb.coords[1].toFixed(3)),
    b: parseFloat(srgb.coords[2].toFixed(3)),
  };
}

function hexToArgb(hex) {
  const raw = hex.replace('#', '');
  const r = parseInt(raw.substring(0, 2), 16);
  const g = parseInt(raw.substring(2, 4), 16);
  const b = parseInt(raw.substring(4, 6), 16);
  return `0xFF${r.toString(16).toUpperCase().padStart(2, '0')}${g.toString(16).toUpperCase().padStart(2, '0')}${b.toString(16).toUpperCase().padStart(2, '0')}`;
}

// ── Build a DTCG color token ──────────────────────────────────────────
function colorToken(hex, description = '') {
  return {
    $type: 'color',
    $value: hex,
    $description: description,
    $extensions: {
      'com.tokens-studio': {
        oklch: hexToOklch(hex),
        srgb: hexToSrgb(hex),
        argb: hexToArgb(hex),
      },
    },
  };
}

// ── Parse dimension string ────────────────────────────────────────────
function parseDimension(str) {
  if (typeof str === 'number') return { value: str, type: 'number' };
  const s = String(str);

  // clamp() — keep as string
  if (s.startsWith('clamp(')) {
    return { value: s, type: 'dimension', original: s };
  }

  // "Npx" or "Nrem"
  const pxMatch = s.match(/^(-?\d+(?:\.\d+)?)px$/);
  if (pxMatch) {
    return { value: parseFloat(pxMatch[1]), unit: 'px', type: 'dimension' };
  }

  const remMatch = s.match(/^(-?\d+(?:\.\d+)?)rem$/);
  if (remMatch) {
    return { value: parseFloat(remMatch[1]), unit: 'rem', type: 'dimension' };
  }

  // Bare number
  const numMatch = s.match(/^(-?\d+(?:\.\d+)?)$/);
  if (numMatch) {
    return { value: parseFloat(numMatch[1]), type: 'number' };
  }

  // Fallback: keep as string
  return { value: s, type: 'dimension', original: s };
}

// ── Parse letterSpacing ───────────────────────────────────────────────
function parseLetterSpacing(val) {
  if (typeof val === 'number') return val === 0 ? 0 : val;
  const s = String(val);

  // "0" → number 0
  if (s === '0') return 0;

  // "-1.32px" → {value, unit, type}
  const pxMatch = s.match(/^(-?\d+(?:\.\d+)?)px$/);
  if (pxMatch) {
    return { value: parseFloat(pxMatch[1]), unit: 'px', type: 'dimension' };
  }

  // "-0.03em"
  const emMatch = s.match(/^(-?\d+(?:\.\d+)?)em$/);
  if (emMatch) {
    return { value: emMatch[1], unit: 'em', type: 'dimension' };
  }

  return s;
}

// ── Parse lineHeight ──────────────────────────────────────────────────
function parseLineHeight(val) {
  if (typeof val === 'number') return val;
  const n = parseFloat(val);
  if (!isNaN(n)) return n;
  return val;
}

// ── Build a DTCG typography token ─────────────────────────────────────
function typoToken(name, config) {
  const fontSizeDim = parseDimension(config.fontSize);
  const lineHeightVal = parseLineHeight(config.lineHeight);
  const letterSpacingVal = parseLetterSpacing(config.letterSpacing);

  const value = {
    fontFamily: { value: config.fontFamily, type: 'string' },
    fontSize: fontSizeDim,
    fontWeight: { value: config.fontWeight, type: 'number' },
    lineHeight: { value: lineHeightVal, type: typeof lineHeightVal === 'number' ? 'number' : 'dimension' },
    letterSpacing: { value: letterSpacingVal, type: typeof letterSpacingVal === 'number' ? 'number' : 'dimension' },
  };

  const token = {
    $type: 'typography',
    $value: value,
    $description: `Typography token: ${name}`,
  };

  // Preserve fontVariantNumeric if present
  if (config.fontVariantNumeric) {
    token.$value.fontVariantNumeric = { value: config.fontVariantNumeric, type: 'string' };
  }

  return token;
}

// ── Build dimension tokens (rounded, spacing) ────────────────────────
function dimensionToken(val) {
  const dim = parseDimension(val);
  if (dim.type === 'number' || dim.type === 'dimension') {
    return dim;
  }
  return dim;
}

// ── Build component token ─────────────────────────────────────────────
function componentToken(config) {
  const value = {};
  for (const [key, val] of Object.entries(config)) {
    if (typeof val === 'string' && val.startsWith('{') && val.endsWith('}')) {
      // Keep references as strings for now
      value[key] = val;
    } else if (key === 'padding') {
      value[key] = val;
    } else if (key === 'backgroundColor' || key === 'textColor') {
      value[key] = val;
    } else {
      value[key] = val;
    }
  }
  return value;
}

// ── Main ───────────────────────────────────────────────────────────────
function main() {
  const [,, inputPath, outputPath] = process.argv;

  if (!inputPath || !outputPath) {
    console.error('Usage: node design-tokens.js <DESIGN.md> <output.json>');
    process.exit(1);
  }

  // Read and parse
  const content = readFileSync(inputPath, 'utf-8');
  const data = extractFrontmatter(content);

  // Build DTCG output
  const dtcg = {
    $schema: 'https://design-tokens.github.io/community-group/format/',
    $description: data.description || 'SkateLab Design Tokens',
  };

  // Colors
  if (data.colors) {
    dtcg.colors = {};
    for (const [name, hex] of Object.entries(data.colors)) {
      dtcg.colors[name] = colorToken(hex);
    }
  }

  // Typography
  if (data.typography) {
    dtcg.typography = {};
    for (const [name, config] of Object.entries(data.typography)) {
      dtcg.typography[name] = typoToken(name, config);
    }
  }

  // Rounded
  if (data.rounded) {
    dtcg.rounded = {};
    for (const [name, val] of Object.entries(data.rounded)) {
      dtcg.rounded[name] = {
        $type: 'dimension',
        $value: parseDimension(val),
        $description: `Border radius: ${name}`,
      };
    }
  }

  // Spacing
  if (data.spacing) {
    dtcg.spacing = {};
    for (const [name, val] of Object.entries(data.spacing)) {
      dtcg.spacing[name] = {
        $type: 'dimension',
        $value: parseDimension(val),
        $description: `Spacing: ${name}`,
      };
    }
  }

  // Components
  if (data.components) {
    dtcg.components = {};
    for (const [name, config] of Object.entries(data.components)) {
      dtcg.components[name] = {
        $type: 'composite',
        $value: componentToken(config),
        $description: `Component: ${name}`,
      };
    }
  }

  // Write output
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, JSON.stringify(dtcg, null, 2) + '\n');
  console.log(`Written ${outputPath}`);

  // Verify primary OKLCH
  if (dtcg.colors?.primary?.$extensions?.['com.tokens-studio']?.oklch) {
    console.log(`  colors.primary OKLCH: ${dtcg.colors.primary.$extensions['com.tokens-studio'].oklch}`);
  }
}

main();