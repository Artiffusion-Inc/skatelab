// style-dictionary.config.js
// Design token build config — generates CSS, Android Kotlin, and iOS Swift outputs
// from the single source of truth: tokens/dtcg.json (DTCG format)
//
// Usage: npx style-dictionary build --config style-dictionary.config.js
// Or:    task design:build  (runs token extraction from DESIGN.md first)

import StyleDictionary from 'style-dictionary';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a CSS variable name from a token path array.
 *  Matches globals.css naming: --primary, --ink-mute, --score-good, etc.
 *  For colors: path = ["colors", "primary"] → --primary
 *  For spacing: path = ["spacing", "sm"] → --spacing-sm
 *  For radius: path = ["rounded", "lg"] → --radius-lg
 */
function cssVarName(path) {
  const [group, ...rest] = path;
  const suffix = rest.join('-');
  // Color tokens: drop the "colors" prefix to match --primary, --ink-mute, etc.
  if (group === 'colors') {
    return `--${suffix}`;
  }
  // Spacing → --spacing-sm, --spacing-md, etc.
  if (group === 'spacing') {
    return `--spacing-${suffix}`;
  }
  // Rounded → --radius-xs, --radius-sm, etc.
  if (group === 'rounded') {
    return `--radius-${suffix}`;
  }
  // Typography → --typography-display-xxl-font-size, etc.
  if (group === 'typography') {
    return `--${group}-${suffix}`;
  }
  return `--${path.join('-')}`;
}

/** CamelCase from kebab — "primary-deep" → "primaryDeep" */
function camelCase(str) {
  return str.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
}

/** PascalCase from kebab — "primary-deep" → "PrimaryDeep" */
function pascalCase(str) {
  return str.replace(/(^|-)([a-z])/g, (_all, _sep, c) => c.toUpperCase());
}

/** Resolve a dimension token's value to a CSS string.
 *  DTCG dimension tokens can be: number, string, or {value, unit, type} object */
function resolveDimensionValue(token) {
  const v = token.$value ?? token.value;
  if (typeof v === 'object' && v !== null) {
    // {value: N, unit: 'px', type: 'dimension'}
    if (v.value !== undefined) {
      return typeof v.value === 'number' && v.unit === 'px' ? `${v.value}px` : String(v.value);
    }
    return String(v);
  }
  return String(v);
}

// ---------------------------------------------------------------------------
// Custom format: CSS custom properties with OKLCH values
// ---------------------------------------------------------------------------

StyleDictionary.registerFormat({
  name: 'skatelab/css:variables',
  format: async ({ dictionary, file }) => {
    // Simple file header (formatHelpers.fileHeader not exported from ESM package)
    const header = `/**\n * AUTO-GENERATED — do not edit. Source: DESIGN.md\n * Regenerate: task design:build\n */`;

    const colorLines = [];
    const spacingLines = [];
    const radiusLines = [];

    for (const token of dictionary.allTokens) {
      const type = token.$type ?? token.type;

      if (type === 'color') {
        const ext = token.$extensions?.['com.tokens-studio'];
        const oklch = ext?.oklch || token.$value;
        const hex = token.$value;
        const varName = cssVarName(token.path);
        // Clean up NaN in oklch values (e.g., pure white "oklch(1.000 0.000 NaN)")
        const cleanOklch = oklch.replace(/NaN/g, '0');
        colorLines.push(`  ${varName}: ${cleanOklch};  /* ${hex} */`);
      }

      if (type === 'dimension') {
        const varName = cssVarName(token.path);
        const val = resolveDimensionValue(token);
        if (token.path[0] === 'spacing') {
          spacingLines.push(`  ${varName}: ${val};`);
        } else if (token.path[0] === 'rounded') {
          radiusLines.push(`  ${varName}: ${val};`);
        }
      }
    }

    return [
      header,
      ':root {',
      ...colorLines,
      '',
      ...spacingLines,
      '',
      ...radiusLines,
      '}',
    ].join('\n') + '\n';
  },
});

// ---------------------------------------------------------------------------
// Custom format: Kotlin Compose — object SkateLabColors { val primary = Color(0xFF155F73) }
// ---------------------------------------------------------------------------

StyleDictionary.registerFormat({
  name: 'skatelab/compose:object',
  format: async ({ dictionary, file }) => {
    const pkg = file.options?.package || 'ru.skatelab.capture.presentation.theme';
    const header = `// AUTO-GENERATED — do not edit. Source: DESIGN.md\n// Regenerate: task design:build`;

    const colors = dictionary.allTokens
      .filter(t => (t.$type ?? t.type) === 'color')
      .map(t => {
        const argb = t.$extensions?.['com.tokens-studio']?.argb || `0xFF${(t.$value || '').replace('#', '').toUpperCase()}`;
        const name = camelCase(t.path.slice(1).join('-'));
        return `    val ${name} = Color(${argb})`;
      });

    return [
      header,
      `package ${pkg}`,
      '',
      'import androidx.compose.ui.graphics.Color',
      '',
      'object SkateLabColors {',
      ...colors,
      '}',
    ].join('\n') + '\n';
  },
});

// ---------------------------------------------------------------------------
// Custom format: iOS Swift — extension Color { static let skatePrimary = Color(...) }
// ---------------------------------------------------------------------------

StyleDictionary.registerFormat({
  name: 'skatelab/ios/swift/extension',
  format: async ({ dictionary, file }) => {
    const header = `// AUTO-GENERATED — do not edit. Source: DESIGN.md\n// Regenerate: task design:build`;

    const colors = dictionary.allTokens
      .filter(t => (t.$type ?? t.type) === 'color')
      .map(t => {
        const ext = t.$extensions?.['com.tokens-studio'];
        const srgb = ext?.srgb;
        const name = 'skate' + pascalCase(t.path.slice(1).join('-'));
        if (srgb) {
          return `    static let ${name} = Color(red: ${srgb.r}, green: ${srgb.g}, blue: ${srgb.b})`;
        }
        // Fallback: parse hex
        const hex = (t.$value || '').replace('#', '');
        const r = parseInt(hex.substring(0, 2), 16) / 255;
        const g = parseInt(hex.substring(2, 4), 16) / 255;
        const b = parseInt(hex.substring(4, 6), 16) / 255;
        return `    static let ${name} = Color(red: ${r.toFixed(3)}, green: ${g.toFixed(3)}, blue: ${b.toFixed(3)})`;
      });

    return [
      header,
      'import SwiftUI',
      '',
      '@available(iOS 15, *)',
      'extension Color {',
      ...colors,
      '}',
    ].join('\n') + '\n';
  },
});

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export default {
  source: ['tokens/dtcg.json'],
  log: {
    warnings: 'warn',
    verbosity: 'default',
    errors: {
      brokenReferences: 'warn',
    },
  },
  platforms: {
    css: {
      buildPath: 'frontend/src/app/',
      files: [{
        destination: 'tokens.css',
        format: 'skatelab/css:variables',
      }],
    },
    android: {
      buildPath: 'mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/',
      files: [{
        destination: 'Colors.kt',
        format: 'skatelab/compose:object',
        options: { package: 'ru.skatelab.capture.presentation.theme' },
      }],
    },
    ios: {
      buildPath: 'mobile/iosApp/SkateLab/Theme/',
      files: [{
        destination: 'SkateLabColors.swift',
        format: 'skatelab/ios/swift/extension',
      }],
    },
  },
};