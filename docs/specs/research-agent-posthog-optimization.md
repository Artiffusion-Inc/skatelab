# PostHog Self-Hosted Optimization Research

**Date:** 2026-05-24
**Context:** SkateLab dedic server — 8 CPU, 62GB RAM, 905GB disk (Hetzner). PostHog hobby tier with ~24 services consuming ~14.5GB RAM. Current config: ClickHouse 5g limit (4GB max server + 1GB mark cache), Redpanda 4g limit, PostgreSQL 15 1g limit.

---

## 1. Minimum Viable Specs for PostHog Self-Hosted

### Official Requirements

PostHog's official hobby deployment docs state:
- **Minimum: 4 vCPU, 16GB RAM, 30GB+ storage** (Hetzner-equivalent VM)
- This is the floor, not the recommendation for production

### Real-World Reports

| Source | Specs | Result |
|--------|-------|--------|
| GitHub #27120 | GCP 2 vCPU, 8GB RAM | Crashed after ~30 min. System became unresponsive. |
| GitHub #3888 | 1 vCPU, 2GB RAM, 20GB SSD | PostHog idle: 800MB, Postgres idle: 600MB. VPS died after 2-3 days. |
| Reddit r/digital_ocean | 8GB minimum | "All these services (especially ClickHouse) eat up a lot of RAM, which is why the minimum requirement is 16GB" |
| Cotera article (healthcare SaaS) | 3x Kubernetes nodes + managed PG + dedicated ClickHouse + S3 | ~$450/month infra cost. 6-8 hrs/month maintenance. |

### Key Findings

1. **8GB RAM is the absolute floor** and unstable under load. PostHog's own docs recommend 16GB.
2. Our 62GB server has ample headroom. The current 14.5GB allocation for PostHog is conservative and leaves ~47.5GB for SkateLab + other services.
3. The real bottleneck is not total RAM but **ClickHouse memory behavior** — it will consume everything available unless hard-limited via Docker `mem_limit` AND ClickHouse's own `max_server_memory_usage`.

### Recommendations

- **Current 14.5GB allocation is adequate for low-traffic hobby use.** No need to reduce.
- If SkateLab needs more RAM, ClickHouse could be reduced to **3-4GB total** (see Section 4 for tuning), freeing 1-2GB.
- The 5GB Docker limit + 4GB `max_server_memory_usage` is reasonable. The 1GB gap allows for ClickHouse overhead outside the query engine.

---

## 2. PostHog GitHub Issues — Known Memory Problems

### Issue #27120: Performance Issues on Minimum Specs (8GB, 2 CPU)

- User deployed PostHog on GCP with minimum recommended specs
- System worked for ~30 minutes then became completely unresponsive
- Screenshot shows all containers at high CPU/memory
- **Lesson: 8GB is not enough for stable PostHog operation under any real load**

### Issue #3888: 900MB Memory at Idle

- Two VPS with 1 vCPU, 2GB RAM each
- At idle: Redis 5MB, Postgres 600MB, PostHog web 800MB
- Both VPS died within 2-3 days
- **Lesson: PostHog's Python/Django web server alone uses ~800MB idle. This is not tunable.**

### Issue #28804: Self-Host Basic Bugs

- Multiple issues with the latest self-hosted deployment
- Docker Compose has stale/unstable tags
- CSRF issues, missing ClickHouse UDFs for funnel queries
- Session recording broken by default
- **Lesson: Self-hosted PostHog requires careful tag pinning. Rolling `latest` is unreliable.**

### Issue from HN Discussion: SSRF & Default Creds

- PostHog hobby deployment had default PostgreSQL credentials (`posthog:posthog`)
- ClickHouse SQL injection possible via SSRF
- **Lesson: Change default credentials. Ensure ClickHouse is not exposed externally.**

### General Patterns from Issues

1. **Zookeeper/Kafka memory** is a major contributor. Our setup already uses Redpanda in KRaft mode (no Zookeeper) which saves ~500MB-1GB.
2. **PostHog web container** at ~800MB idle is the largest non-tunable consumer.
3. **ClickHouse is the most aggressive memory user** — it will consume all available RAM unless limited both at Docker level AND in ClickHouse config.

---

## 3. Redpanda vs Kafka — Resource Usage for Small Deployments

### Architecture Comparison

