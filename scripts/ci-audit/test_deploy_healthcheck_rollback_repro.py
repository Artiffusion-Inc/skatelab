"""Validate the active Dokploy deployment path, not the retired deploy script."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = REPO_ROOT / "infra/dokploy/scripts/sync-traefik-config.sh"
DEPLOY_WORKFLOW = REPO_ROOT / ".github/workflows/deploy.yml"
HEALTH_SCRIPT = REPO_ROOT / "infra/dokploy/scripts/health-check-poll.sh"


def main() -> int:
    sync = SYNC_SCRIPT.read_text()
    workflow = DEPLOY_WORKFLOW.read_text()
    health = HEALTH_SCRIPT.read_text()

    required_sync_markers = (
        'BACKUP_DIR="/etc/dokploy/traefik/rollback/',
        "trap rollback ERR",
        "timeout 10s",
        "--configFile=/etc/traefik/traefik.yml",
        'if [[ -d "$REMOTE_DYNAMIC" ]]; then',
        'root_cmd rm -rf "$REMOTE_DYNAMIC"',
        "curl --fail --silent --show-error",
    )
    missing = [marker for marker in required_sync_markers if marker not in sync]
    if missing:
        print(f"FAIL: Traefik sync lost rollback/validation markers: {missing}")  # noqa: T201
        return 1

    required_workflow_markers = ("sync-traefik-config.sh", "health-check-poll.sh")
    missing = [marker for marker in required_workflow_markers if marker not in workflow]
    if missing:
        print(f"FAIL: deployment workflow lost required gates: {missing}")  # noqa: T201
        return 1
    if workflow.index("- name: Synchronize Traefik routing source") < workflow.index(
        "- name: Trigger Dokploy compose.deploy via SSH"
    ):
        print("FAIL: Traefik health gate runs before the app compose deploy")  # noqa: T201
        return 1

    if '"https://api.skatelab.ru/v1/health"' not in health:
        print("FAIL: public API health probe is missing")  # noqa: T201
        return 1

    print("GREEN: active Dokploy deployment has validated config rollback and public health gates")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
