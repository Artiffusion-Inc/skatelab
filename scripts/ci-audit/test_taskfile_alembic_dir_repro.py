"""Static repro for Taskfile db-* alembic working-dir mismatch (I3). RED-by-design.

`Taskfile.yml` db-* tasks (db-migrate, db-rollback, db-reset, db-migration) run
`{{.UV_RUN}} alembic <cmd>` with NO `dir:` set, so they default to the repo root.
But `alembic.ini` lives at `backend/alembic.ini`. Running alembic from the repo
root deterministically fails to locate `alembic.ini` -> FileNotFoundError on every
invocation.

This script parses `Taskfile.yml` read-only and asserts the bug is structurally
present: the four db-* tasks lack `dir: backend` (dir unset or `.`) AND
`backend/alembic.ini` exists. Exit 1 = RED = bug present. No DB mutation.

Companion to GitHub issue (fix(infra): Taskfile db-* tasks run alembic from repo
root). Proposed fix (NOT applied here): add `dir: backend` to all four db-* tasks.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKFILE = REPO_ROOT / "Taskfile.yml"
ALEMBIC_INI = REPO_ROOT / "backend" / "alembic.ini"
DB_TASKS = ("db-migrate", "db-rollback", "db-reset", "db-migration")


def _dir_is_backend_or_unset(task: dict) -> bool:
    """True if the task has NO effective `dir: backend` (unset or explicitly `.`)."""
    dir_val = task.get("dir")
    if dir_val is None:
        return True
    # Normalize: strip, drop trailing slash, treat "." as repo root.
    normalized = str(dir_val).strip().rstrip("/")
    return normalized != "backend"


def main() -> int:
    # Precondition: alembic.ini must exist at backend/alembic.ini.
    if not ALEMBIC_INI.is_file():
        print(  # noqa: T201
            "INCONCLUSIVE: backend/alembic.ini not found at "
            f"{ALEMBIC_INI} — cannot assert the mismatch.",
        )
        return 2

    if not TASKFILE.is_file():
        print(f"INCONCLUSIVE: Taskfile.yml not found at {TASKFILE}.")  # noqa: T201
        return 2

    data = yaml.safe_load(TASKFILE.read_text(encoding="utf-8")) or {}
    tasks = data.get("tasks", {}) or {}

    missing_dir: list[str] = []
    for name in DB_TASKS:
        task = tasks.get(name)
        if task is None:
            print(f"INCONCLUSIVE: task '{name}' missing from Taskfile.yml.")  # noqa: T201
            return 2
        if _dir_is_backend_or_unset(task):
            missing_dir.append(name)

    if not missing_dir:
        # Bug fixed: every db-* task sets dir: backend. GREEN.
        print(  # noqa: T201
            "GREEN: all db-* tasks set dir: backend and alembic.ini is at "
            "backend/alembic.ini — no working-dir mismatch.",
        )
        return 0

    print(  # noqa: T201
        "RED: Taskfile db-* tasks run alembic from repo root "
        f"(no dir: backend) but alembic.ini at {ALEMBIC_INI.relative_to(REPO_ROOT)} "
        f"-> deterministic FileNotFoundError. Affected tasks: {', '.join(missing_dir)}",
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