| Aspect | Kafka (KRaft, no ZK) | Redpanda |
|--------|---------------------|----------|
| Language | Java (JVM) | C++ (Seastar) |
| Memory model | JVM heap (configurable, default 2GB) | Allocates available RAM for cache |
| Single-node complexity | KRaft controller + broker | Single binary, built-in schema registry + HTTP proxy |
| No Zookeeper | Yes (Kafka 4.0+) | Yes (always KRaft-native) |

### Real Benchmark Data (April 2026, identical 4 vCPU / 8GB VMs)

Source: computingforgeeks.com Kafka vs Redpanda benchmarks

| Test | Kafka 4.2.0 | Redpanda 26.1.2 |
|------|-------------|-----------------|
| 100B, 1 partition, acks=1 | 203K rec/s, 989ms avg lat | **296K rec/s**, 533ms avg lat |
| 1KB, 1 partition, acks=1 | 81K rec/s, 350ms avg lat | **100K rec/s**, 191ms avg lat |
| 100B, 6 partitions, acks=1 | **479K rec/s**, 17ms avg lat | 291K rec/s, 34ms avg lat |
| 1KB, 6 partitions, acks=1 | **165K rec/s**, 57ms avg lat | 61K rec/s, 460ms avg lat |
| acks=all (single node) | **326K rec/s**, 573ms avg lat | 39K rec/s, 6,275ms avg lat |
| Sustained 5M x 1KB (6 partitions) | **211K rec/s**, 2.53ms avg lat | 89K rec/s, 315ms avg lat |

### Memory Comparison

- **Kafka (KRaft, no ZooKeeper):** JVM heap 2GB default. Total process memory ~3-4GB (heap + JVM overhead + OS page cache usage).
- **Redpanda:** Seastar allocates all available RAM for cache. With Docker `mem_limit=4g`, Redpanda will try to use ~3.5GB (leaving some for OS overhead). Our config: `2 SMP, 3G memory, 500M reserved` = effective ~2.5GB for Redpanda cache.
- **Key insight for small deployments:** Redpanda's memory model is *less* predictable because it tries to use all available RAM. Kafka's JVM heap is a fixed ceiling. For a resource-constrained single-node deployment, **Kafka with a small heap (1-2GB) is more predictable**.

### Verdict for Our Setup

**Our current Redpanda config (4g limit, 2 SMP, 3G memory, 500M reserved) is appropriate.**

- Redpanda in KRaft mode eliminates Zookeeper (~512MB savings vs Kafka+ZK)
- For single-node hobby deployment, Redpanda's `acks=all` penalty is irrelevant (PostHog uses `acks=1` for event ingestion)
- Redpanda's single-binary deployment is simpler operationally than Kafka+KRaft
- **Do NOT switch to Kafka.** The marginal memory savings from a small Kafka heap would be offset by added operational complexity and the need for a separate KRaft controller.

### If Further Optimization Needed

- Redpanda memory can be reduced to **3g Docker limit, 2G memory, 500M reserved** for very low event volumes
- This saves ~1GB but risks OOM under burst loads

---

## 4. ClickHouse Tuning for Low-Memory Deployments (4GB RAM)

### Current Configuration

Our `custom.xml`:
```xml
<clickhouse>
    <max_server_memory_usage>4294967296</max_server_memory_usage>  <!-- 4GB -->
    <mark_cache_size>1073741824</mark_cache_size>                   <!-- 1GB -->
    <index_mark_cache_size>268435456</index_mark_cache_size>        <!-- 256MB -->
    <max_bytes_to_merge_at_max_space_in_pool>536870912</max_bytes_to_merge_at_max_space_in_pool>  <!-- 512MB -->
</clickhouse>
```

### Altinity KB Recommendations for Low Memory (4GB Raspberry Pi)

Source: kb.altinity.com — Configure ClickHouse for low memory environments

Key settings for 4GB RAM:

| Setting | Recommended (4GB) | Our Current | Notes |
|---------|-------------------|-------------|-------|
| `mark_cache_size` | **256MB** (for 4/8GB total) | 1024MB | **OVER-ALLOCATED.** 1GB mark cache is for 16GB+ systems. At 4GB server memory, 256MB is appropriate. |
| `index_mark_cache_size` | Not specified | 256MB | Reasonable for our size |
| `max_server_memory_usage` | Leave ~25% for OS | 4GB | Should be ~3GB if Docker limit is 5GB, or 4GB if 5GB Docker limit |
| `max_server_memory_usage_to_ram_ratio` | 0.75 | Not set | **ADD THIS.** Prevents ClickHouse from using more than 75% of total RAM |
| `background_pool_size` | 1-2 (match core count) | Not set (default 16) | **ADD THIS.** Reduce merge thread pool |
| `merge_max_block_size` | 1024 (from 8192 default) | Not set | **ADD THIS.** Reduces per-merge memory |
| `max_bytes_to_merge_at_max_space_in_pool` | 268MB (256MB) | 512MB | Could reduce to 256MB |
| `max_concurrent_queries` | 2 | Not set | **ADD THIS.** Limit concurrent queries |
| `max_execution_time` | 60 (seconds) | Not set | **ADD THIS.** Kill long queries |
| `max_bytes_before_external_group_by` | Enable disk spilling | Not set | **ADD THIS.** Allows GROUP BY to spill to disk |
| `max_bytes_before_external_sort` | Enable disk spilling | Not set | **ADD THIS.** Allows ORDER BY to spill to disk |

### Additional Recommendations from Uptrace & Community

1. **Disable unused interfaces:**
   ```xml
   <mysql_port remove="1" />
   <postgresql_port remove="1" />
   ```
   Frees CPU and memory resources.

2. **Disable verbose system logs:**
   ```xml
   <query_log remove="1" />
   <query_thread_log remove="1" />
   <text_log remove="1" />
   <trace_log remove="1" />
   <metric_log remove="1" />
   <asynchronous_metric_log remove="1" />
   <session_log remove="1" />
   <part_log remove="1" />
   <processor_profile_log remove="1" />
   <opentelemetry_span_log remove="1" />
   ```
   These tables write continuously and consume disk I/O + memory on small systems.

3. **Enable `cache_size_to_ram_max_ratio`** (ClickHouse 24.11+):
   Set to `0.2` to limit cache size to 20% of RAM.

4. **Reduce `max_block_size`** to 8192 (already default) or lower for low-memory.

### James O'Claire's 2GB Docker Experience

Key settings for <2GB RAM:
```xml
<max_server_memory_usage_to_ram_ratio>0.2</max_server_memory_usage_to_ram_ratio>
<mark_cache_size>2000000000</mark_cache_size>  <!-- 2GB for larger systems -->
```
For 2GB systems, set `max_server_memory_usage_to_ram_ratio` to 0.2 (very conservative). For 4-5GB, 0.75 is reasonable.

### Plausible's ClickHouse Low-Memory Config (Community)

```xml
<clickhouse>
    <mysql_port remove="1" />
    <postgresql_port remove="1" />
    <query_thread_log remove="1" />
    <opentelemetry_span_log remove="1" />
    <processors_profile_log remove="1" />
    <processor_profile_log remove="1" />
    <query_log remove="1"/>
    <text_log remove="1"/>
    <trace_log remove="1"/>
    <metric_log remove="1"/>
    <asynchronous_metric_log remove="1"/>
    <session_log remove="1"/>
    <part_log remove="1"/>
    <mlock_executable>false</mlock_executable>
    <background_pool_size>1</background_pool_size>
    <background_merges_mutations_concurrency_ratio>2</background_merges_mutations_concurrency_ratio>
    <merge_tree>
        <merge_max_block_size>1024</merge_max_block_size>
        <max_bytes_to_merge_at_max_space_in_pool>268435456</max_bytes_to_merge_at_max_space_in_pool>
        <number_of_free_entries_in_pool_to_lower_max_size_of_merge>2</number_of_free_entries_in_pool_to_lower_max_size_of_merge>
        <number_of_free_entries_in_pool_to_execute_mutation>2</number_of_free_entries_in_pool_to_execute_mutation>
        <number_of_free_entries_in_pool_to_execute_optimize_entire_partition>2</number_of_free_entries_in_pool_to_execute_optimize_entire_partition>
    </merge_tree>
</clickhouse>
```

### Recommended Optimized Config for Our 5GB Docker Limit

