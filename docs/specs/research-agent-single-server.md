# Research: Single-Server Docker Compose Infrastructure Patterns

> Research conducted 2026-05-24 for infra cleanup design review.
> Context: Hetzner VPS (8 CPU, 62GB RAM, 905GB disk), ~30+ Docker services across infra/prod/dev zones.

---

## 1. Single-Server Docker Compose Infrastructure Organization

### How others structure multiple services on one VPS

The dominant pattern for running 10-30+ services on a single server is a **two-layer compose architecture**:

```
/opt/infra/
  compose.yaml          # Shared platform services (reverse proxy, DB, cache, S3, monitoring)
  .env                  # Secrets and config
  caddy/Caddyfile       # TLS termination, routing

/opt/app/
  compose.yaml          # Application services (backend, frontend, workers)
  .env                  # App-specific config (references infra services by Docker DNS)
```

Key principles from production guides:

- **Shared infrastructure compose** owns the data layer (Postgres, Valkey/Redis, object storage, reverse proxy). These are long-lived, rarely restarted, and must be backed up.
- **Application compose** owns the application layer. It connects to infra via a shared Docker network (`external: true`).
- **Dev** is code-only, no containers. Local dev uses `podman compose up valkey postgres` from the infra compose for dependencies.

### Concrete directory layout (recommended)

```
/opt/infra/                        # Platform layer (manual deploy)
  compose.yaml                     # PG, Valkey, RustFS, Caddy, PostHog, utility
  .env                             # Secrets (chmod 600)
  caddy/Caddyfile
  clickhouse/config.d/custom.xml
  prometheus/prometheus.yml
  prometheus/rules/*.yml
  backups/                         # Backup scripts and cron config
    pg_dump.sh
    clickhouse_backup.sh
    rustfs_snapshot.sh

/opt/skatelab/                     # App layer (CI/CD)
  compose.prod.yaml                # Backend, frontend, prometheus
  .env                             # App secrets (S3_*, DATABASE_URL, etc.)

/home/dev/skatelab/                # Dev code only, no containers
```

### Docker Compose profiles for optional services

Per the Docker Compose profiles specification and the detailed guide at cr0x.net:

- Services without a `profiles:` key start by default (always-on: PG, Valkey, Caddy).
- Services with `profiles: [posthog]` only start when `--profile posthog` is passed.
- This avoids running 10+ PostHog containers when PostHog is not needed.
- `COMPOSE_PROFILES=posthog` can be set in `.env` for persistent profile activation.

```yaml
services:
  postgres:
    # No profiles key = always starts
    image: postgres:17

  posthog_web:
    profiles: ["posthog"]
    image: posthog/posthog:v1.88.0
    depends_on:
      postgres:
        condition: service_healthy
      clickhouse:
        condition: service_healthy
```

**Startup commands:**

```bash
# Infra only (PG, Valkey, RustFS, Caddy)
docker compose up -d

# Infra + PostHog
docker compose --profile posthog up -d
```

### Gotchas

- **Compose V2 required** for profiles. Verify with `docker compose version` (must be v2.x).
- **Profile services with `depends_on` to non-profile services**: If PostHog services depend on PG (no profile), PG must be running first. Use `condition: service_healthy` to enforce startup order.
- **Do NOT use profiles for dev/prod parity**: Profiles are feature gates, not environment switches. Use separate compose files (`compose.prod.yaml`) for env-specific overrides.

### References

- Docker Compose profiles spec: https://docs.docker.com/reference/compose-file/profiles/
- Docker Compose startup order: https://docs.docker.com/compose/how-tos/startup-order
- Single VPS architecture guide (dchost.com): https://www.dchost.com/blog/en/docker-compose-production-vps-architecture-for-small-saas-apps
- Docker Compose profiles deep dive: https://cr0x.net/en/docker-compose-profiles-dev-prod/

---

## 2. Hetzner-Specific Docker Best Practices

### Hetzner dedicated server tips

Hetzner dedicated servers (like the AX-series) have specific considerations:

