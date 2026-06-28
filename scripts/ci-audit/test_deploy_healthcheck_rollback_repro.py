"""RED-by-design static assertion: deploy.sh health-check block lacks rollback.

T027 / I4. `infra/deploy.sh` has an asymmetric rollback policy:
- Migration block (~:47-51): on `alembic upgrade head` failure it runs
  `docker rollout --timeout 60 --rollback backend` then exits 1.
- Health-check block (~:54): `timeout 120 bash -c "while true; do ... done"`
  with NO `--rollback` / no exit-on-failure handling.

If the new backend never passes `/v1/health` within 120s (deterministic
app-startup failure: bad config, import error, port conflict), `timeout`
returns 124, `set -e` exits the script, and the NEW BROKEN BACKEND STAYS
DEPLOYED — migration already succeeded so DB is at the new schema but the
running backend is broken. Asymmetric with the migration block.

This script parses `infra/deploy.sh` READ-ONLY (line-based, no shell exec)
and asserts the asymmetry: migration block HAS `--rollback`, health-check
block does NOT. Both hold -> bug present -> exit 1 (RED). No live deploy.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = REPO_ROOT / "infra" / "deploy.sh"

RED_MSG = (
    "RED: deploy.sh health-check block lacks rollback (asymmetric with "
    "migration block which rolls back via docker rollout --rollback backend) "
    "-> broken backend stays deployed on health-check failure"
)


def main() -> int:
    lines = DEPLOY_SH.read_text().splitlines()

    # Locate the migration block: the `if ! ... alembic` line through its `fi`.
    mig_start = next(
        (i for i, ln in enumerate(lines) if "alembic upgrade head" in ln),
        None,
    )
    if mig_start is None:
        print("FATAL: migration block (alembic upgrade head) not found")  # noqa: T201
        return 2
    mig_end = next(
        (i for i in range(mig_start, len(lines)) if lines[i].strip() == "fi"),
        None,
    )
    if mig_end is None:
        print("FATAL: migration block `fi` not found")  # noqa: T201
        return 2
    migration_block = "\n".join(lines[mig_start : mig_end + 1])
    if "--rollback" not in migration_block:
        print("FATAL: migration block has no --rollback (precondition)")  # noqa: T201
        return 2

    # Locate the health-check block: the `timeout 120 bash -c "while...` line
    # through the next blank line / `# Cleanup` comment.
    hc_start = next(
        (i for i, ln in enumerate(lines) if "timeout 120" in ln and "while" in ln),
        None,
    )
    if hc_start is None:
        print("FATAL: health-check block (timeout 120 ... while) not found")  # noqa: T201
        return 2
    hc_end = len(lines)
    for j in range(hc_start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped == "" or stripped.startswith("# Cleanup"):
            hc_end = j
            break
    health_block = "\n".join(lines[hc_start:hc_end])

    # Bug present iff the health-check block lacks any rollback handling.
    has_rollback = any(tok in health_block for tok in ("--rollback", "rollback"))
    if not has_rollback:
        print(RED_MSG)  # noqa: T201
        return 1

    # If someone fixes it, GREEN (exit 0) so the repro flips on a real fix.
    print("GREEN: deploy.sh health-check block has rollback handling")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
