# PostHog Infrastructure Setup

## Overview

PostHog self-hosted deployed on existing Hetzner dedic alongside SkateLab services.
~28 containers, 14.5GB RAM (saved 1.5GB via shared Valkey + RustFS).

## Quick Start

```bash
# 1. Download official hobby compose
curl -sL https://raw.githubusercontent.com/PostHog/posthog/master/docker-compose.hobby.yml \
  -o /opt/posthog/docker-compose.yml

# 2. Apply our overlay (see overlay.patch below)
# 3. Copy and fill env
cp .env.posthog.example .env.posthog
vim .env.posthog

# 4. Start data layer first
docker compose up -d posthog-db kafka
# Wait for healthy, then:
docker compose up -d
```

## Overlay Changes from Default Hobby Compose

Apply these modifications to the official `docker-compose.hobby.yml`:

### Remove services (replaced by shared infra)
- **`objectstorage` (MinIO)** — replaced by RustFS at `infra-rustfs-1:9000`
- **`seaweedfs`** — replaced by RustFS
- **`redis7`** — replaced by shared Valkey at `infra-valkey-1:6379/2`

### Modify services
- **`db`**: Pin image to `postgres:15.12-alpine` (NOT PG 17). Add port `5433:5432` to avoid clash with SkateLab PG.
- **`clickhouse`**: Mount `./clickhouse/config.d/custom.xml` to `/etc/clickhouse-server/config.d/custom.xml`. Set `memory_limit=4G`.
- **`web`, `worker`, `plugins`**: Add env vars `REDIS_URL=redis://infra-valkey-1:6379/2`, `OBJECT_STORAGE_ENDPOINT=http://infra-rustfs-1:9000`, `OBJECT_STORAGE_ACCESS_KEY_ID=...`, `OBJECT_STORAGE_SECRET_ACCESS_KEY=...`, `SESSION_RECORDING_V2_S3_ENDPOINT=http://infra-rustfs-1:9000`, `SESSION_RECORDING_V2_S3_ACCESS_KEY_ID=...`, `SESSION_RECORDING_V2_S3_SECRET_ACCESS_KEY=...`
- **All services**: Add `networks: [infra]` and remove default network config.
- **`kafka` (Redpanda)**: Set `--memory 3G --reserve-memory 500M --smp 2` in command.

### Network
All services on `infra_app_network` (external) to share with SkateLab services.

## Deployment Order

```
Phase 1: Data layer (no deps)
  posthog-db, kafka (Redpanda)

Phase 2: Analytics engine
  clickhouse (depends on kafka)

Phase 3: Processing services
  kafka-init → Rust + Node.js services

Phase 4: Application
  web, worker, temporal

Phase 5: Proxy + verification
  Caddy route → test events in ClickHouse
```

## Monitoring

Prometheus scrape targets (add to `infra/prometheus/prometheus.yml`):
- `posthog_clickhouse:8123` — ClickHouse metrics
- `posthog_kafka:9644` — Redpanda metrics

Alert rules in `infra/prometheus/rules/posthog.yml`.

## Backup

- **PostgreSQL**: Daily `pg_dump` both `posthog` + `posthog_persons` DBs → RustFS
- **ClickHouse**: Weekly native `BACKUP DATABASE posthog TO S3(...)` (CH 26.3+)
- **Valkey**: None (DB 2 is cache-only)
- **RustFS**: Local disk — rely on dedic backups

## Upgrade

1. Pin `POSTHOG_APP_TAG` to specific version (NOT `latest`)
2. Read changelog between current and target version
3. Pull during low-traffic window (30min routine, 2hr for major)
4. Monitor `asyncmigrationscheck` logs for ClickHouse migration completion
5. Keep previous tag for rollback: `POSTHOG_APP_TAG=<old> docker compose up -d`