1. **No virtualization overhead** -- bare metal, full CPU/RAM available to Docker.
2. **Network**: Hetzner provides a single public IP. No private network by default; use Docker networks for inter-service communication.
3. **Storage**: Use ext4 or XFS for Docker volumes. XFS recommended for databases (better handling of large files, no fragmentation issues with PostgreSQL).
4. **Firewall**: Hetzner provides a hardware firewall option, but for Docker, use host-level iptables/nftables or Caddy as the only public-facing service.
5. **Rescue system**: Hetzner offers a rescue system for recovery. Ensure your backup strategy works independently of the host OS.

### Specific recommendations for the 8-CPU / 62GB RAM setup

With 62GB RAM and 8 CPUs on a single server:

- **Memory is your main constraint**, not CPU. 30+ containers will consume 4-8GB just for base processes. PostHog (ClickHouse + PG + Kafka + web) alone needs 8-16GB.
- **Set memory limits** on all containers. Without limits, one misbehaving container (especially ClickHouse) can OOM-kill the entire system.
- **PostHog is RAM-hungry**: allocate at least 8GB for ClickHouse, 2GB for Kafka/ZooKeeper, 2GB for PostHog web+worker. Use profiles to keep it off when not needed.
- **Use `deploy.resources.limits`** in compose:

```yaml
services:
  clickhouse:
    profiles: ["posthog"]
    deploy:
      resources:
        limits:
          memory: 8G
    # ...
```

### References

- Hetzner Docker setup guide: https://blog.antosubash.com/posts/part-1-setup-docker-with-ubuntu-server-in-hetzner
- Hetzner community tutorials: https://community.hetzner.com/tutorials

---

## 3. Caddy Reverse Proxy Across Multiple Compose Stacks

### The recommended pattern: shared external network

The standard approach for proxying across compose projects is:

1. **Define an external network** in the infra compose (where Caddy lives).
2. **Attach app compose services** to that network.
3. **Caddy routes by hostname** to service names via Docker DNS.

```yaml
# /opt/infra/compose.yaml
networks:
  app_network:
    name: infra_app_network
    driver: bridge

services:
  caddy:
    image: caddy:2
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - app_network
```

```yaml
# /opt/skatelab/compose.prod.yaml
networks:
  app_network:
    external: true
    name: infra_app_network

services:
  backend:
    image: ghcr.io/artiffusion-inc/skatelab-backend:latest
    networks:
      - app_network
    # No ports published -- Caddy proxies to backend:8000
```

```Caddyfile
# /opt/infra/caddy/Caddyfile
skatelab.ru {
    reverse_proxy backend:8000
}

ph.skatelab.ru {
    reverse_proxy posthog_web:8000
}

s3.skatelab.ru {
    reverse_proxy infra-rustfs-1:9000
}
```

### Key insight: Caddy in the same compose vs. separate

Two approaches exist:

1. **Caddy in infra compose** (recommended for this project): Caddy, PG, Valkey, RustFS are all in `/opt/infra/compose.yaml`. App compose connects via `infra_app_network`. Simple, predictable DNS resolution (`backend`, `posthog_web`, `infra-rustfs-1`).

2. **caddy-docker-proxy** (labels-based): Caddy watches Docker labels on containers across all networks and generates config dynamically. Better for dynamic multi-tenant setups, but adds complexity. Overkill for a fixed set of services.

### Gotchas

- **Network must be created by infra first**: Start infra compose before app compose, or the `external: true` network won't exist.
- **Container DNS names are service names** from the compose file that created them, prefixed with the project name by default. Use `container_name:` to get predictable names, or reference by service name within the same compose project.
- **Cross-compose DNS**: When backend (in `/opt/skatelab/`) connects to `infra-postgres-1`, it uses the Docker container name. The compose project name defaults to the directory name. Explicitly set `name:` in each compose file to avoid confusion.

```yaml
# /opt/infra/compose.yaml
name: infra  # Explicit project name
```

