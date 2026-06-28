"""Shared helper for ci-audit RED-by-design repro scripts.

Loads GitHub Actions workflow YAML (read-only) and provides small helpers
for extracting job needs / triggers and emitting deterministic assertion
messages. These scripts ASSERT THE BUG IS PRESENT and exit non-zero (RED)
when the bug is structurally detected in the checked-in workflow YAML.

No live GitHub Actions runs are required — this is a static structural
oracle over the workflow files committed in the repo.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def load_workflow(name: str) -> dict[str, Any]:
    """Load a workflow YAML file by filename under .github/workflows/.

    PyYAML's safe_load parses the YAML 1.1 bool keywords ``on``/``off``/
    ``yes``/``no`` as Python booleans, so a workflow's top-level ``on:``
    trigger key becomes ``True`` instead of the string ``"on"``. Normalize
    that back so callers can ``workflow.get("on")`` and actually see the
    trigger block. Without this, every trigger assertion is silently a
    no-op (``get("on")`` returns ``None`` for every workflow).
    """
    path = WORKFLOWS_DIR / name
    if not path.exists():
        print(f"RED: workflow file not found: {path}", file=sys.stderr)  # noqa: T201
        sys.exit(2)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if isinstance(data, dict) and True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def red(message: str) -> tuple[int, str]:
    """Return a (exit_code, message) RED result."""
    return (1, message)


def green(message: str) -> tuple[int, str]:
    """Return a (exit_code, message) GREEN result."""
    return (0, message)


def emit(result: tuple[int, str]) -> int:
    """Print the message and return the exit code."""
    code, msg = result
    print(msg)  # noqa: T201
    return code
