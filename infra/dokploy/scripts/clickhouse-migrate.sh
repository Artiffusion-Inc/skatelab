#!/usr/bin/env bash
# Migrate ClickHouse data old -> new via native BACKUP/RESTORE.
# Skip entirely if ClickHouse not deployed (spec finding #29 — not in current stack).
# Usage: ./clickhouse-migrate.sh <old-container> <new-container>
set -euo pipefail

OLD="${1:-infra-clickhouse-1}"
NEW="${2:?usage: clickhouse-migrate.sh <old> <new>}"

if ! docker ps --filter name="$OLD" --format '{{.Names}}' | grep -q "^${OLD}$"; then
  echo "ClickHouse not deployed ($OLD missing) — skipping. Confirms spec finding #29."
  exit 0
fi

STAMP=$(date +%Y%m%d)
echo "Migrating ClickHouse: $OLD -> $NEW"

docker exec "$OLD" clickhouse-client --query \
  "BACKUP DATABASE default TO Disk('backups', 'migration-${STAMP}.zip')"

docker cp "$OLD:/var/lib/clickhouse/backups/migration-${STAMP}.zip" /tmp/
docker cp "/tmp/migration-${STAMP}.zip" "$NEW:/var/lib/clickhouse/backups/"

docker exec "$NEW" clickhouse-client --query \
  "RESTORE DATABASE default FROM Disk('backups', 'migration-${STAMP}.zip')"

echo "ClickHouse migration complete"
rm -f "/tmp/migration-${STAMP}.zip"