```yaml
# /opt/skatelab/compose.prod.yaml
name: skelab  # Explicit project name
```

### References

- SO: Caddy reverse proxy across compose stacks: https://stackoverflow.com/questions/68323071
- Reddit: Single reverse proxy for multiple compose: https://www.reddit.com/r/docker/comments/p10shc
- caddy-docker-proxy: https://github.com/lucaslorentz/caddy-docker-proxy
- Caddy community: https://caddy.community/t/basic-question-about-caddy-docker-compose/18265

---

## 4. Backup Strategy for PostgreSQL and ClickHouse

### PostgreSQL backup patterns for Docker

Three approaches, ranked by recommendation for this project:

#### Pattern A: Sidecar backup container (recommended)

A dedicated container that runs `pg_dump` on a cron schedule, stores compressed backups locally, and optionally uploads to S3.

```yaml
# In infra compose.yaml
services:
  pg_backup:
    image: postgres:17
    profiles: ["ops"]  # Or always-on with cron
    environment:
      PGHOST: postgres
      PGUSER: skatelab
      PGPASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ./backups:/backups
    entrypoint: ["/bin/sh", "-c"]
    command: >
      while true; do
        TIMESTAMP=$$(date +%Y%m%d_%H%M%S);
        pg_dump -h postgres -U skatelab -d skatelab | gzip > /backups/skatelab_$${TIMESTAMP}.sql.gz;
        pg_dump -h postgres -U posthog -d posthog | gzip > /backups/posthog_$${TIMESTAMP}.sql.gz;
        find /backups -name "*.sql.gz" -mtime +30 -delete;
        sleep 86400;
      done
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - app_network
```

**Advantages**: No host cron, reproducible, container-native, easy to test.

#### Pattern B: WAL-G for PITR (Point-in-Time Recovery)

WAL-G provides continuous WAL archiving + base backups to S3. Essential if you need to recover to a specific point in time.

- **Restore time**: ~18 minutes for a 4.2 GB database from S3 (benchmarked).
- **PITR**: Yes, can replay WAL to any point in time.
- **Overhead**: Requires WAL archiving configuration in postgres, additional S3 storage (~180MB/day for moderate write workloads).
- **Setup complexity**: Medium. Binary install, env vars for S3 credentials, `archive_command` in postgresql.conf.

```bash
# WAL-G environment (in postgres container)
export WALG_S3_PREFIX="s3://backups/postgres"
export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY}"
export WALG_COMPRESSION_METHOD=brotli

# postgresql.conf
archive_mode = on
archive_command = 'wal-g wal-push %p'
```

#### Pattern C: pg_dump with host cron

Simple but fragile. A cron job on the host runs `docker exec` to execute `pg_dump`.

**Not recommended for production**: Host cron is invisible to Docker lifecycle, hard to test, and breaks if container names change.

### Recommendation for this project

**Use Pattern A (sidecar) for daily full backups + Pattern B (WAL-G) if PITR is required.** For SkateLab's scale (single server, moderate write volume), daily `pg_dump` with 30-day retention is likely sufficient. Add WAL-G only if the RPO requirement is sub-day.

### Backup retention guidelines

| Frequency    | Retention | Storage (4.2 GB DB) |
|-------------|-----------|---------------------|
| Daily       | 30 days   | ~126 GB compressed  |
| Weekly      | 12 weeks  | ~50 GB compressed   |
| Monthly     | 12 months | ~50 GB compressed   |

With pg_dump + gzip, expect ~70% compression ratio. A 4.2 GB DB compresses to ~1.3 GB.

### ClickHouse backup patterns

For PostHog's ClickHouse data:

1. **clickhouse-backup** (by Altinity): The standard tool. Supports S3 uploads, incremental backups, and table-level restore.

