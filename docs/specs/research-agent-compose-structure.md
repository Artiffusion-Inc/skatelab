# Docker Compose Organizational Patterns: Research Findings

> Research for `2026-05-24-infra-cleanup-design.md` — infra/prod split, PostHog profiles, shared network, DNS resolution, memory optimization.

---

## 1. How Others Structure PostHog Docker Compose

### Official PostHog Structure: Multi-File with `extends`

PostHog's own repo uses a **multi-file architecture** with `extends` inheritance:

| File | Purpose |
|------|---------|
| `docker-compose.base.yml` | Common service definitions (proxy, db, redis, clickhouse, kafka, etc.) |
| `docker-compose.hobby.yml` | Self-hosted single-server — extends base, adds all services including Temporal, SeaweedFS, object storage |
| `docker-compose.dev.yml` | Local development — extends base + profiles overlay, uses `extra_hosts: host-gateway` |
| `docker-compose.dev-minimal.yml` | Lightweight dev — extends base, removes Temporal, Kafka UI, Jaeger, OTEL collector |
| `docker-compose.dev-full.yml` | Full dev stack — everything including observability |
| `docker-compose.profiles.yml` | Legacy profile overlay (gates services by profile) |

**Key patterns from PostHog:**

1. **`extends` for DRY** — Every file extends `docker-compose.base.yml` for shared service definitions. Override specifics (volumes, env, ports) in each variant.
2. **No profiles in the hobby file** — `docker-compose.hobby.yml` starts everything unconditionally. Profiles are only used in `dev` variants.
3. **Hobby = 15+ services** — db, redis7, clickhouse, zookeeper, kafka, worker, web, plugins, ingestion-general, ingestion-sessionreplay, recording-api, ingestion-error-tracking, ingestion-logs, ingestion-traces, proxy, objectstorage, seaweedfs, personhog-router, temporal.
4. **Dev-minimal drops** — Temporal, Kafka UI, Jaeger, OTEL collector. Still has: proxy, db, redis, redis7, clickhouse, zookeeper, kafka, objectstorage, capture, feature-flags.
5. **Kafka + Zookeeper** — Hobby still uses Kafka (not Redpanda). Redpanda is used in dev-minimal via `redpanda-data` volume but the base file uses Bitnami Kafka.

### Community Patterns

From the DEV Community debugging article and other sources:

- **Most self-hosters use a single `docker-compose.yml`** — they clone PostHog's repo, copy `docker-compose.hobby.yml`, and modify. No profiles, no multi-file.
- **The `selfhog` tool** (npm package) deploys a single modified compose file with all gotchas documented inline.
- **Multiple instances on same VM** — Docker Community Forums post reports port conflicts and blank pages when running multiple PostHog instances. The solution requires careful port remapping and separate networks per instance.
- **PostHog explicitly says**: Docker Compose is for "evaluation stage" only. Production = Kubernetes (now sunset) or Cloud.

### Recommendation for Our Spec

The spec's approach (profiles `[posthog]` in infra compose) is sound and matches PostHog's own dev pattern. However:

