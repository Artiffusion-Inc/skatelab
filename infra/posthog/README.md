# PostHog Infrastructure Setup

## Overview

PostHog self-hosted on existing Hetzner dedic alongside SkateLab services.
~28 containers, ~14.5GB RAM (saved ~1.5GB via shared Valkey + RustFS).

Uses **docker-compose overlay pattern**: official hobby compose + our override.

## Quick Start

```bash
# 1. Download official hobby compose (into /opt/posthog/)
curl -sL https://raw.githubusercontent.com/PostHog/posthog/master/docker-compose.hobby.yml \
  -o /opt/posthog/docker-compose.yml

# 2. Copy our overlay + config into place
#    docker-compose.override.yml → /opt/posthog/
#    clickhouse/config.d/custom.xml → /opt/posthog/clickhouse/config.d/
#    .env.posthog → /opt/posthog/.env

# 3. Start data layer first
docker compose up -d db kafka
# Wait for healthy, then:
docker compose up -d clickhouse kafka-init
# Then all services:
docker compose up -d
```

## Overlay Changes (docker-compose.override.yml)

Applied on top of official `docker-compose.hobby.yml`:

### Removed services (replaced by shared infra, hidden via `profiles: [disabled]`)
- **`objectstorage`** (MinIO) → shared RustFS at `infra-rustfs-1:9000`
- **`seaweedfs`** → shared RustFS at `infra-rustfs-1:9000`
- **`redis7`** → shared Valkey at `infra-valkey-1:6379/2`
- **`proxy`** (Caddy) → infra Caddy at `ph.skatelab.ru`
- **`zookeeper`** → Redpanda KRaft mode (no ZK needed)

### Modified services
- **`db`**: Pin `postgres:15.12-alpine` (NOT PG 17). Port `5433:5432` (avoid clash with infra PG on 5432). On `infra_app_network`.
- **`clickhouse`**: Mount `./clickhouse/config.d/custom.xml` (4GB RAM limit). On `infra_app_network`.
- **`kafka`** (Redpanda): KRaft mode `--smp 2 --memory 3G --reserve-memory 500M`. No Zookeeper dependency.
- **`web`, `worker`, `plugins`, `temporal-django-worker`**: `REDIS_URL=redis://infra-valkey-1:6379/2`, `OBJECT_STORAGE_ENDPOINT=http://infra-rustfs-1:9000`, `SESSION_RECORDING_V2_S3_ENDPOINT=http://infra-rustfs-1:9000` + RustFS credentials.
- **All Rust services** (`capture`, `replay-capture`, `feature-flags`, `property-defs-rs`, `cyclotron-janitor`, `cymbal`, `personhog-router`, `hypercache-server`): `REDIS_URL=redis://infra-valkey-1:6379/2`. Storage services get RustFS endpoints.
- **All Node.js ingestion services**: `REDIS_URL=redis://infra-valkey-1:6379/2`. `recording-api` gets RustFS session recording vars.
- **All services**: Added `networks: [infra]` (external `infra_app_network`).

### Network
All services on `infra_app_network` (external) — shared with SkateLab + infra stacks.

## Deployment Order

```
Phase 1: Data layer (no deps)
  db, kafka (Redpanda)

Phase 2: Analytics engine
  clickhouse (depends on kafka)

Phase 3: Processing services
  kafka-init → Rust + Node.js services

Phase 4: Application
  web, worker, temporal

Phase 5: Proxy + verification
  Caddy route (infra stack) → test events in ClickHouse
```

## RustFS Bucket Setup

PostHog needs a bucket in RustFS before first start:

```bash
# Using s3cmd or mc client against RustFS
mc alias set rustfs http://s3.skatelab.ru <access-key> <secret-key>
mc mb rustfs/posthog
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
3. Download updated `docker-compose.hobby.yml` (our override stays unchanged)
4. Pull during low-traffic window (30min routine, 2hr for major)
5. Monitor `asyncmigrationscheck` logs for ClickHouse migration completion
6. Keep previous tag for rollback: `POSTHOG_APP_TAG=<old> docker compose up -d`