```yaml
# Sidecar container for ClickHouse backups
services:
  ch_backup:
    image: altinity/clickhouse-backup:latest
    profiles: ["ops"]
    environment:
      CLICKHOUSE_HOST: clickhouse
      S3_ACCESS_KEY: ${S3_ACCESS_KEY_ID}
      S3_SECRET_KEY: ${S3_SECRET_ACCESS_KEY}
    volumes:
      - ./backups/clickhouse:/backups
    command: ["cron", "--schedule", "0 2 * * *"]  # Daily at 2 AM
```

2. **ClickHouse native BACKUP/RESTORE commands**: Available since ClickHouse 22.7, but requires `allow_backup_to_s3` setting. Less flexible than clickhouse-backup.

3. **Cold backup**: Stop ClickHouse, copy data directory, restart. Only for maintenance windows.

### References

- pgbackrest alternatives (WAL-G vs Barman vs pg_dump): https://juanchi.dev/en/blog/pgbackrest-unmaintained-postgres-backup-alternatives-production
- Cookiecutter Django PostgreSQL backups: https://cookiecutter-django.readthedocs.io/en/latest/4-guides/docker-postgres-backups.html
- clickhouse-backup: https://github.com/altinity/clickhouse-backup
- ClickHouse S3 backup docs: https://clickhouse.com/docs/operations/backup/s3_endpoint

---

## 5. RustFS vs MinIO vs SeaweedFS for Single-Server S3 Storage

### Comparison table

| Feature | RustFS | MinIO | SeaweedFS |
|---------|--------|-------|-----------|
| **Language** | Rust | Go | Go |
| **License** | Apache 2.0 | AGPLv3 (since 2024) | Apache 2.0 |
| **S3 compatibility** | 100% | 100% | ~95% (most APIs) |
| **Single-node mode** | Yes | Yes | Yes (volume + filer) |
| **Distributed mode** | Alpha (not production) | Yes (erasure coding) | Yes (volume servers + filer) |
| **Memory safety** | Yes (Rust) | No (Go, GC pauses) | No (Go) |
| **Docker image size** | ~80 MB | ~150 MB | ~100 MB (filer) + ~60 MB (volume) |
| **Console UI** | Yes (port 9001) | Yes (port 9001) | No built-in UI |
| **Production readiness** | Alpha -- not recommended for mission-critical | Mature, but AGPL risk | Mature, used at scale |
| **Performance (single node)** | Good (see benchmarks below) | Excellent | Excellent |
| **MinIO community status** | -- | No longer accepting community changes (maintenance mode) | Active community |

### Performance benchmarks (from rustfs/rustfs GitHub discussion #1500)

Tests run on 4-node clusters, warp benchmark. Key results for single-server relevance (128 threads, large objects):

| Operation | RustFS | MinIO | SeaweedFS |
|-----------|--------|-------|-----------|
| GET (5 MiB) | 1,898 MiB/s | 1,987 MiB/s | 1,900 MiB/s |
| GET (32 MiB) | 1,947 MiB/s | 2,013 MiB/s | 1,886 MiB/s |
| PUT (5 MiB) | 629 MiB/s | 632 MiB/s | 634 MiB/s |
| PUT (32 MiB) | 648 MiB/s | 651 MiB/s | 633 MiB/s |

**RustFS is within 3-5% of MinIO on GET, and within 1-2% on PUT** for large objects. Performance is not a differentiator.

### Critical considerations for this project

**RustFS is alpha software.** The Milvus evaluation (May 2026) explicitly states: "RustFS is still under active development, and its distributed mode has not yet been officially released. RustFS is not recommended for production or mission-critical workloads at this stage."

**RustFS crashed under high concurrency** (512+ threads at 1 MiB object size) in the benchmarks. This is a red flag for production use.

**MinIO AGPLv3 licensing** is the reason many are migrating away. Since 2024, MinIO no longer accepts community contributions and uses AGPLv3, which requires open-sourcing your entire application if you distribute MinIO as part of it. For a self-hosted single-server setup where you're not distributing the software, AGPLv3 is not a legal concern -- but the "maintenance mode" of the OSS project is.