- **Gotcha**: PostHog's hobby compose has ~15 services. Putting all of them behind a single `posthog` profile is correct, but the profile only controls *whether they start*. The service definitions are still parsed and validated by `docker compose config`.
- **Gotcha**: PostHog uses `extends` heavily. If we copy their hobby file into our infra compose, we lose the `extends` inheritance (since we don't have `docker-compose.base.yml`). We'd need to inline the base definitions or maintain our own base file.

---

## 2. Docker Compose Profiles vs Separate Compose Files

### Profiles

**How they work:**
- Services with `profiles: [...]` only start when that profile is active
- Services without `profiles` always start (core services)
- Activate via `--profile posthog` flag or `COMPOSE_PROFILES=posthog` env var
- Running `docker compose run <service-with-profile>` auto-activates that service's profile

**Strengths:**
- Single file = single source of truth. No file-switching.
- `COMPOSE_PROFILES` env var means no command-line flags needed on servers.
- Dependencies work: if profile-gated service `depends_on` a core service, the core service starts. If core service `depends_on` a profile-gated service with `required: false`, it's ignored.
- Implicit activation: `docker compose run posthog_web` works without `--profile posthog`.

**Weaknesses:**
- **v2.19 breaking change**: `depends_on` on profile-gated services became mandatory by default. Fixed in v2.20.2+ with explicit `required: true/false`.
- **No per-profile environment variables**: You can't set different env vars for the same service depending on which profile activated it. Workaround: define two services (e.g., `postgres-dev` and `postgres-prod`) with different profiles.
- **All services are parsed** even when not started. Validation errors in profile-gated services block `docker compose config`.
- **No `docker compose --profile` in systemd units** without `Environment=COMPOSE_PROFILES=...` in the unit file.

### Separate Compose Files

**How they work:**
- `docker compose -f compose.yaml -f compose.prod.yaml up` merges files
- Or separate `docker compose` invocations in different directories
- Each file is a standalone project (different network, different volume namespace)

**Strengths:**
- Complete isolation between stacks (networks, volumes, lifecycle)
- Can be deployed/updated independently
- No validation bleed between stacks
- Clear ownership: infra team owns compose.yaml, app team owns compose.prod.yaml

**Weaknesses:**
- No shared service discovery by default (need external network)
- Duplicate service definitions if both stacks need the same base config
- `docker compose -f a -f b` merging has precedence rules that can be confusing
- Two separate `docker compose up` commands to start everything

### Decision Matrix

| Criterion | Profiles | Separate Files |
|-----------|----------|----------------|
| Services share a network | Yes (auto) | Only with external network |
| Independent lifecycle | No (same project) | Yes (different projects) |
| Single command to start all | Yes (`--profile`) | No (two `up` commands) |
| Validation isolation | No | Yes |
| Per-service env variation | Hard | Easy |
| DRY across stacks | Easy (same file) | Need `extends` or duplication |
| Systemd unit simplicity | One unit | Two units |
| `docker compose ps` scope | All services | Per-project only |

### Recommendation for Our Spec

**Use both**: Separate files (infra + prod) for lifecycle isolation, profiles within infra for optional services (PostHog). This is exactly what the spec proposes and it's the right call.

- `compose.yaml` (infra) — always-on core services (postgres, valkey, caddy, rustfs) + profile-gated PostHog
- `compose.prod.yaml` (prod) — SkateLab app, deployed independently

**Profile activation on the server**: Set `COMPOSE_PROFILES=posthog` in the `.env` file (or systemd unit `Environment=`) on the Hetzner server. For local dev, don't set it — PostHog won't start locally.

**Important**: Use `required: false` on any `depends_on` that crosses profile boundaries in the infra compose. Docker Compose v2.20.2+ supports this explicitly.

---

## 3. Single Server, Multiple Stacks, Shared Network

### How Docker DNS Works Across Stacks

**Default behavior**: Each compose project creates its own `<project-name>_default` network. Containers in project A cannot resolve containers in project B by service name.

**Shared network pattern** (recommended for our setup):

1. **Create the network in one compose file** (the "owner"):
   ```yaml
   # compose.yaml (infra)
   networks:
     app_network:
       name: infra_app_network  # explicit name so prod can reference it
   ```

2. **Reference as external in the other**:
   ```yaml
   # compose.prod.yaml
   networks:
     app_network:
       name: infra_app_network
       external: true
   ```

3. **Attach services to the shared network**:
   ```yaml
   services:
     backend:
       networks:
         - app_network
   ```

**DNS resolution rules on a shared network:**

| Resolution Method | Works? | Notes |
|-------------------|--------|-------|
| Service name (`postgres`) | Yes, within same project | Docker DNS resolves within the project's default network |
| Service name (`postgres`) | No, across projects | Different projects = different default networks |
| Service name on shared network | Yes | Both containers on `infra_app_network` can resolve by service name |
| `<project>-<service>-1` (container name) | Yes | Always works on any shared network |
| `container_name` (custom) | Yes | Works on any shared network |

**Key insight from the Silvenga blog**: On user-created bridge networks (like our shared `infra_app_network`), container name resolution just works. No limitations like the default `bridge` network.

**Key insight from the differentpla.net blog**: Cross-project DNS uses the pattern `<service>.<network>`. E.g., `nginx.nginx` means service `nginx` on network `nginx`. But for simple setups, just the service name works when both containers share the network.

### Pre-create vs Define-in-Compose

**Option A: Define in compose.yaml, reference as external in compose.prod.yaml**
- Network lifecycle tied to infra stack: `docker compose -f compose.yaml down` destroys the network
- If prod is still running, it loses connectivity
- Simpler: only one file "owns" the network definition

**Option B: Pre-create with `docker network create`**
- Network survives both stacks going down
- Extra manual step during initial setup
- More resilient: accidental `down` of one stack doesn't kill the network

**Recommendation for our spec**: Option A (define in compose.yaml) is fine because:
1. Infra is always started before prod
2. If infra goes down, prod loses DB/Valkey anyway — the network being gone is the least of the problems
3. Document the dependency: always start infra first, stop prod first

**Gotcha**: If you `docker compose down` the infra stack while prod is running, Docker will refuse to remove the network because it's in use. This is a safety feature, not a bug.

### The Default Network Problem

Even with a shared network, each compose project still creates its own `<project>_default` network. This means:

- A service in prod is on TWO networks: `prod_default` and `infra_app_network`
- A service in infra is on TWO networks: `infra_default` and `infra_app_network`
- DNS resolution works on ALL attached networks

**You can suppress the default network** if you want:
```yaml
networks:
  default:  # suppress auto-creation
    driver: none
```

But this is usually unnecessary — the extra default network doesn't hurt.

---

## 4. Docker Compose Project Naming and Container Resolution

### How Project Names Work

- Default: directory name containing the compose file
- Override: `COMPOSE_PROJECT_NAME` env var or `--project-name` flag or top-level `name:` in compose file
- Affects: network names (`<project>_default`), volume names (`<project>_data`), container names (`<project>-<service>-1`)

### Container Name Format

```
<project>-<service>-<number>
```

Examples:
- `infra-postgres-1` (project=infra, service=postgres)
- `skatelab-backend-1` (project=skatelab, service=backend)
- `infra-valkey-1` (project=infra, service=valkey)

### DNS Resolution Across Projects on Shared Network

When `infra-postgres-1` and `skatelab-backend-1` share `infra_app_network`:

| From backend container | Resolves to | Method |
|------------------------|-------------|--------|
| `postgres` | infra-postgres-1 | Service name on shared network |
| `infra-postgres-1` | infra-postgres-1 | Container name on shared network |
| `valkey` | infra-valkey-1 | Service name on shared network |

**This is the key design point**: When both stacks share `infra_app_network`, the prod backend can reach infra's postgres simply as `postgres` (the Docker Compose service name). No need for container names or IPs.

**Gotcha: name collisions**. If both stacks define a service called `postgres`, they'll collide on the shared network. The second service to start will register and shadow the first. Solution: use unique service names across stacks (e.g., `postgres` in infra, `postgres-exporter` in prod if needed).

**Gotcha: `container_name` conflicts**. If you set explicit `container_name:` in compose files, two stacks cannot have the same container name. Don't set `container_name` for services on the shared network — let Docker auto-generate the `<project>-<service>-<number>` pattern.

### Recommendation for Our Spec

1. Set explicit `name:` at the top of each compose file:
   ```yaml
   # compose.yaml
   name: infra  # explicit project name
   ```

   ```yaml
   # compose.prod.yaml
   name: skatelab  # explicit project name
   ```

2. Do NOT set `container_name` on any service that participates in the shared network.

3. Prod services reference infra services by their **compose service name** (e.g., `postgres`, `valkey`), which resolves via Docker DNS on `infra_app_network`.

4. The `DATABASE_URL` in prod should use `postgres` (not `infra-postgres-1`), because service name is the stable identifier.

---

## 5. PostHog ClickHouse/Kafka/Redpanda Memory Optimization

### Official Requirements

PostHog's hobby install script warns: "You REALLY need 8GB or more of memory to run this stack." Official docs say 4 vCPU + 16GB RAM minimum.

### Memory Footprint by Service (Estimated)

Based on the hobby compose file and community reports:

| Service | Container | Est. RAM |
|---------|-----------|----------|
| PostgreSQL | `postgres:15-alpine` | 256–512 MB |
| Redis 7 | `redis:7-alpine` | 64–128 MB |
| ClickHouse | `clickhouse/clickhouse-server` | 1–4 GB (depends on data) |
| Kafka + Zookeeper | `bitnami/kafka` + `bitnami/zookeeper` | 512 MB – 2 GB |
| PostHog web | `posthog/posthog` | 512 MB – 1 GB |
| PostHog worker | `posthog/posthog` | 512 MB – 1 GB |
| PostHog plugins | `posthog/posthog-node` | 256–512 MB |
| Ingestion services (5x) | `posthog/posthog-node` | 256 MB each = 1.3 GB total |
| Caddy (proxy) | `caddy` | 32–64 MB |
| Object storage (MinIO/SeaweedFS) | `seaweedfs` | 256–512 MB |
| Temporal | `temporal` | 512 MB – 1 GB |
| **Total (hobby)** | | **~6–12 GB** |

### Redpanda vs Kafka

PostHog's dev-minimal file uses Redpanda (single binary, no Zookeeper). This saves ~512 MB of RAM and simplifies the stack.

**For our 62 GB server with ~30+ services**: Kafka + Zookeeper overhead is acceptable. But Redpanda is worth considering for the simpler operational model (no Zookeeper, no JVM tuning).

### ClickHouse Memory Tuning

ClickHouse's own docs say: "You can use ClickHouse in a system with as low as 2 GB RAM, but these setups require additional tuning and can only ingest at a low rate."

Key tuning parameters (from PostHog's dev config):
```xml
<!-- config.d/dev-memory.xml -->
<clickhouse>
    <max_memory_usage>2000000000</max_memory_usage>  <!-- 2 GB per query -->
    <max_bytes_ratio_before_external_group_by>0.5</max_bytes_ratio_before_external_group_by>
</clickhouse>
```

For a shared server, limit ClickHouse to 4 GB max:
```xml
<max_memory_usage>4000000000</max_memory_usage>
```

### Lightweight PostHog Alternatives / Trimming

If memory is tight, the PostHog stack can be trimmed:

| What to cut | How | RAM saved |
|-------------|-----|-----------|
| Zookeeper | Use Redpanda instead of Kafka | ~256 MB |
| Temporal | Only needed for async migrations; disable if you don't need them | ~1 GB |
| SeaweedFS | Use shared RustFS/MinIO instead | ~512 MB |
| 5x ingestion services | Combine or reduce replicas | ~500 MB |
| `plugins: false` | Disable plugin server via env var | ~256 MB |

**Absolute minimum PostHog stack** (for low traffic evaluation):
- PostgreSQL, Redis, ClickHouse, Kafka (or Redpanda), web, worker, Caddy
- ~3–4 GB total
- No Temporal, no SeaweedFS, no plugin server, single ingestion service

### Our Server Context: 62 GB RAM, ~30+ Services

With 62 GB total and ~30+ services, PostHog's 8–12 GB footprint is manageable but significant (~15–20% of total RAM). Recommendations:

1. **Set memory limits** on all PostHog services in compose:
   ```yaml
   clickhouse:
     deploy:
       resources:
         limits:
           memory: 4G
   kafka:
     deploy:
       resources:
         limits:
           memory: 1G
   ```

2. **Use Redpanda instead of Kafka+Zookeeper** if starting fresh. Single container, no JVM, no Zookeeper.

3. **Share PostgreSQL** — Use the infra PostgreSQL for both PostHog and SkateLab (different databases). PostHog's `db` service can point to `postgres` (the infra service) instead of its own container. This removes one more container.

4. **Skip SeaweedFS** — Use RustFS (already in infra) as PostHog's object storage backend. Set `OBJECT_STORAGE_ENDPOINT=http://infra-rustfs-1:9000`.

5. **Consider `COMPOSE_PROFILES=posthog` only on the Hetzner server**. Never set it locally — local dev doesn't need PostHog.

---

## Summary: Recommendations for the Spec

| Topic | Recommendation | Rationale |
|-------|---------------|-----------|
| **Profiles vs files** | Both: separate files (infra/prod) + profiles within infra | Lifecycle isolation for infra/prod; profiles for optional PostHog |
| **Shared network** | Define `infra_app_network` in `compose.yaml`, reference as external in `compose.prod.yaml` | Infra owns the network; prod depends on infra anyway |
| **Project naming** | Set `name: infra` and `name: skatelab` explicitly in compose files | Avoids directory-name ambiguity; container names become predictable |
| **DNS resolution** | Prod services use infra service names (`postgres`, `valkey`) on shared network | Docker DNS resolves by service name on shared networks |
| **No `container_name`** | Let Docker auto-name containers `<project>-<service>-<number>` | Avoids name collisions; compatible with scaling |
| **Profile activation** | `COMPOSE_PROFILES=posthog` in `.env` on Hetzner server only | Local dev never starts PostHog |
| **`depends_on` with profiles** | Use `required: false` on cross-profile dependencies | Supported in Docker Compose v2.20.2+ |
| **PostHog memory** | Set `deploy.resources.limits.memory` on all PostHog services | Prevents ClickHouse/Kafka from consuming all RAM |
| **Kafka vs Redpanda** | Redpanda preferred (single binary, no Zookeeper) | Saves ~256 MB, simpler ops |
| **Share infra PostgreSQL** | PostHog uses infra's `postgres` service (separate DB) | Removes one container, reduces memory |
| **Share infra RustFS** | PostHog object storage uses RustFS, not its own SeaweedFS | Removes another container |
| **PostHog startup** | Expect ~12 min first boot; ~5 min subsequent | Document in CLAUDE.md for operational awareness |

---

## References

- [Docker Docs: Using profiles with Compose](https://docs.docker.com/compose/how-tos/profiles)
- [Docker Docs: Networking in Compose](https://docs.docker.com/compose/how-tos/networking)
- [Docker Docs: Networks reference](https://docs.docker.com/reference/compose-file/networks)
- [Nick Janetakis: Docker Compose v2 and Profiles Are the Best Thing Ever](https://nickjanetakis.com/blog/docker-tip-94-docker-compose-v2-and-profiles-are-the-best-thing-ever)
- [Nick Janetakis: Optional depends_on with Docker Compose v2.20.2+](https://nickjanetakis.com/blog/optional-depends-on-with-docker-compose-v2-20-2)
- [Silvenga: Multiple Docker Compose's in a Single Network](https://silvenga.com/posts/multiple-docker-compose-single-network)
- [differentpla.net: Sharing networks between multiple docker compose projects](http://blog.differentpla.net/blog/2025/03/30/docker-compose-shared-networks)
- [Stack Overflow: Communication between multiple docker-compose projects](https://stackoverflow.com/questions/38088279/communication-between-multiple-docker-compose-projects)
- [PostHog: docker-compose.hobby.yml](https://raw.githubusercontent.com/PostHog/posthog/HEAD/docker-compose.hobby.yml)
- [PostHog: docker-compose.dev-minimal.yml](https://github.com/PostHog/posthog/blob/080e8e76b95d006c87ea3364020960ebcd773b4d/docker-compose.dev-minimal.yml)
- [PostHog: docker-compose.base.yml](https://github.com/PostHog/posthog-foss/blob/master/docker-compose.base.yml)
- [DEV Community: I Spent 12 Hours Debugging PostHog Self-Hosting](https://dev.to/ismailmirza/i-spent-12-hours-debugging-posthog-self-hosting-so-you-dont-have-to-pb0)
- [Cotera: PostHog Self-Hosted: Worth the Ops Overhead?](https://cotera.co/articles/posthog-self-hosted-guide)
- [Optiblack: Guide to Self-Hosting PostHog on AWS EC2](https://optiblack.com/insights/guide-to-self-hosting-posthog-on-aws-ec2)
- [Compose Spec: Allow depends_on to be optional (Issue #274)](https://github.com/compose-spec/compose-spec/issues/274)
- [Hacker News: Docker Compose best practices for dev and prod](https://news.ycombinator.com/item?id=32484008)
- [Reddit: Multiple Compose Files vs Profiles](https://www.reddit.com/r/docker/comments/1oj2el5/multiple_compose_files_vs_profiles_in_1_compose)
- [IT Playground: Container names and docker-compose](https://blog.it-playground.eu/container-names-docker-compose)
- [Server Fault: Connection between two docker containers of two stacks](https://serverfault.com/questions/935701/connection-between-two-docker-containers-of-two-stacks)
