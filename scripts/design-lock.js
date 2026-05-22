#!/usr/bin/env node
/**
 * design-lock.js — Checksum lockfile manager for design tokens
 *
 * Subcommands:
 *   node scripts/design-lock.js update  — Compute SHA-256 of each generated file
 *                                          + DESIGN.md hash, write tokens/lock.json
 *   node scripts/design-lock.js check   — Compute hashes, compare with lock.json.
 *                                          Exit 0 if match, exit 1 if drift.
 *                                          Missing files log a warning but don't fail.
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// ─── Paths ────────────────────────────────────────────────────────────────

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DESIGN_MD = resolve(ROOT, "DESIGN.md");
const LOCK_FILE = resolve(ROOT, "tokens", "lock.json");

// ─── Generated files (must match design-build.js PLATFORM_FILES) ──────────

const GENERATED_FILES = [
  "frontend/src/app/tokens.css",
  "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Colors.kt",
  "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Type.kt",
  "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Theme.kt",
  "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Shadows.kt",
  "mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/theme/Modifiers.kt",
  "mobile/iosApp/SkateLab/Theme/SkateLabColors.swift",
  "mobile/iosApp/SkateLab/Theme/SkateLabTypography.swift",
  "mobile/iosApp/SkateLab/Theme/SkateLabTheme.swift",
  "mobile/iosApp/SkateLab/Theme/SkateLabShadows.swift",
  "mobile/iosApp/SkateLab/Theme/SkateLabModifiers.swift",
];

const PLATFORMS = {
  css: GENERATED_FILES.filter((f) => f.endsWith(".css")),
  kotlin: GENERATED_FILES.filter((f) => f.endsWith(".kt")),
  swift: GENERATED_FILES.filter((f) => f.endsWith(".swift")),
};

// ─── Hash Utilities ───────────────────────────────────────────────────────

function sha256(content) {
  return "sha256:" + createHash("sha256").update(content).digest("hex");
}

function fileHash(absPath) {
  if (!existsSync(absPath)) return null;
  return sha256(readFileSync(absPath, "utf8"));
}

function sectionHash(designContent, sectionName) {
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

function computeSectionHashes(designContent) {
  return {
    colors: sectionHash(designContent, "colors"),
    typography: sectionHash(designContent, "typography"),
    shadows: sectionHash(designContent, "shadows"),
    components: sectionHash(designContent, "components"),
  };
}

// ─── Lock I/O ─────────────────────────────────────────────────────────────

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

// ─── update ───────────────────────────────────────────────────────────────

function update() {
  const designContent = existsSync(DESIGN_MD)
    ? readFileSync(DESIGN_MD, "utf8")
    : "";

  const files = {};
  for (const rel of GENERATED_FILES) {
    const h = fileHash(resolve(ROOT, rel));
    if (h !== null) files[rel] = h;
  }

  const platformHashes = {};
  for (const [platform, paths] of Object.entries(PLATFORMS)) {
    const hashes = {};
    for (const rel of paths) {
      if (files[rel]) hashes[rel] = files[rel];
    }
    platformHashes[platform] = hashes;
  }

  const lock = {
    version: 2,
    timestamp: new Date().toISOString(),
    designMdHash: designContent ? sha256(designContent) : "",
    sectionHashes: designContent ? computeSectionHashes(designContent) : {},
    files,
    platformHashes,
  };

  writeLock(lock);
  console.log("Updated: tokens/lock.json");

  const fileCount = Object.keys(files).length;
  const totalCount = GENERATED_FILES.length;
  console.log(`  Files hashed: ${fileCount}/${totalCount}`);
  if (fileCount < totalCount) {
    console.log(
      `  Missing: ${totalCount - fileCount} files not yet generated`
    );
  }
}

// ─── check ────────────────────────────────────────────────────────────────

function check() {
  const lock = readLock();
  if (!lock) {
    console.error("Error: tokens/lock.json not found. Run `update` first.");
    process.exit(1);
  }

  if (lock.version !== 2) {
    console.error(`Error: lock.json version ${lock.version}, expected 2`);
    process.exit(1);
  }

  const designContent = existsSync(DESIGN_MD)
    ? readFileSync(DESIGN_MD, "utf8")
    : "";
  const currentDesignHash = designContent ? sha256(designContent) : "";
  const drifts = [];

  // Check DESIGN.md hash
  if (lock.designMdHash && currentDesignHash !== lock.designMdHash) {
    drifts.push({ type: "source", file: "DESIGN.md" });
    console.log(`Drift: DESIGN.md hash mismatch`);
    console.log(`  locked:   ${lock.designMdHash}`);
    console.log(`  current:  ${currentDesignHash}`);
  }

  // Check section hashes
  if (lock.sectionHashes && designContent) {
    const currentSections = computeSectionHashes(designContent);
    for (const [section, hash] of Object.entries(lock.sectionHashes)) {
      if (hash && currentSections[section] !== hash) {
        drifts.push({ type: "section", section });
        console.log(`Drift: section "${section}" hash mismatch`);
        console.log(`  locked:   ${hash}`);
        console.log(`  current:  ${currentSections[section]}`);
      }
    }
  }

  // Check generated file hashes
  for (const [rel, lockedHash] of Object.entries(lock.files)) {
    if (!lockedHash) continue; // skip empty entries
    const absPath = resolve(ROOT, rel);
    if (!existsSync(absPath)) {
      console.warn(`Warning: missing file (skipped): ${rel}`);
      continue;
    }
    const currentHash = fileHash(absPath);
    if (currentHash !== lockedHash) {
      drifts.push({ type: "file", file: rel });
      console.log(`Drift: ${rel}`);
      console.log(`  locked:   ${lockedHash}`);
      console.log(`  current:  ${currentHash}`);
    }
  }

  // Check platform hashes
  for (const [platform, hashes] of Object.entries(lock.platformHashes || {})) {
    for (const [rel, lockedHash] of Object.entries(hashes)) {
      if (!lockedHash) continue;
      const absPath = resolve(ROOT, rel);
      if (!existsSync(absPath)) {
        console.warn(`Warning: missing file (skipped): ${rel}`);
        continue;
      }
      const currentHash = fileHash(absPath);
      if (currentHash !== lockedHash) {
        // Already reported in files check above, don't double-count
        if (!drifts.some((d) => d.type === "file" && d.file === rel)) {
          drifts.push({ type: "platform-file", platform, file: rel });
          console.log(`Drift [${platform}]: ${rel}`);
          console.log(`  locked:   ${lockedHash}`);
          console.log(`  current:  ${currentHash}`);
        }
      }
    }
  }

  if (drifts.length === 0) {
    console.log("OK: all hashes match");
    process.exit(0);
  } else {
    console.log(`\n${drifts.length} drift(s) detected. Run \`node scripts/design-lock.js update\` or \`node scripts/design-build.js --force\`.`);
    process.exit(1);
  }
}

// ─── CLI ──────────────────────────────────────────────────────────────────

const command = process.argv[2];

if (!command || command === "--help" || command === "-h") {
  console.log(`Usage: design-lock.js <update|check>

  update  Compute SHA-256 of generated files + DESIGN.md, write tokens/lock.json
  check   Compare current hashes with lock.json, exit 1 on drift
`);
  process.exit(0);
}

if (command === "update") {
  update();
} else if (command === "check") {
  check();
} else {
  console.error(`Unknown command: ${command}`);
  console.error('Use "update" or "check"');
  process.exit(1);
}