**SeaweedFS** is the most mature distributed alternative. It scales well, has an active community, but its single-node setup requires running both `volume` and `filer` services, and its S3 compatibility is not 100% (edge cases with multipart upload, versioning).

### Recommendation

For this project (single-server, S3-compatible storage for SkateLab video pipeline + PostHog):

1. **Short term: RustFS** (as currently specified in the design). It's already in the compose, its S3 API compatibility is sufficient for the workload (video upload, PostHog events), and single-node mode works for the use case. The alpha risk is mitigated by having backups.

2. **Have a migration plan to MinIO or SeaweedFS** if RustFS proves unstable. The `S3_*` variable naming already abstracts the backend, making migration a config change.

3. **If RustFS causes issues**, switch to MinIO (pin to the last community-acceptable version) or SeaweedFS. MinIO is the path of least resistance for single-server S3.

### RustFS Docker setup (from design spec, confirmed)

```yaml
rustfs:
  image: rustfs/rustfs:latest
  container_name: infra-rustfs-1
  environment:
    RUSTFS_ACCESS_KEY: ${S3_ACCESS_KEY_ID}
    RUSTFS_SECRET_KEY: ${S3_SECRET_ACCESS_KEY}
    RUSTFS_CONSOLE_ENABLE: "true"
  ports:
    - "9000:9000"   # S3 API
    - "9001:9001"   # Console
  volumes:
    - rustfs_data:/data
  command: server /data
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:9000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### References

- RustFS evaluation for Milvus: https://milvus.io/blog/evaluating-rustfs-as-a-viable-s3-compatible-object-storage-backend-for-milvus.md
- RustFS performance benchmarks: https://github.com/orgs/rustfs/discussions/1500
- RustFS official site: https://rustfs.com
- SeaweedFS vs MinIO comparison: https://itnext.io/minio-alternative-seaweedfs-41fe42c3f7be
- LowEndTalk production comparison: https://lowendtalk.com/discussion/210203/

---

## 6. Prometheus Monitoring for 30+ Docker Services

### Recommended stack for single-server monitoring

```
Prometheus (metrics collection)
  + Node Exporter (host metrics: CPU, RAM, disk, network)
  + cAdvisor (container metrics: per-container CPU, memory, I/O)
  + Grafana (dashboards and visualization)
  + Alertmanager (alert routing)
```

### Resource planning for 30+ containers

On a 62 GB RAM server with 8 CPUs:

| Component | RAM | CPU | Disk (TSDB) |
|-----------|-----|-----|-------------|
| Prometheus | 500 MB - 2 GB | 0.5 core | 1 GB/day per 200 targets |
| Node Exporter | 20 MB | negligible | -- |
| cAdvisor | 100-200 MB | 0.1 core | -- |
| Grafana | 100-200 MB | 0.1 core | 50 MB |
| Alertmanager | 20-50 MB | negligible | 10 MB |
| **Total** | ~1-3 GB | ~1 core | ~5 GB/month |

For 30+ containers, expect ~500-1000 time series per container. With 15-second scrape intervals, Prometheus needs about 500 MB RAM and 1-2 GB disk per month.

### Key configuration recommendations

```yaml
# prometheus.yml - optimized scrape config
global:
  scrape_interval: 15s       # Default
  evaluation_interval: 15s   # Rule evaluation

scrape_configs:
  # Host metrics - more frequent
  - job_name: 'node-exporter'
    scrape_interval: 10s
    static_configs:
      - targets: ['node-exporter:9100']

  # Container metrics - moderate frequency
  - job_name: 'cadvisor'
    scrape_interval: 15s
    static_configs:
      - targets: ['cadvisor:8080']

  # Application metrics - varies by service
  - job_name: 'backend'
    scrape_interval: 30s     # App metrics change slowly
    static_configs:
      - targets: ['backend:8000']

  # Prometheus self-monitoring
  - job_name: 'prometheus'
    scrape_interval: 30s
    static_configs:
      - targets: ['localhost:9090']
