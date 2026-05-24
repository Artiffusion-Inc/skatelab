# Docker Compose Environment Variable Management: Research Findings

> Research date: 2026-05-24
> Context: SkateLab .env cleanup -- removing image tag vars, consolidating R2_*/RUSTFS_* duplicates, separating infra from app vars.

---

## 1. What Belongs in .env vs docker-compose.yml

### Core Principle: .env is for deployment-specific values, compose is for declarative infrastructure

**Docker official docs** (https://docs.docker.com/compose/how-tos/environment-variables/best-practices/) define four best practices:
1. Handle sensitive information securely (use Docker Secrets, not env vars, for secrets)
2. Understand environment variable precedence
3. Use specific environment files for different stages (dev/staging/prod)
4. Know interpolation syntax for dynamic configs

### What goes in .env (the project-level .env that Compose auto-reads)

| Category | Examples | Why |
|----------|----------|-----|
| **Secrets** | DB passwords, API keys, S3 credentials | Must differ per deployment, never committed |
| **Deployment-specific endpoints** | S3_ENDPOINT_URL, DATABASE_URL, REDIS_URL | Different per environment (local vs staging vs prod) |
| **Feature flags / toggles** | ENABLE_3D_LIFT=true, LOG_LEVEL=debug | Runtime behavior that changes per deployment |
| **Resource overrides** | DOCKER_WEB_PORT_FORWARD=127.0.0.1:8000 | Per-host port bindings |

### What stays in docker-compose.yml

| Category | Examples | Why |
|----------|----------|-----|
| **Image tags** (see section 2) | `image: postgres:15`, `image: rustfs/rustfs:latest` | Declarative, version-controlled |
| **Static port mappings** | `ports: ["5432:5432"]` | Infrastructure definition |
| **Volume mounts** | `volumes: [db_data:/var/lib/postgresql/data]` | Infrastructure definition |
| **Network definitions** | `networks: [backend]` | Infrastructure definition |
| **Service relationships** | `depends_on`, `healthcheck` | Infrastructure definition |
| **Default (non-secret) env values** | `POSTGRES_DB: skatelab`, `NODE_ENV: ${NODE_ENV:-production}` | Safe defaults with interpolation fallback |

### The `.env` vs `env_file` distinction (common confusion)

- **`.env`** (at project root): Used for **Compose variable interpolation** (`${VAR}`) in the compose file itself. Compose reads it automatically. These values are NOT automatically injected into containers.
- **`env_file:`** (attribute in compose): Loads variables **into the container's environment**. Does NOT participate in compose interpolation.

Source: https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/

**Key gotcha**: If you want a variable available both for compose interpolation AND inside a container, you need BOTH the `.env` file (for interpolation) and either `env_file:` or `environment:` (for container injection).

### Precedence (highest to lowest)

1. `docker compose run -e VAR=value` (CLI)
2. `environment:` attribute in compose (interpolated from shell/.env)
3. `environment:` attribute in compose (hardcoded value)
4. `env_file:` attribute in compose
5. Image `ENV` directive in Dockerfile

Source: https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/

---

## 2. Image Tags: Hardcode vs Environment Variable

### Industry consensus: Hardcode image tags in docker-compose.yml

**The strong consensus** across Docker community forums, Stack Overflow, and production guides is:

**Hardcode image tags in docker-compose.yml for infrastructure images** (databases, caches, object storage). Use environment variables for image tags only when you need to dynamically change them across deployments.

### When to hardcode

```yaml
# GOOD: infrastructure services with known-compatible versions
services:
  postgres:
    image: postgres:15-alpine    # pinned, version-controlled
  redis:
    image: redis:7-alpine        # pinned, version-controlled
  rustfs:
    image: rustfs/rustfs:latest  # or pin to specific tag
```

**Rationale** (from Nick Janetakis, DockerCon 21 speaker):
- Image tags are infrastructure declarations, not configuration
- They should be version-controlled in git alongside compose changes
- Changing an image tag is a deliberate infrastructure change that should go through code review
- `.env` is for values that change per-deployment, not per-release

Source: https://nickjanetakis.com/blog/best-practices-around-production-ready-web-apps-with-docker-compose

### When to use env vars for image tags

```yaml
# ACCEPTABLE: application images that change frequently across environments
services:
  app:
    image: myorg/app:${APP_TAG:-latest}  # dev uses latest, prod pins to release
```

**Only acceptable when**:
- The same compose file deploys to multiple environments with different image versions
- CI/CD pipelines inject the tag at deploy time
- The image is built from the same repo and changes every deploy (your own app)

### Concrete examples from mature projects

| Project | Approach | Image tag handling |
|---------|----------|-------------------|
| **Grafana** (github.com/grafana/grafana) | Hardcoded in compose | `image: grafana/grafana:latest` |
| **RustFS** (github.com/rustfs/rustfs) | Hardcoded in compose | `image: rustfs/rustfs:latest` |
| **PostHog** (github.com/PostHog/posthog) | Mixed: infra hardcoded, app via env | Infra pinned; PostHog app image uses `${POSTHOG_APP_TAG:-latest}` |
| **AutoGPT** (github.com/Significant-Gravitas/AutoGPT) | Env vars with `.env.example` | Platform compose uses `${VAR}` for all configurable values |

### Gotchas

1. **`image: ${TAG}` without default**: If the env var is unset, Compose fails with a cryptic error. Always use `${TAG:-fallback}`.
2. **Latest tag drift**: `image: rustfs/rustfs:latest` means the actual image can change between pulls. Pin to digest (`image: rustfs/rustfs@sha256:...`) for reproducibility in production.
3. **Multiple services, one tag var**: Using `POSTHOG_APP_TAG` for both the web and worker service is correct (same codebase, same version). But using one tag for unrelated services (e.g., PostHog + Kafka) is wrong.

### Recommendation for SkateLab

**Remove `POSTHOG_APP_TAG`, `POSTHOG_NODE_TAG`, `POSTHOG_RUST_TAG` from .env and hardcode in compose.** These are PostHog infrastructure images whose versions change only on upgrade -- a deliberate, reviewable action.

```yaml
# Before (env-dependent, fragile)
services:
  posthog:
    image: posthog/posthog:${POSTHOG_APP_TAG:-latest}

# After (hardcoded, version-controlled)
services:
  posthog:
    image: posthog/posthog:9d3f8bc  # pin to specific release
```

---

## 3. How Mature Projects Handle Env Vars in docker-compose.yml

### Pattern A: Single .env + .env.example (most common)

Used by: Nick Janetakis templates, AutoGPT, most small-to-medium projects.

```
repo/
  docker-compose.yml
  .env              # gitignored, contains real secrets
  .env.example      # committed, contains non-secret defaults with comments
```

`.env.example` pattern:
```bash
# Which environment is running? "development" or "production"
#export FLASK_ENV=production
#export NODE_ENV=production
export FLASK_ENV=development
export NODE_ENV=development

# Database (override for production)
DATABASE_URL=postgres://skatelab:skatelab@db:5432/skatelab

# Secrets -- set these in .env, never commit
# S3_ACCESS_KEY_ID=changeme
# S3_SECRET_ACCESS_KEY=changeme
```

Key insight from Nick Janetakis: **Comment out the production defaults, uncomment dev overrides.** This makes `.env.example` work as a dev quickstart while documenting what prod needs.

Source: https://nickjanetakis.com/blog/best-practices-around-production-ready-web-apps-with-docker-compose

### Pattern B: Multiple env files per environment

Used by: Larger projects with distinct dev/staging/prod configs.

```yaml
services:
  webapp:
    env_file:
      - path: ./default.env
        required: true
      - path: ./override.env
        required: false  # Compose 2.24+ feature
```

Or via CLI: `docker compose --env-file .env.prod up`

Source: https://oneuptime.com/blog/post/2026-01-25-docker-compose-environment-files/view

### Pattern C: Docker Compose Profiles (modern approach)

Instead of separate compose files, use profiles to activate dev-only or prod-only services:

```yaml
services:
  postgres:
    image: postgres:15
    profiles: ["dev"]  # only runs with --profile dev

  webapp:
    image: myapp:latest
    environment:
      - DB_HOST=${DB_HOST:-prod-db.internal}
```

Source: https://nickjanetakis.com/blog/docker-tip-94-docker-compose-v2-and-profiles-are-the-best-thing-ever

### Pattern D: YAML anchors for reducing duplication

```yaml
x-app: &default-app
  build:
    context: "."
  env_file:
    - ".env"
  restart: "${DOCKER_RESTART_POLICY:-unless-stopped}"

services:
  web:
    <<: *default-app
    ports:
      - "${DOCKER_WEB_PORT:-127.0.0.1:8000}:8000"
  worker:
    <<: *default-app
    command: celery -A app worker
```

Source: https://nickjanetakis.com/blog/best-practices-around-production-ready-web-apps-with-docker-compose

### Real-world .env.example patterns

**AutoGPT** (PR #9331): Moved hardcoded passwords in compose to `.env` with `${VAR}` interpolation. Reviewer caught: still had some hardcoded Redis passwords -- shows how easy it is to miss duplicates.

**Hashgraph Guardian** (docker-compose-production.yml): Separate compose file for production with hardcoded image tags, `.env` only for secrets and endpoints.

Source: https://github.com/Significant-Gravitas/AutoGPT/pull/9331

---

## 4. .env.example Template Patterns for Production

### Anatomy of a good .env.example

```bash
# =============================================================================
# SkateLab Docker Compose Environment Variables
# =============================================================================
# Copy this file to .env and fill in values marked <required>.
# Values with defaults work for local development.
# =============================================================================

# ---- Secrets (REQUIRED in production) ----
S3_ACCESS_KEY_ID=<required>
S3_SECRET_ACCESS_KEY=<required>
DATABASE_PASSWORD=<required>
JWT_SECRET=<required>

# ---- S3-compatible Storage ----
S3_ENDPOINT_URL=http://rustfs:9000       # RustFS internal, or https://<account>.r2.cloudflarestorage.com
S3_BUCKET_NAME=skatelab                   # Bucket name
S3_REGION=auto                            # Cloudflare R2 uses "auto"

# ---- Database ----
DATABASE_URL=postgres://skatelab:${DATABASE_PASSWORD}@db:5432/skatelab
# DATABASE_PORT=5432                       # Override if using external DB

# ---- Application ----
# NODE_ENV=production                      # Uncomment for production
# LOG_LEVEL=info                            # debug | info | warn | error

# ---- Docker Compose Interpolation ----
# These are used for ${VAR} substitution in docker-compose.yml
# DOCKER_WEB_PORT_FORWARD=127.0.0.1:8000  # Port binding override
```

### Best practices for .env.example

1. **Include every variable** the project uses, even if optional. Missing vars = silent failures.
2. **Mark required vs optional clearly**. `<required>` or comments explaining defaults.
3. **Provide sensible dev defaults** so `cp .env.example .env && docker compose up` works.
4. **Comment out production values** so devs see them but don't accidentally use them.
5. **Group by category**, not by service. A variable like `S3_ENDPOINT_URL` is used by multiple services.
6. **Never include real secrets**. Use placeholder values like `changeme` or `<required>`.

### Anti-patterns to avoid

1. **Duplicating vars across .env and compose `environment:` block** -- pick one location, not both.
2. **`.env` with 200+ lines and no grouping** -- becomes unmaintainable.
3. **Mixing infra vars (image tags, ports) with app vars (secrets, endpoints)** -- the exact problem SkateLab has now.
4. **No `.env.example` at all** -- new developers cannot bootstrap without tribal knowledge.

---

## 5. S3-Compatible Storage Env Var Naming Conventions

### The standard: AWS SDK naming (`AWS_*`)

The AWS SDKs and CLI standardized on these env vars for S3-compatible access:

| Variable | Purpose | Used by |
|----------|---------|---------|
| `AWS_ACCESS_KEY_ID` | Access key (username equivalent) | All AWS SDKs, CLI |
| `AWS_SECRET_ACCESS_KEY` | Secret key (password equivalent) | All AWS SDKs, CLI |
| `AWS_ENDPOINT_URL` | Custom endpoint for S3-compatible storage | AWS CLI v2, boto3, AWS SDK Rust |
| `AWS_ENDPOINT_URL_S3` | Service-specific endpoint override | AWS CLI v2 |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | Region | All AWS SDKs, CLI |

Source: https://docs.aws.amazon.com/sdkref/latest/guide/feature-ss-endpoints.html
Source: https://aws.amazon.com/blogs/security/a-new-and-standardized-way-to-manage-credentials-in-the-aws-sdks

### MinIO naming convention (`MINIO_*`)

MinIO uses its own prefixed env vars for the **server** configuration:

| Variable | Purpose |
|----------|---------|
| `MINIO_ROOT_USER` | Root access key (replaces old `MINIO_ACCESS_KEY`) |
| `MINIO_ROOT_PASSWORD` | Root secret key (replaces old `MINIO_SECRET_KEY`) |
| `MINIO_SERVER_URL` | External URL for the MinIO server |

**Key insight**: MinIO uses `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` for **server-side** auth config, while clients connecting to MinIO use standard `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`.

Source: https://docs.min.io/aistor/reference/aistor-server/settings/root-credentials
Source: https://github.com/minio/minio/issues/18665

### RustFS naming convention (`RUSTFS_*`)

RustFS mirrors MinIO's naming convention exactly (it is a drop-in MinIO replacement):

| Variable | Purpose |
|----------|---------|
| `RUSTFS_ACCESS_KEY` | Root access key (server config) |
| `RUSTFS_SECRET_KEY` | Root secret key (server config) |
| `RUSTFS_CONSOLE_ENABLE` | Enable web console |
| `RUSTFS_SERVER_DOMAINS` | Server domain names |
| `RUSTFS_ADDRESS` | Listen address |
| `RUSTFS_TLS_PATH` | TLS certificate path |

Source: https://docs.rustfs.com/installation/docker

### SeaweedFS naming convention

SeaweedFS does NOT have dedicated env vars for S3 credentials. Instead:
- Server-side: uses a JSON config file or command-line flags
- Client-side: uses standard `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
- Railway template uses: `S3_ACCESS_KEY` / `S3_SECRET_KEY` (non-standard)

Source: https://github.com/seaweedfs/seaweedfs/issues/7311
Source: https://railway.com/deploy/seaweedfs

### Summary: Two naming worlds

| Context | Convention | Example |
|---------|-----------|---------|
| **Server-side** (configuring the storage server) | Vendor-prefixed | `MINIO_ROOT_USER`, `RUSTFS_ACCESS_KEY` |
| **Client-side** (connecting to S3-compatible storage) | AWS standard | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL` |

### Recommendation for SkateLab: Use `S3_*` for client-side abstraction

The current duplication (`R2_ACCESS_KEY_ID` and `RUSTFS_ACCESS_KEY_ID` for the same credentials) arises from mixing server-side and client-side naming. The fix:

**Consolidate to a generic `S3_*` prefix for the APPLICATION's S3 client config** (what the backend uses to connect to storage), separate from the **storage server's own config** (what the RustFS/MinIO container uses for its root credentials).

```bash
# .env -- Application S3 client configuration (backend reads these)
S3_ENDPOINT_URL=http://rustfs:9000
S3_ACCESS_KEY_ID=changeme
S3_SECRET_ACCESS_KEY=changeme
S3_BUCKET_NAME=skatelab
S3_REGION=auto
```

```yaml
# docker-compose.yml -- RustFS server uses its own vars
services:
  rustfs:
    image: rustfs/rustfs:latest
    environment:
      RUSTFS_ACCESS_KEY: ${S3_ACCESS_KEY_ID}    # map from app var
      RUSTFS_SECRET_KEY: ${S3_SECRET_ACCESS_KEY}
      RUSTFS_CONSOLE_ENABLE: "true"
```

**Why `S3_*` and not `AWS_*`**: SkateLab is not using AWS. The `S3_` prefix signals "S3-compatible protocol" without implying a specific vendor. This is the convention used by SeaweedFS Railway templates and several S3 client libraries. The `AWS_*` prefix is misleading when the endpoint is Cloudflare R2 or RustFS.

**Alternative if you want strict standards compliance**: Use `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_ENDPOINT_URL`. Every S3-compatible client library (boto3, aws-sdk-go, minio-py) supports these natively. But the prefix "AWS" can confuse developers who think it implies AWS usage.

---

## Summary of Recommendations for SkateLab

| Current Problem | Recommended Fix | Rationale |
|-----------------|----------------|-----------|
| `POSTHOG_APP_TAG`, `POSTHOG_NODE_TAG`, `POSTHOG_RUST_TAG` in .env | Remove from .env, hardcode in compose | Image tags are infrastructure declarations, not deployment config |
| Duplicate `R2_*` and `RUSTFS_*` vars for same S3 backend | Consolidate to `S3_*` prefix (S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_BUCKET_NAME, S3_REGION) | Single source of truth; map to server-specific vars in compose |
| Mix of infra and app vars in one .env | Group .env by category with section headers; consider separate env_file for infrastructure-only services | Reduces cognitive load, easier to audit |
| No .env.example | Create .env.example with defaults, required markers, and comments | Enables new developer onboarding and CI bootstrapping |

### Proposed .env structure

```bash
# ==== Secrets (REQUIRED) ====
S3_ACCESS_KEY_ID=changeme
S3_SECRET_ACCESS_KEY=changeme
DATABASE_PASSWORD=changeme
JWT_SECRET=changeme

# ==== S3-compatible Storage ====
S3_ENDPOINT_URL=http://rustfs:9000
S3_BUCKET_NAME=skatelab
S3_REGION=auto

# ==== Database ====
DATABASE_URL=postgres://skatelab:${DATABASE_PASSWORD}@db:5432/skatelab

# ==== Application (dev defaults, override for prod) ====
# NODE_ENV=production
# LOG_LEVEL=info

# ==== Docker Compose Interpolation ====
# DOCKER_WEB_PORT=127.0.0.1:8000
```

---

## Sources

- Docker official: Environment variable best practices -- https://docs.docker.com/compose/how-tos/environment-variables/best-practices/
- Docker official: Setting environment variables -- https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/
- Docker official: Environment variable precedence -- https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/
- Nick Janetakis: Best Practices Around Production Ready Web Apps with Docker Compose -- https://nickjanetakis.com/blog/best-practices-around-production-ready-web-apps-with-docker-compose
- Wallace Freitas: 10 Best Practices for Writing Maintainable Docker Compose Files -- https://dev.to/wallacefreitas/10-best-practices-for-writing-maintainable-docker-compose-files-4ca2
- Configu: 4 Ways to Set Docker Compose Environment Variables -- https://configu.com/blog/4-ways-to-set-docker-compose-environment-variables
- OneUptime: How to Use Docker Compose Environment Files -- https://oneuptime.com/blog/post/2026-01-25-docker-compose-environment-files/view
- Docker Community Forums: Best practice for storing env variables -- https://forums.docker.com/t/what-is-the-best-practice-for-storing-environment-variables-in-a-docker-project/144702
- Docker Community Forums: Runtime env var requirements in build stage -- https://forums.docker.com/t/runtime-environment-variable-requirements-in-build-stage/132427
- vSupalov: Docker ARG, ENV and .env Complete Guide -- https://vsupalov.com/docker-arg-env-variable-guide
- RustFS Docker installation docs -- https://docs.rustfs.com/installation/docker
- MinIO Root Access Settings docs -- https://docs.min.io/aistor/reference/aistor-server/settings/root-credentials
- AWS: Service-specific endpoints -- https://docs.aws.amazon.com/sdkref/latest/guide/feature-ss-endpoints.html
- AWS: Standardized credential management -- https://aws.amazon.com/blogs/security/a-new-and-standardized-way-to-manage-credentials-in-the-aws-sdks
- SeaweedFS GitHub: S3 env var issue -- https://github.com/seaweedfs/seaweedfs/issues/7311
- AutoGPT PR #9331: .env vars in docker-compose -- https://github.com/Significant-Gravitas/AutoGPT/pull/9331