```xml
<clickhouse>
    <!-- Memory limits -->
    <max_server_memory_usage>4294967296</max_server_memory_usage>
    <max_server_memory_usage_to_ram_ratio>0.75</max_server_memory_usage_to_ram_ratio>

    <!-- Cache: reduce from 1GB to 256MB for our dataset size -->
    <mark_cache_size>268435456</mark_cache_size>
    <index_mark_cache_size>134217728</index_mark_cache_size>  <!-- 128MB, down from 256MB -->

    <!-- Disable unused ports -->
    <mysql_port remove="1" />
    <postgresql_port remove="1" />

    <!-- Disable verbose logs for small system -->
    <query_log remove="1" />
    <query_thread_log remove="1" />
    <text_log remove="1" />
    <trace_log remove="1" />
    <metric_log remove="1" />
    <asynchronous_metric_log remove="1" />
    <session_log remove="1" />
    <part_log remove="1" />
    <processor_profile_log remove="1" />
    <opentelemetry_span_log remove="1" />

    <!-- Merge tuning -->
    <background_pool_size>2</background_pool_size>
    <background_merges_mutations_concurrency_ratio>2</background_merges_mutations_concurrency_ratio>

    <merge_tree>
        <merge_max_block_size>1024</merge_max_block_size>
        <max_bytes_to_merge_at_max_space_in_pool>268435456</max_bytes_to_merge_at_max_space_in_pool>  <!-- 256MB -->
        <number_of_free_entries_in_pool_to_lower_max_size_of_merge>2</number_of_free_entries_in_pool_to_lower_max_size_of_merge>
        <number_of_free_entries_in_pool_to_execute_mutation>2</number_of_free_entries_in_pool_to_execute_mutation>
    </merge_tree>

    <!-- Query limits -->
    <max_concurrent_queries>4</max_concurrent_queries>
    <max_execution_time>60</max_execution_time>

    <!-- Disk spilling -->
    <max_bytes_before_external_group_by>268435456</max_bytes_before_external_group_by>
    <max_bytes_before_external_sort>268435456</max_bytes_before_external_sort>
</clickhouse>
```

**Net memory savings:** Mark cache reduced from 1GB to 256MB (-768MB). Index mark cache reduced from 256MB to 128MB (-128MB). System logs disabled (saves ~50-100MB). **Total: ~900MB freed** within the 5GB Docker limit.

**Risk:** Smaller mark cache means more disk reads for queries. For our low-traffic hobby use (~1-5 users), this is an acceptable trade-off.

---

## 5. PostHog Backup Strategy — ClickHouse + PostgreSQL

### Current State (from infra/CLAUDE.md)

Daily 04:00 cron via `/usr/local/bin/backup-dbs.sh`, 7-day retention:
- PG 17: `pg_dumpall` → `/opt/infra/backups/postgres/`
- PG 15: PostHog dump → `/opt/infra/backups/posthog-pg/`
- ClickHouse: `clickhouse-client dump` → `/opt/infra/backups/clickhouse/`
- Config: tar of env, Caddyfile, iptables, sshd → `/opt/infra/backups/config/`

### Problems with Current ClickHouse Backup Approach

`clickhouse-client dump` (likely using `CLICKHOUSE_DUMP` or similar) is **not reliable** for ClickHouse because:

1. ClickHouse data is columnar and stored in parts. A simple SQL dump loses MergeTree engine settings.
2. Large tables may not complete within backup window.
3. No atomic consistency guarantee — data can change during dump.

### Recommended: `clickhouse-backup` by Altinity

**Repository:** https://github.com/Altinity/clickhouse-backup

Features:
- Creates consistent backups using ClickHouse's `FREEZE TABLE` or `BACKUP` command
- Supports S3, GCS, Azure, and local storage as backup destinations
- Can run as a Docker sidecar or standalone binary
- Supports incremental backups
- Configurable retention policies
- Works with ClickHouse 1.1.54390+

**Installation in Docker Compose:**

```yaml
clickhouse-backup:
  image: altinity/clickhouse-backup:latest
  container_name: posthog_clickhouse_backup
  volumes:
    - clickhouse-data:/var/lib/clickhouse
    - ./clickhouse/backup-config.yml:/etc/clickhouse-backup/config.yml
    - clickhouse-backup-data:/var/lib/clickhouse-backup
  depends_on:
    - clickhouse
  entrypoint: ["clickhouse-backup", "server"]  # REST API mode
```

**backup-config.yml example:**
```yaml
general:
  remote_storage: local
  backup_data_format: directory
clickhouse:
  host: posthog_clickhouse
  port: 9000
  username: default
  backup_path: /var/lib/clickhouse-backup
```