```

### TSDB retention settings

```yaml
# In Prometheus compose service
command:
  - '--storage.tsdb.retention.time=30d'      # Keep 30 days of data
  - '--storage.tsdb.retention.size=10GB'     # Or cap at 10GB
  - '--storage.tsdb.path=/prometheus'
```

For single-server monitoring, 30 days retention at 10GB max is generous. Start conservative and increase only if needed.

### Critical alert rules for 30+ containers

```yaml
# rules/container_alerts.yml
groups:
  - name: container_alerts
    rules:
      # Container restart loop
      - alert: ContainerRestarting
        expr: delta(container_start_time_seconds{name!=""}[15m]) > 0
        for: 5m
        labels:
          severity: warning

      # Memory pressure
      - alert: HighMemoryUsage
        expr: (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) < 0.1
        for: 5m
        labels:
          severity: critical

      # Disk space
      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes{fstype=~"ext4|xfs"} / node_filesystem_size_bytes{fstype=~"ext4|xfs"}) < 0.15
        for: 10m
        labels:
          severity: warning

      # Predictive: unusual memory growth
      - alert: UnusualMemoryGrowth
        expr: deriv(node_memory_MemAvailable_bytes[30m]) < -10 * 1024 * 1024
        for: 10m
        labels:
          severity: warning

      # CPU throttling (container-level)
      - alert: ContainerCPUThrottling
        expr: rate(container_cpu_cfs_throttled_periods_total{name!=""}[5m]) / rate(container_cpu_cfs_periods_total{name!=""}[5m]) > 0.25
        for: 5m
        labels:
          severity: warning
```

### cAdvisor configuration

cAdvisor provides per-container metrics essential for a dense single-server setup:

```yaml
cadvisor:
  image: gcr.io/cadvisor/cadvisor:latest
  container_name: cadvisor
  volumes:
    - /:/rootfs:ro
    - /var/run:/var/run:rw
    - /sys:/sys:ro
    - /var/lib/docker/:/var/lib/docker:ro
    - /dev/disk/:/dev/disk:ro
  ports:
    - "8080:8080"
  networks:
    - monitoring
  restart: unless-stopped
```

**Important**: cAdvisor needs access to `/var/lib/docker` and `/dev/disk` to collect per-container I/O metrics. These are read-only mounts.

### References

- Prometheus Docker Compose guide: https://last9.io/blog/prometheus-with-docker-compose
- Grafana Cloud: Prometheus with Docker Compose on Linux: https://grafana.com/docs/grafan-cloud/send-data/metrics/metrics-prometheus/prometheus-config-examples/docker-compose-linux
- Uptrace: Prometheus for Docker: https://uptrace.dev/tools/prometheus-for-docker

---

## 7. Docker Compose Healthcheck and Dependency Ordering

### The `depends_on` + `healthcheck` pattern

Docker Compose `depends_on` with `condition` is the canonical way to control startup order. There are three conditions:

| Condition | Meaning |
|-----------|---------|
| `service_started` | Wait until container starts (default, weakest) |
| `service_healthy` | Wait until healthcheck passes (recommended) |
| `service_completed_successfully` | Wait until container exits with code 0 (for init tasks) |

### Recommended pattern for this project

```yaml
services:
  # Layer 1: Data stores (no dependencies)
  postgres:
    image: postgres:17
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U skatelab"]
      interval: 5s
      timeout: 5s
      retries: 20
      start_period: 30s
    # No depends_on -- starts first

  valkey:
    image: valkey/valkey:8
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    # No depends_on -- starts first

  rustfs:
    image: rustfs/rustfs:latest
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    # No depends_on -- starts first

  # Layer 2: Services that depend on data stores
  backend:
    depends_on:
      postgres:
        condition: service_healthy
      valkey:
        condition: service_healthy
      rustfs:
        condition: service_healthy

  # Layer 3: Reverse proxy (depends on app)
  caddy:
    depends_on:
      backend:
        condition: service_healthy
      # Don't wait for posthog -- it starts independently
