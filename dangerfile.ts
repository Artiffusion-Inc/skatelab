// Danger CI rules — PR-level enforcement.
// Complements local lefthook hooks (defense-in-depth).
// Runs via danger-js (npm).
// Types/scopes/branches: .commit-conventions (single source of truth)

import { readFileSync } from "fs";
import { danger, fail, warn, message } from "danger";

const conventions = readFileSync(".commit-conventions", "utf-8");
const typesLine = conventions.match(/^types:(.+)$/m)?.[1] ?? "feat|fix|refactor|chore|docs|test|ci";
const scopesLine = conventions.match(/^scopes:(.+)$/m)?.[1] ?? "repo|backend|frontend|ml|ci|dev";
const branchesLine = conventions.match(/^branches:(.+)$/m)?.[1] ?? "feature/|fix/|hotfix/|refactor/|chore/|ci/|docs/|test/";

// ── Branch naming convention ──────────────────────────────────
const branch = danger.github.pr.head.ref;
const validPrefixes = branchesLine.split("|").map((p) => p.trim());
if (!validPrefixes.some((p) => branch.startsWith(p))) {
  fail(`Branch '${branch}' doesn't follow naming convention. Use: ${validPrefixes.join(", ")}`);
}

// ── Commit message format ─────────────────────────────────────
const pattern = new RegExp(`^(${typesLine})\\(([a-z0-9_-]+)\\): .{3,}$`);
for (const commit of danger.git.commits) {
  if (!pattern.test(commit.message.split("\n")[0])) {
    fail(
      `Bad commit message: \`${commit.message.split("\n")[0]}\`\n` +
        `  Expected: \`type(scope): summary\`\n` +
        `  Types: ${typesLine.replace(/\|/g, ", ")}\n` +
        `  Scopes: ${scopesLine.replace(/\|/g, ", ")}`
    );
    break; // One failure enough
  }
}

// ── PR size warning ───────────────────────────────────────────
const additions = danger.github.pr.additions ?? 0;
const deletions = danger.github.pr.deletions ?? 0;
const total = additions + deletions;
if (total > 1000) {
  warn(`Large PR: ${total} lines changed. Consider splitting.`);
} else if (total > 500) {
  message(`PR size: ${total} lines changed.`);
}

// ── Test coverage requirement ─────────────────────────────────
const srcFiles = danger.git.modified_files.filter(
  (f) => f.endsWith(".py") && !f.includes("test")
);
const testFiles = danger.git.modified_files.filter(
  (f) => f.endsWith(".py") && f.includes("test")
);
if (srcFiles.length > 0 && testFiles.length === 0) {
  warn("Source files changed without tests. Consider adding test coverage.");
}