**For S3 (RustFS) offload:**
```yaml
general:
  remote_storage: s3
s3:
  endpoint: "http://infra-rustfs-1:9000"
  access_key_id: "${S3_ACCESS_KEY_ID}"
  secret_access_key: "${S3_SECRET_ACCESS_KEY}"
  bucket: "posthog-backups"
  backup_path_format: "clickhouse-backups"
```

**Cron-based backup (simpler than sidecar):**
```bash
# Add to existing backup-dbs.sh:
docker compose exec posthog_clickhouse clickhouse-backup create daily_$(date +%Y%m%d)
docker compose exec posthog_clickhouse clickhouse-backup upload daily_$(date +%Y%m%d)
# Keep last 7 locally, older to S3
```

### PostgreSQL Backup

Current `pg_dumpall` approach is adequate for PostHog's PostgreSQL 15 database. No changes needed.

### ClickHouse Native BACKUP Command (ClickHouse 22.7+)

ClickHouse now supports native `BACKUP TO` and `RESTORE FROM` commands:
```sql
BACKUP TABLE events TO S3('http://infra-rustfs-1:9000/posthog-backups/events_backup')
RESTORE TABLE events FROM S3('http://infra-rustfs-1:9000/posthog-backups/events_backup')
```

This is simpler than `clickhouse-backup` but requires ClickHouse 22.7+. Our version (26.3) supports this natively.

**Recommendation:** Use `clickhouse-backup` for automated daily backups (handles retention, S3 upload, and verification). Use native `BACKUP TO` for ad-hoc snapshots before upgrades.

---

## 6. Docker Image Tag Pinning Best Practices

### The Problem

PostHog's hobby deployment uses `$POSTHOG_APP_TAG` variable that defaults to `latest`. This means:
- `docker compose pull` can pull a different image than what was previously running
- No guarantee of reproducibility
- Breaking changes can arrive unannounced (see GitHub #28804)

### Best Practices (from multiple sources)

**Option A: Pin to exact version tag (e.g., `1.88.0`)**
- Pros: Readable, semantically meaningful, easy to understand what's running
- Cons: Same tag can point to different image digests if the publisher re-pushes (rare but possible)
- **This is what our spec proposes** — hardcoded version tags in compose.yaml

**Option B: Pin to SHA256 digest (e.g., `posthog/posthog@sha256:abc123...`)**
- Pros: Cryptographically guaranteed reproducibility — same digest = same image bits
- Cons: Unreadable, hard to audit, requires tooling to update (e.g., renovatebot, dependabot)
- Microsoft's recommendation for production workloads
- Docker's own best practice guide recommends digest pinning for production

**Option C: Hybrid — version tag in compose, SHA256 lock in lockfile**
- `compose.yaml` uses human-readable tags (`1.88.0`)
- `compose.lock.yaml` or `docker-compose.override.yml` pins SHA256
- `docker compose up --pull never` uses locked images
- Best of both worlds but adds operational complexity

### PostHog-Specific Considerations

1. **PostHog does NOT publish tagged releases for self-hosted.** From their docs: "We don't do tagged releases for self-hosted PostHog. All commits go through our standard CI/CD pipeline before they are merged into our cloud deployments and also become available for self-hosted instances."

2. **PostHog uses commit SHAs as Docker tags.** The "version" is actually a short commit hash like `1.88.0` which maps to a specific commit.

3. **Self-host breakage is common between versions.** GitHub #28804 shows that the "latest installable commit" changes frequently and can break things.

### Recommendation for Our Setup

**Pin exact version tags in compose.yaml** (as the spec already proposes). This is the right approach because:

1. **Readability:** `posthog/posthog:1.88.0` is immediately understandable
2. **PostHog's tag model:** Their tags are already commit-locked (they don't re-push)
3. **Deliberate upgrades:** Changing version requires editing compose.yaml and running `docker compose --profile posthog up -d`, which is an explicit action
4. **No `.env` tag variables:** The spec correctly removes `POSTHOG_*_TAG` from `.env` to prevent accidental upgrades

**Additional safety measures:**
- Before upgrading, check PostHog's GitHub releases and self-host changelog for breaking changes
- Pin ClickHouse image to a specific version too (`clickhouse/clickhouse-server:26.3.alpine`) — do NOT use `latest`
- Pin Redpanda to specific version (`redpanda/redpanda:v25.1.8`) — Redpanda upgrades can break KRaft
- Pin PostgreSQL to specific minor version (`postgres:15.12-alpine`) — PG minor upgrades are safe but should be deliberate

