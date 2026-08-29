#!/usr/bin/env bash
# Set up pglogical replication old Postgres -> new Dokploy Postgres.
# BLOCKER #5 fix: zero-data-loss cutover. Old DB stays read-write; replica catches up
# before backend DATABASE_URL switch.
#
# Usage: ./postgres-replication-setup.sh <old-container> <new-container>
# Both must run Postgres 17 with pglogical extension available.
set -euo pipefail

OLD="${1:?usage: postgres-replication-setup.sh <old> <new}"
NEW="${2:?usage: postgres-replication-setup.sh <old> <new}"
PGUSER="${PGUSER:-skatelab}"
PGDB="${PGDB:-skatelab}"

echo "Setting up pglogical: $OLD -> $NEW (user=$PGUSER db=$PGDB)"

install_pglogical() {
  local c="$1"
  local pmgr
  pmgr=$(docker exec "$c" sh -c 'command -v apk && echo apk || (command -v apt-get && echo apt-get)')
  case "$pmgr" in
    apk)
      docker exec "$c" sh -c 'apk add --no-cache postgresql17-pglogical 2>/dev/null || apk add --no-cache pglogical' || {
        echo "WARN: pglogical not in alpine repos on $c — switch to bitnami/postgres or build image with pglogical"
        return 1
      }
      ;;
    apt-get)
      docker exec "$c" bash -c 'apt-get update && apt-get install -y postgresql-17-pglogical || apt-get install -y postgresql-15-pglogical'
      ;;
    *)
      echo "WARN: no package manager on $c"; return 1
      ;;
  esac
  # Reload shared_preload_libraries
  docker exec "$c" sh -c "psql -U $PGUSER -d postgres -c \"ALTER SYSTEM SET shared_preload_libraries = 'pglogical';\"" 2>/dev/null || true
  docker restart "$c" >/dev/null
  sleep 3
}

echo "[1/4] Install pglogical on both..."
install_pglogical "$OLD"
install_pglogical "$NEW"

echo "[2/4] Create extension + provider node on old..."
docker exec "$OLD" psql -U "$PGUSER" -d "$PGDB" -c "CREATE EXTENSION IF NOT EXISTS pglogical;"
docker exec "$OLD" psql -U "$PGUSER" -d "$PGDB" -c "SELECT pglogical.create_node('old_provider', 'host=$OLD port=5432 dbname=$PGDB');"
docker exec "$OLD" psql -U "$PGUSER" -d "$PGDB" -c "SELECT pglogical.create_replication_set('skatelab_migration');"
docker exec "$OLD" psql -U "$PGUSER" -d "$PGDB" -c "SELECT pglogical.replication_set_add_all_tables('skatelab_migration', '{public}');"

echo "[3/4] Create extension + subscriber node on new..."
docker exec "$NEW" psql -U "$PGUSER" -d "$PGDB" -c "CREATE EXTENSION IF NOT EXISTS pglogical;"
docker exec "$NEW" psql -U "$PGUSER" -d "$PGDB" -c "SELECT pglogical.create_node('new_subscriber', 'host=$NEW port=5432 dbname=$PGDB');"
docker exec "$NEW" psql -U "$PGUSER" -d "$PGDB" -c "SELECT pglogical.create_subscription('skatelab_sub', 'old_provider', 'host=$OLD port=5432 dbname=$PGDB user=$PGUSER', 'skatelab_migration', true);"

echo "[4/4] Verify sync..."
sleep 10
OLD_COUNT=$(docker exec "$OLD" psql -U "$PGUSER" -d "$PGDB" -t -c "SELECT count(*) FROM users;" | xargs)
NEW_COUNT=$(docker exec "$NEW" psql -U "$PGUSER" -d "$PGDB" -t -c "SELECT count(*) FROM users;" | xargs)
echo "old users=$OLD_COUNT  new users=$NEW_COUNT"
if [[ "$OLD_COUNT" == "$NEW_COUNT" && -n "$OLD_COUNT" ]]; then
  echo "PASS: user count matches"
else
  echo "FAIL: mismatch (replication may still be catching up — re-run verify)"
  exit 1
fi