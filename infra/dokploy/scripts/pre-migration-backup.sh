#!/usr/bin/env bash
# Snapshot all volumes + DBs before Dokploy migration.
# Run on VPS as user with docker access (sudo not required for docker if user in docker group).
set -euo pipefail

BACKUP_DIR="/opt/backups/migration-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "[1/6] Snapshotting /opt/infra/ volumes..."
tar -czf "$BACKUP_DIR/infra-volumes.tar.gz" -C /var/lib/docker/volumes \
  infra_valkey-data \
  infra_postgres-data \
  infra_rustfs-data \
  2>/dev/null || echo "WARN: some infra volumes missing (may be named differently)"

echo "[2/6] Snapshotting /opt/skatelab/ volumes..."
tar -czf "$BACKUP_DIR/skatelab-volumes.tar.gz" -C /var/lib/docker/volumes \
  skatelab_prometheus-data \
  2>/dev/null || echo "WARN: skatelab volumes missing"

echo "[3/6] Backing up Postgres (pg_dumpall)..."
docker exec infra-postgres-1 pg_dumpall -U skatelab > "$BACKUP_DIR/postgres.sql"

echo "[4/6] Backing up Valkey (BGSAVE)..."
docker exec infra-valkey-1 valkey-cli -n 3 BGSAVE >/dev/null
sleep 5
docker cp infra-valkey-1:/data/dump.rdb "$BACKUP_DIR/valkey-dump.rdb"

echo "[5/6] Backing up ClickHouse (skip if not deployed)..."
if docker ps --filter name=clickhouse --format '{{.Names}}' | grep -q clickhouse; then
  docker exec infra-clickhouse-1 clickhouse-client --query \
    "BACKUP DATABASE default TO Disk('backups', 'migration-$(date +%Y%m%d).zip')" 2>/dev/null || \
    echo "WARN: ClickHouse backup query failed"
else
  echo "ClickHouse not deployed, skipping (confirms spec finding #29)"
fi

echo "[6/6] Backing up RustFS data dir..."
if docker inspect infra-rustfs-1 --format '{{range .Mounts}}{{.Source}}{{"\n"}}{{end}}' 2>/dev/null | grep -q .; then
  RUSTFS_SRC=$(docker inspect infra-rustfs-1 --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}')
  if [[ -n "$RUSTFS_SRC" && -d "$RUSTFS_SRC" ]]; then
    tar -czf "$BACKUP_DIR/rustfs-data.tar.gz" -C "$(dirname "$RUSTFS_SRC")" "$(basename "$RUSTFS_SRC")" 2>/dev/null || \
      echo "WARN: RustFS tar failed"
  else
    echo "WARN: RustFS data path not found, falling back to S3 sync"
  fi
else
  echo "WARN: RustFS container not inspectable"
fi

echo "Backup complete: $BACKUP_DIR"
ls -lah "$BACKUP_DIR"