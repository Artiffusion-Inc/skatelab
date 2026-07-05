#!/usr/bin/env bash
# Migrate Valkey data old -> new container via RDB copy.
# Usage: ./valkey-migrate.sh <old-container> <new-container>
set -euo pipefail

OLD="${1:?usage: valkey-migrate.sh <old> <new}"
NEW="${2:?usage: valkey-migrate.sh <old> <new}"

echo "Migrating Valkey: $OLD -> $NEW"

docker exec "$OLD" valkey-cli BGSAVE >/dev/null
sleep 5

docker cp "$OLD:/data/dump.rdb" /tmp/valkey-migration.rdb

docker stop "$NEW" >/dev/null
docker cp /tmp/valkey-migration.rdb "$NEW:/data/dump.rdb"
docker start "$NEW" >/dev/null
sleep 5

OLD_KEYS=$(docker exec "$OLD" valkey-cli DBSIZE)
NEW_KEYS=$(docker exec "$NEW" valkey-cli DBSIZE)
echo "old=$OLD_KEYS keys  new=$NEW_KEYS keys"
if [[ "$OLD_KEYS" -eq "$NEW_KEYS" ]]; then
  echo "PASS: key count matches"
else
  echo "WARN: mismatch (old may have new writes after BGSAVE snapshot)"
fi
rm -f /tmp/valkey-migration.rdb