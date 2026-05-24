"""Merged PreToolUse guard for Bash commands.

Combines block-pip, block-nohup, block-unsafe-git into one script.
Eliminates 2 Python cold starts per Bash tool call (61ms → 14ms).

Exit code 2 = deny (blocks the tool call).
"""

import json
import re
import sys

# ── pip guard ──────────────────────────────────────────────────
PIP_PATTERN = re.compile(r"^pip(-?3)?(?:\.\d+)?$")
PIP_INSTALL_WORD = "install"


def check_pip(cmd: str, parts: list[str]) -> str | None:  # noqa: ARG001
    if not parts:
        return None
    first = parts[0]
    if PIP_PATTERN.match(first) and PIP_INSTALL_WORD in parts:
        return (
            "BLOCKED: pip install not allowed. Use uv instead.\n"
            "Pattern: uv add <packages>\n"
            "Example: uv add requests httpx"
        )
    return None


# ── nohup guard ─────────────────────────────────────────────────
def check_nohup(cmd: str, parts: list[str]) -> str | None:  # noqa: ARG001
    if parts and parts[0] == "nohup":
        return (
            "BLOCKED: nohup not allowed. Use tmux instead.\n"
            "\n"
            "Patterns:\n"
            "  nohup <cmd> &             →  tmux new -s <name> -d '<cmd>'\n"
            "  nohup <cmd> > out.log 2>&1 &  →  tmux new -s <name> -d '<cmd> 2>&1 | tee out.log'\n"
            "\n"
            "Attach later:  tmux attach -t <name>\n"
            "List sessions: tmux ls\n"
            "Kill session:  tmux kill-session -t <name>\n"
            "\n"
            "Quick one-liner: tmux new -s build -d 'docker build -f Containerfile .'"
        )
    return None


# ── unsafe git guard ──────────────────────────────────────────
BLOCKED_CMD_PATTERNS = [
    (r"\b--no-verify\b", "BLOCKED: --no-verify skips hooks. Fix the hook failures instead."),
    (
        r"\b--skip-hooks\b",
        "BLOCKED: --skip-hooks bypasses lefthook. Fix the hook failures instead.",
    ),
    (
        r"\bgit\s+push\s+.*\s+--force\b",
        "BLOCKED: --force push overwrites upstream. Use --force-with-lease instead.",
    ),
    (
        r"\bgit\s+reset\s+--hard\b",
        "BLOCKED: reset --hard discards uncommitted changes. Use reset --soft or --mixed.",
    ),
    (
        r"\bgit\s+checkout\s+-f\b",
        "BLOCKED: checkout -f discards local changes. Stash or commit first.",
    ),
    (
        r"\bgit\s+clean\s+-f\b",
        "BLOCKED: clean -f removes untracked files. Use clean -fd with caution.",
    ),
    (r"\bgit\s+stash\s+drop\b", "BLOCKED: stash drop loses work. Use stash pop instead."),
    (
        r"\bgit\s+branch\s+-D\b",
        "BLOCKED: branch -D force-deletes. Use branch -d for safe deletion.",
    ),
    (
        r"^git\s+restore\b",
        "BLOCKED: git restore discards working tree changes. Use git stash instead.",
    ),
    (
        r"^git\s+checkout\s+--\b",
        "BLOCKED: checkout -- discards uncommitted changes. Use git stash instead.",
    ),
    (
        r"^git\s+worktree\s+remove\s+--force\b",
        "BLOCKED: worktree remove --force skips safety checks. Remove without --force.",
    ),
]

BLOCKED_ENV_PATTERNS = [
    (r"LEFTHOOK=0", "BLOCKED: LEFTHOOK=0 disables all hooks. Fix the hook failures instead."),
    (r"HUSKY=0", "BLOCKED: HUSKY=0 disables all hooks. Fix the hook failures instead."),
]

SHELL_WRAPPER_PATTERNS = [
    (
        r"\b(bash|sh|zsh)\s+-c\s+.*\b(git\s+reset\s+--hard|git\s+checkout\s+-f|git\s+clean\s+-f|git\s+branch\s+-D|git\s+stash\s+drop|git\s+restore|git\s+push\s+.*--force)\b",
        "BLOCKED: shell wrapper detected containing blocked git command.",
    ),
]

COMPILED_CMD = [(re.compile(p), msg) for p, msg in BLOCKED_CMD_PATTERNS]
COMPILED_ENV = [(re.compile(p), msg) for p, msg in BLOCKED_ENV_PATTERNS]
COMPILED_SHELL = [(re.compile(p), msg) for p, msg in SHELL_WRAPPER_PATTERNS]

# git restore without --staged is destructive. git restore --staged is safe (un-stages).
RESTORE_STAGED_PATTERN = re.compile(r"\bgit\s+restore\s+--stage")


def check_unsafe_git(cmd: str, parts: list[str]) -> str | None:  # noqa: ARG001
    for pattern, message in COMPILED_ENV:
        if pattern.search(cmd):
            return message

    for pattern, message in COMPILED_SHELL:
        if pattern.search(cmd):
            return message

    for pattern, message in COMPILED_CMD:
        if pattern.search(cmd):
            # Special case: git restore --staged is safe (unstages, doesn't discard)
            if "git restore" in message and RESTORE_STAGED_PATTERN.search(cmd):
                continue
            return message

    return None


# ── main ───────────────────────────────────────────────────────
def main():
    try:
        input_data = json.loads(sys.stdin.read())
        cmd = input_data.get("tool_input", {}).get("command", "")

        if not cmd:
            sys.exit(0)

        parts = cmd.split()

        # Run all checks; return first block
        for checker in (check_pip, check_nohup, check_unsafe_git):
            result = checker(cmd, parts)
            if result:
                print(f"[hook] {result}", file=sys.stderr)  # noqa: T201
                sys.exit(2)

        sys.exit(0)

    except json.JSONDecodeError:
        sys.exit(0)
    except Exception:  # noqa: BLE001
        sys.exit(0)


if __name__ == "__main__":
    main()