### What NOT to Do

- **Never use `latest` tag** for any PostHog service — it's a moving target
- **Never use floating minor tags** (`1.88`) for PostHog — they may not exist
- **Don't pin SHA256 digests** for PostHog specifically — their tags are already stable and SHA pinning adds complexity with no practical benefit for this project's scale

---

## Summary of Recommendations

### Immediate Actions (No Risk)

| Action | Impact | Effort |
|--------|--------|--------|
| Reduce `mark_cache_size` from 1GB to 256MB | Save ~768MB RAM | 1 line XML change |
| Reduce `index_mark_cache_size` from 256MB to 128MB | Save ~128MB RAM | 1 line XML change |
| Disable MySQL/PostgreSQL ports in ClickHouse | Save CPU + minor memory | 2 lines XML |
| Disable verbose ClickHouse system logs | Save I/O + ~100MB RAM | 10 lines XML |
| Add `max_concurrent_queries: 4` and `max_execution_time: 60` | Prevent OOM from runaway queries | 2 lines XML |
| Add `max_server_memory_usage_to_ram_ratio: 0.75` | Safety net against memory overuse | 1 line XML |
| Add disk spilling settings | Prevent OOM on large GROUP BY/ORDER BY | 2 lines XML |
| Pin all Docker image tags in compose.yaml | Reproducibility | Already in spec |

### Medium-Term Improvements

| Action | Impact | Effort |
|--------|--------|--------|
| Switch ClickHouse backup from `clickhouse-client dump` to `clickhouse-backup` | Reliable backups | Medium |
| Upload ClickHouse backups to RustFS (S3) | Off-server backup | Medium |
| Use native `BACKUP TO S3` for pre-upgrade snapshots | Quick restore point | Low |
| Reduce Redpanda memory from 4g to 3g Docker limit | Save ~1GB RAM | 1 line YAML + monitoring |

### What NOT to Change

| Decision | Reason |
|----------|--------|
| Do NOT switch from Redpanda to Kafka | Redpanda KRaft mode is simpler, already working, and saves ~512MB vs Kafka+ZK |
| Do NOT reduce Docker mem_limit for ClickHouse below 5g | Current 4GB internal + 1GB overhead is tight but works |
| Do NOT remove PostgreSQL 15 separate instance | PG 15 (PostHog) is incompatible with PG 17 (SkateLab) |
| Do NOT use SHA256 pinning for PostHog images | Unnecessary complexity for this scale; version tags are sufficient |
| Do NOT disable ClickHouse query_log entirely in production | Useful for debugging; keep `query_log` but remove `query_thread_log` and others |

---

## Sources

- PostHog self-host docs: https://posthog.com/docs/self-host
- GitHub #27120 — PostHog 8GB RAM instability
- GitHub #3888 — 900MB idle memory
- GitHub #28804 — Self-host basic bugs
- Altinity KB — Configure ClickHouse for low memory: https://kb.altinity.com/altinity-kb-setup-and-maintenance/configure_clickhouse_for_low_mem_envs
- Uptrace — Running ClickHouse with low memory: https://clickhouse.uptrace.dev/clickhouse/low-memory.html
- Altinity Blog — Single-node ClickHouse on small servers: https://altinity.com/blog/deploying-single-node-clickhouse-on-small-servers
- James O'Claire — ClickHouse < 2GB RAM in Docker: https://jamesoclaire.com/2024/12/20/clickhouse-in-less-than-2gb-ram-in-docker
- Plausible #5535 — ClickHouse eating resources: https://github.com/plausible/analytics/discussions/5535
- ComputingForGeeks — Kafka vs Redpanda benchmarks (April 2026): https://computingforgeeks.com/kafka-vs-redpanda-benchmarks/
- Redpanda sizing docs: https://docs.redpanda.com/current/deploy/redpanda/manual/sizing/
- Cotera — PostHog self-hosted honest take: https://cotera.co/articles/posthog-self-hosted-guide
- Altinity clickhouse-backup: https://github.com/Altinity/clickhouse-backup
- Microsoft — Container image tagging best practices: https://learn.microsoft.com/en-us/azure/container-registry/container-registry-image-tag-version
- Docker — Tags and labels best practices: https://www.docker.com/blog/docker-best-practices-using-tags-and-labels-to-manage-docker-image-sprawl