```

### Healthcheck best practices

1. **Always set `start_period`**: Services need time to initialize before healthchecks start counting retries. PostgreSQL needs 10-30 seconds for WAL recovery on restart.

2. **Use `retries: 5-20` for data stores**: Databases can take 10-60 seconds to become ready, especially after a crash recovery. More retries prevents flapping.

3. **Use `interval: 5-10s`**: Frequent enough to detect readiness, but not so frequent it adds load.

4. **For application healthchecks**, add a `/health` endpoint:

```yaml
backend:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 10s
    timeout: 3s
    retries: 12
    start_period: 15s
```

5. **For PostHog services** (which can be slow to start):

```yaml
posthog_web:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 15s
    timeout: 10s
    retries: 20
    start_period: 60s    # PostHog is slow to start
```

6. **ClickHouse healthcheck**:

```yaml
clickhouse:
  healthcheck:
    test: ["CMD", "clickhouse-client", "--query", "SELECT 1"]
    interval: 10s
    timeout: 5s
    retries: 10
    start_period: 30s
```

### Common healthcheck commands

| Service | Healthcheck Command |
|---------|-------------------|
| PostgreSQL | `pg_isready -U <user> -d <db>` |
| Valkey/Redis | `valkey-cli ping` / `redis-cli ping` |
| Caddy | `curl -f http://localhost:2019/config/` (admin API) |
| RustFS/MinIO | `curl -f http://localhost:9000/health` |
| ClickHouse | `clickhouse-client --query "SELECT 1"` |
| Kafka | `kafka-topics --bootstrap-server localhost:9092 --list` |
| FastAPI/uvicorn | `curl -f http://localhost:8000/health` |
| Next.js | `curl -f http://localhost:3000/api/health` |

### Gotchas

- **`restart: true` on `depends_on`**: In Docker Compose v2.27+, you can set `restart: true` on `depends_on` to auto-restart dependents when a dependency restarts. This is useful for backend when postgres restarts.

```yaml
backend:
  depends_on:
    postgres:
      condition: service_healthy
      restart: true  # Restart backend if postgres restarts
```

- **Healthchecks and profiles**: A profile service with `depends_on` referencing a non-profile service works fine. But if a non-profile service depends on a profile service, it will fail when the profile is not active. Ensure dependency direction always goes from profile services to core services.

- **`start_period` is critical for databases**: Without it, PostgreSQL's crash recovery can take 30+ seconds and the healthcheck will mark it unhealthy before it finishes recovery, causing cascading failures.

### References

- Docker Compose startup order docs: https://docs.docker.com/compose/how-tos/startup-order
- Docker Compose healthcheck guide: https://last9.io/blog/docker-compose-health-checks
- OneUptime: depends_on with healthchecks: https://oneuptime.com/blog/post/2026-01-16-docker-compose-depends-on-healthcheck/view

---

## Summary of Recommendations

| Area | Recommendation | Risk Level |
|------|---------------|------------|
| **Organization** | Two-compose architecture (infra + app) with shared external network | Low |
| **Profiles** | PostHog behind `profiles: [posthog]` to save RAM when not in use | Low |
| **Reverse proxy** | Caddy in infra compose, `infra_app_network` shared network, hostname-based routing | Low |
| **PostgreSQL backup** | Sidecar `pg_dump` cron container + 30-day retention. Add WAL-G if PITR needed | Low |
| **ClickHouse backup** | `clickhouse-backup` sidecar with S3 upload | Low |
| **S3 storage** | RustFS (already specified), but monitor for stability. Have MinIO migration plan ready | Medium (alpha software) |
| **Monitoring** | Prometheus + Node Exporter + cAdvisor + Grafana. 10-15s scrape intervals. 30-day retention | Low |
| **Healthchecks** | `depends_on` with `condition: service_healthy` on all data stores. Set `start_period` for DBs | Low |
| **Memory limits** | Set `deploy.resources.limits.memory` on all containers, especially ClickHouse (8GB) | High if skipped |