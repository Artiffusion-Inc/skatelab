"""Danger CI rules — PR-level enforcement.

Runs in CI only. Complements local lefthook hooks (defense-in-depth).

NOTE: danger-python==0.1.0 pins click<8.0, conflicting with arq (click>=8.0).
Install in an isolated venv for CI:

    python -m venv /tmp/danger-venv && /tmp/danger-venv/bin/pip install danger-python
    /tmp/danger-venv/bin/danger-ci

Run with DANGER_GITHUB_API_TOKEN set.
"""

from danger import Danger

danger = Danger()

# ── Branch naming convention ──────────────────────────────────
if danger.github.pr.branch_name:
    branch = danger.github.pr.branch_name
    valid_prefixes = ("feature/", "fix/", "hotfix/", "refactor/", "chore/", "ci/", "docs/", "test/")
    if not any(branch.startswith(p) for p in valid_prefixes):
        danger.fail(
            f"Branch '{branch}' doesn't follow naming convention. Use: {', '.join(valid_prefixes)}"
        )

# ── Commit message format ─────────────────────────────────────
if danger.git.commits:
    import re

    pattern = r"^(feat|fix|refactor|chore|docs|test|ci)\([a-z0-9_-]+\): .{3,}$"
    for commit in danger.git.commits:
        if not re.match(pattern, commit.message.split("\n")[0]):
            danger.fail(
                f"Bad commit message: `{commit.message.split(chr(10))[0]}`\n"
                f"  Expected: `type(scope): summary`"
            )
            break  # One failure enough

# ── PR size warning ───────────────────────────────────────────
if danger.github.pr.additions and danger.github.pr.deletions:
    total = danger.github.pr.additions + danger.github.pr.deletions
    if total > 1000:
        danger.warn(f"Large PR: {total} lines changed. Consider splitting.")
    elif total > 500:
        danger.message(f"PR size: {total} lines changed.")

# ── Test coverage requirement ─────────────────────────────────
src_files = [f for f in danger.git.modified_files if f.endswith(".py") and "test" not in f]
test_files = [f for f in danger.git.modified_files if f.endswith(".py") and "test" in f]
if src_files and not test_files:
    danger.warn("Source files changed without tests. Consider adding test coverage.")
