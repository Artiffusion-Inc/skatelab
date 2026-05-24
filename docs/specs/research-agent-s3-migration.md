# S3 Migration Research: R2 to RustFS

**Date:** 2026-05-24  
**Purpose:** Feed into design review for infra cleanup spec (R2 → S3 rename, RustFS consolidation)

---

## 1. Cloudflare R2 to Self-Hosted S3 Migration Patterns

### 1.1 General Migration Strategy

All sources agree: migrating from R2/cloud S3 to a self-hosted S3-compatible backend is primarily a **configuration change** — swap `endpoint_url` and credentials. The boto3/aiobotocore client code stays identical because all these backends implement the S3 API.

Key migration steps:
1. **Deploy self-hosted S3 backend** (RustFS/MinIO) alongside R2
2. **Copy existing data** using `rclone sync` or S3-to-S3 copy
3. **Switch endpoint URL and credentials** in application config
4. **Verify** with integration tests
5. **Decommission** R2 bucket

**rclone** is the universally recommended tool for data migration. Cloudflare even provides "R2 Super Slurper" for bulk migration in the other direction (S3 → R2).

### 1.2 Presigned URL Gotchas

This is the **most critical migration concern**:

| Concern | R2 Behavior | RustFS/MinIO Behavior | Impact |
|---------|-------------|----------------------|--------|
| Presigned URLs work only on S3 API domain | `.r2.cloudflarestorage.com` endpoints only; **cannot** be used with custom domains | Works on the configured endpoint URL directly | R2 presigned URLs contain the account ID; RustFS URLs contain your domain |
| Custom domains | R2 custom domains are **read-only public CDN**; presigned URLs **don't work** on custom domains | Not applicable — RustFS serves presigned URLs from its own endpoint | If SkateLab uses presigned URLs with R2 custom domains, this is already broken |
| Signature version | SigV4 | SigV4 (configurable) | Both use SigV4 by default — compatible |
| Region parameter | R2 requires `region_name="auto"` | RustFS/MinIO typically use `region_name="us-east-1"` or custom | **Must update** `region_name` from `"auto"` to appropriate value |

**SkateLab impact:** The current code uses `region_name="auto"` (R2 convention). Must change to `us-east-1` or configure RustFS region. This is a **breaking change** if not updated.

### 1.3 R2 → Self-Hosted: Key Differences

| Aspect | Cloudflare R2 | RustFS / MinIO |
|--------|---------------|----------------|
| Egress fees | Zero (included) | Zero (self-hosted) |
| Authentication | S3-compatible (access key ID + secret) | S3-compatible (access key + secret) |
| Endpoint format | `https://<account_id>.r2.cloudflarestorage.com` | `http://<host>:9000` or `https://s3.yourdomain.com` |
| Console | Cloudflare dashboard | Built-in web console (RustFS: `:9001`) |
| Path-style vs virtual-hosted | Supports both | Path-style by default; virtual-hosted needs DNS config |
| CORS | Cloudflare dashboard config | RustFS/MinIO config file or bucket policy |
| Object lock | Supported | RustFS: supported (MinIO: AGPL-restricted) |
| Versioning | Supported | Supported |
| Server-side encryption | Supported | RustFS: via RustyVault; MinIO: supported |

---

## 2. RustFS vs MinIO: Self-Hosted S3 Comparison

### 2.1 RustFS

- **License:** Apache 2.0 (commercial-friendly, no AGPL restrictions)
- **Language:** Rust (memory-safe, high performance)
- **S3 API Compatibility:** Claims 100% S3 protocol compatible
- **Docker:** Available as `rustfs/rustfs:latest`, ports 9000 (S3 API) + 9001 (console)
- **Performance:** Claims 2.3x faster than MinIO for 4KB object payloads
- **Status:** Alpha (1.0.0-alpha.89 as of March 2026), 3,048+ commits, 23k+ GitHub stars
- **Migration from MinIO:** Supports in-place binary replacement (drop-in for single-node MinIO)

**RustFS docker-compose-simple.yml** (from official repo):
```yaml
services:
  rustfs:
    image: rustfs/rustfs:latest
    container_name: rustfs-server
    ports:
      - "9000:9000"   # S3 API port
      - "9001:9001"   # Console port
    environment:
      - RUSTFS_VOLUMES=/data/rustfs{0...3}
      - RUSTFS_ADDRESS=0.0.0.0:9000
      - RUSTFS_CONSOLE_ADDRESS=0.0.0.0:9001
      - RUSTFS_CONSOLE_ENABLE=true
      - RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS=*
      - RUSTFS_ACCESS_KEY=rustfsadmin    # CHANGEME
      - RUSTFS_SECRET_KEY=rustfsadmin    # CHANGEME
      - RUSTFS_OBS_LOGGER_LEVEL=info
    volumes:
      - rustfs_data_0:/data/rustfs0
      - rustfs_data_1:/data/rustfs1
      - rustfs_data_2:/data/rustfs2
      - rustfs_data_3:/data/rustfs3
```

**RustFS env vars** use `RUSTFS_` prefix:
- `RUSTFS_ACCESS_KEY` — root access key
- `RUSTFS_SECRET_KEY` — root secret key
- `RUSTFS_ADDRESS` — S3 API bind address
- `RUSTFS_CONSOLE_ADDRESS` — web console bind address
- `RUSTFS_VOLUMES` — storage volume paths
- `RUSTFS_CONSOLE_ENABLE` — enable/disable console
- `RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS` — CORS origins

### 2.2 MinIO

- **License:** AGPLv3 (commercial use requires enterprise license)
- **Language:** Go
- **S3 API Compatibility:** The de facto standard for S3-compatible storage
- **Maturity:** Production-proven, years of deployments
- **Community:** Very large, extensive documentation
- **Restriction:** Free tier stripped of many features; enterprise features behind paywall

### 2.3 Recommendation for SkateLab

**RustFS is the right choice** for this project:
1. Apache 2.0 license is commercial-friendly (no AGPL concern)
2. Single-node deployment matches the project's dedicated server architecture
3. RustFS is designed as a drop-in MinIO replacement with compatible API
4. Active development (3,048+ commits), growing community (23k stars)
5. The Alpha status is acceptable for a single-server MVP — production hardening comes later

**Risk mitigation:** The `S3_ENDPOINT_URL` config means switching between RustFS/MinIO/Garage requires only a config change. No code changes needed.

### 2.4 Garage (Alternative)

Garage is a lighter-weight alternative (written in Rust, 3-node distributed):
- Runs on different ports (3900 for S3 API) — can coexist with MinIO/RustFS
- Lower resource requirements for small deployments
- Currently more CLI-driven, less polished console
- Worth monitoring but not as mature as RustFS for production use

---

## 3. S3-Compatible Storage Environment Variable Naming Conventions

### 3.1 What Mature Projects Use

Research across multiple mature projects reveals clear naming patterns:

#### AWS SDK Standard (boto3, AWS CLI)

Since boto3 1.28.0, AWS SDKs support **service-specific endpoint override via environment variables**:

```
AWS_ENDPOINT_URL            — Global endpoint for ALL services
AWS_ENDPOINT_URL_S3         — S3-specific endpoint (overrides global)
AWS_ENDPOINT_URL_DYNAMODB   — DynamoDB-specific endpoint
```

**Precedence order:** Code `endpoint_url` parameter > `AWS_ENDPOINT_URL_<SERVICE>` > `AWS_ENDPOINT_URL` > config file > default AWS endpoint.

This is the **official AWS convention** and boto3 1.28+ automatically picks up these env vars. No code changes needed if using standard boto3 sessions.

#### Langfuse

Uses `LANGFUSE_S3_*` prefix with per-use-case granularity:

```
LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT
LANGFUSE_S3_EVENT_UPLOAD_BUCKET
LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID
LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY
LANGFUSE_S3_EVENT_UPLOAD_REGION
LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE

LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT
LANGFUSE_S3_MEDIA_UPLOAD_BUCKET
...
LANGFUSE_S3_BATCH_EXPORT_ENDPOINT
LANGFUSE_S3_BATCH_EXPORT_BUCKET
...
```

**Key observation:** Langfuse includes `FORCE_PATH_STYLE` — required for MinIO/RustFS (self-hosted S3 always needs `addressing_style="path"`).

Also notable: Langfuse has `EXTERNAL_ENDPOINT` for presigned URLs — separate from internal endpoint:
```
LANGFUSE_S3_BATCH_EXPORT_EXTERNAL_ENDPOINT  # For generating presigned URLs
                                             # accessible from outside the VPC
```

#### PostHog

Uses `OBJECT_STORAGE_*` prefix (vendor-neutral, not S3-specific):

```
OBJECT_STORAGE_ENDPOINT
OBJECT_STORAGE_PUBLIC_ENDPOINT  # For presigned URLs (external-facing)
OBJECT_STORAGE_BUCKET
OBJECT_STORAGE_ACCESS_KEY_ID
OBJECT_STORAGE_SECRET_ACCESS_KEY
```

**Key design:** PostHog separates `OBJECT_STORAGE_ENDPOINT` (internal, Docker network) from `OBJECT_STORAGE_PUBLIC_ENDPOINT` (external, for presigned URLs). This is exactly the pattern SkateLab needs.

#### RustFS

Uses `RUSTFS_` prefix for server configuration:
```
RUSTFS_ACCESS_KEY
RUSTFS_SECRET_KEY
RUSTFS_ADDRESS
RUSTFS_CONSOLE_ADDRESS
RUSTFS_VOLUMES
```

These are **server-side** env vars (configuring the RustFS process itself), not application-side.

### 3.2 SkateLab's Proposed Naming: Assessment

The spec proposes `S3_*` prefix:

```
S3_ENDPOINT_URL
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
S3_BUCKET
```

**Assessment: Good, with caveats:**

| Aspect | Assessment | Recommendation |
|--------|-----------|----------------|
| `S3_` prefix | Vendor-neutral, future-proof | **Keep.** Better than `R2_` or `RUSTFS_` |
| `S3_ENDPOINT_URL` | Matches AWS convention (`AWS_ENDPOINT_URL_S3`) but shorter | **Keep.** Clear and unambiguous |
| Missing: `S3_REGION` | R2 uses `auto`, RustFS needs `us-east-1` or custom | **Add `S3_REGION`** with default `"us-east-1"` |
| Missing: `S3_PATH_STYLE` | Self-hosted S3 always needs path-style addressing | **Add `S3_PATH_STYLE`** with default `True` |
| Missing: public endpoint | Presigned URLs need external-facing URL | **Add `S3_PUBLIC_ENDPOINT_URL`** (see below) |
| Missing: presign expiry | Currently `presign_expires` in config | Keep as `S3_PRESIGN_EXPIRES` with default `3600` |

### 3.3 Recommended Environment Variables

```env
# S3-compatible object storage (RustFS / any S3 backend)
S3_ENDPOINT_URL=http://infra-rustfs-1:9000        # Internal Docker DNS
S3_PUBLIC_ENDPOINT_URL=https://s3.skatelab.ru      # External-facing URL for presigned URLs
S3_ACCESS_KEY_ID=change-me
S3_SECRET_ACCESS_KEY=change-me
S3_BUCKET=skatelab-pipeline
S3_REGION=us-east-1                                 # RustFS default region
S3_PATH_STYLE=true                                  # Required for self-hosted S3
```

### 3.4 The Public Endpoint Pattern

PostHog's `OBJECT_STORAGE_PUBLIC_ENDPOINT` pattern is critical for self-hosted deployments:

- **Internal endpoint** (`S3_ENDPOINT_URL`): `http://infra-rustfs-1:9000` — used by the backend inside Docker network
- **Public endpoint** (`S3_PUBLIC_ENDPOINT_URL`): `https://s3.skatelab.ru` — used in presigned URLs served to frontend/clients

Currently, SkateLab uses a **backend proxy pattern** (no presigned URLs to frontend), so `S3_PUBLIC_ENDPOINT_URL` is optional for now but should be added for future use.

---

## 4. boto3 S3 Client Rename Refactoring Gotchas

### 4.1 Code Changes in the Spec

The spec proposes renaming:
- `R2Config` → `S3Config` (in config.py)
- `R2_` env prefix → `S3_` env prefix
- `get_r2_client()` → `get_s3_client()` (in storage.py)
- `r2` attribute on Settings → `s3`
- All `r2_key` variables → `s3_key`
- All comment references "R2" → "S3"

### 4.2 boto3/Aiobotocore-Specific Gotchas

| Gotcha | Details | Fix |
|--------|---------|------|
| `region_name="auto"` | R2 requires `region_name="auto"`. RustFS/MinIO default is `us-east-1`. | Change default in S3Config to `"us-east-1"` or make configurable |
| `Config(signature_version="s3v4")` | Both R2 and RustFS use SigV4. | Keep as-is — compatible |
| Path-style addressing | R2 supports both virtual-hosted and path-style. Self-hosted S3 backends typically require path-style. | Add `s3={"addressing_style": "path"}` to BotoConfig when `S3_PATH_STYLE=true` |
| `endpoint_url=""` as default | Current code uses `s.r2.endpoint_url or None` — empty string falls back to AWS S3. | Keep this pattern — works for local dev without S3 |
| Thread-local client cache | `threading.local()` stores `r2_client` → rename to `s3_client` | Pure rename, no behavioral change |
| Async client singleton | `_async_client_instance` + `_credential_hash` for credential rotation | Rename only — credential rotation logic is backend-agnostic |
| Presigned URL generation | `generate_presigned_url()` uses the endpoint URL from the client. When switching from R2 to RustFS, URLs will change from `*.r2.cloudflarestorage.com` to `s3.skatelab.ru` or `infra-rustfs-1:9000` | Ensure `endpoint_url` is set correctly; presigned URLs will automatically use the new host |

### 4.3 BotoConfig Changes Required

Current:
```python
_R2_CONFIG = BotoConfig(
    signature_version="s3v4",
    connect_timeout=10,
    read_timeout=300,
    retries={"max_attempts": 3, "mode": "adaptive"},
)
```

Should become:
```python
_S3_CONFIG = BotoConfig(
    signature_version="s3v4",
    connect_timeout=10,
    read_timeout=300,
    retries={"max_attempts": 3, "mode": "adaptive"},
    s3={"addressing_style": "path"},  # REQUIRED for self-hosted S3
)
```

**`s3={"addressing_style": "path"}`** is the critical addition. Without this, boto3 will construct URLs like `https://bucket.s3.skatelab.ru/key` (virtual-hosted style) instead of `https://s3.skatelab.ru/bucket/key` (path-style). Self-hosted S3 backends almost always require path-style addressing unless you set up wildcard DNS.

### 4.4 Region Name Change

Current code:
```python
region_name="auto",  # R2-specific
```

Must change to:
```python
region_name=s.s3.region,  # Configurable, default "us-east-1"
```

R2's `"auto"` region is not recognized by RustFS/MinIO. Using `"us-east-1"` is the standard default for self-hosted S3.

---

## 5. Docker Compose S3 Organization Patterns

### 5.1 Single-Server Pattern (SkateLab's Architecture)

The spec uses a single compose.yaml for shared infrastructure (PostgreSQL, Valkey, RustFS, Caddy) with Docker profiles for optional services (PostHog). This is a well-established pattern.

**Best practices from mature projects:**

#### Network Isolation
```yaml
services:
  rustfs:
    # ... 
    networks:
      - app_network  # Backend services talk to RustFS here
    ports:
      - "9000:9000"   # S3 API (also exposed for local dev)
      - "9001:9001"   # Console (optional, can be internal-only)
```

#### Health Checks
RustFS provides health check endpoints. The official docker-compose includes:
```yaml
healthcheck:
  test: ["CMD", "sh", "-c", 
    "curl -f http://127.0.0.1:9000/health && curl -f http://127.0.0.1:9001/rustfs/console/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

#### Volume Permissions
RustFS runs as UID 10001 by default. The official compose includes a permission-fixer service:
```yaml
volume-permission-helper:
  image: alpine
  volumes:
    - rustfs_data_0:/data0
    # ...
  command: sh -c "chown -R 10001:10001 /data0 /data1 /data2 /data3 /logs && exit 0"
  restart: "no"
```

#### Bucket Auto-Creation
RustFS does **not** auto-create buckets on startup. For the `skatelab-pipeline` and `posthog` buckets:
- Create via RustFS console (`http://<host>:9001`)
- Or create via `mc` (MinIO Client) or `aws s3api create-bucket` in an init container
- Or use a startup script in compose.yaml

### 5.2 PostHog + MinIO/RustFS Integration

PostHog's self-hosted docker-compose uses MinIO with these env vars:
```yaml
minio:
  image: minio/minio:RELEASE.2022-09-17T00-09-45Z.fips
  environment:
    MINIO_ROOT_USER: ${MINIO_ROOT_USER}
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
  command: >-
    minio server --address ":19000" --console-address ":19001" /data
```

PostHog app containers reference object storage via:
```yaml
web:
  environment:
    OBJECT_STORAGE_ENDPOINT: http://minio:19000
    OBJECT_STORAGE_BUCKET: posthog
    # ...
```

**For SkateLab's setup**, the compose.yaml should configure RustFS similarly, sharing the same S3 credentials between SkateLab app and PostHog (or using separate access keys for isolation).

### 5.3 RustFS Single-Node Production Recommendations

Based on the RustFS docs and the FreshBrewed Science article:

1. **Use a dedicated volume** — not the root filesystem. `/data/rustfs` on a separate mount.
2. **Set `RUSTFS_ACCESS_KEY` and `RUSTFS_SECRET_KEY`** — change from defaults.
3. **Restart policy**: `unless-stopped` (matches SkateLab's existing pattern).
4. **No need for multi-disk volumes** for single-server MVP — a single volume path is fine:
   ```yaml
   environment:
     - RUSTFS_VOLUMES=/data
   volumes:
     - rustfs_data:/data
   ```
   Or keep the `{0...3}` erasure coding pattern from the official compose for future scalability.
5. **Backup**: Use `rclone sync` or `aws s3 sync` to another location periodically.
6. **No TLS on RustFS itself** — terminate TLS at Caddy reverse proxy (matches SkateLab's existing Caddy pattern).

---

## 6. Summary of Recommendations

### 6.1 Environment Variable Design (CONFIRMED + ADDITIONS)

The spec's `S3_*` prefix naming is correct. **Add these missing variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `S3_ENDPOINT_URL` | (required) | Internal endpoint (Docker DNS) |
| `S3_PUBLIC_ENDPOINT_URL` | `$S3_ENDPOINT_URL` | External URL for presigned URLs (future-proof) |
| `S3_ACCESS_KEY_ID` | (required) | S3 access key |
| `S3_SECRET_ACCESS_KEY` | (required) | S3 secret key |
| `S3_BUCKET` | `skatelab-pipeline` | Default bucket |
| `S3_REGION` | `us-east-1` | Region (was `"auto"` for R2) |
| `S3_PATH_STYLE` | `true` | Required for self-hosted S3 |

### 6.2 Code Changes Beyond Rename

| Change | Why |
|--------|-----|
| Add `s3={"addressing_style": "path"}` to BotoConfig | Self-hosted S3 requires path-style addressing |
| Change `region_name="auto"` to `region_name=s.s3.region` | RustFS doesn't recognize `"auto"` |
| Add `S3_REGION` and `S3_PATH_STYLE` to S3Config | Make region and path-style configurable |
| Consider `S3_PUBLIC_ENDPOINT_URL` for presigned URLs | Follow PostHog's `OBJECT_STORAGE_PUBLIC_ENDPOINT` pattern |

### 6.3 Infrastructure Changes

| Change | Why |
|--------|-----|
| Add bucket auto-creation init step | RustFS doesn't auto-create buckets |
| Add health check to RustFS service | Standard Docker practice |
| Consider volume permission helper | RustFS runs as UID 10001 |
| Ensure Caddy reverse-proxies S3 API (not direct access) | Security: S3 credentials not exposed publicly |

### 6.4 Migration Checklist

1. Deploy RustFS alongside existing services in `infra/compose.yaml`
2. Create `skatelab-pipeline` bucket in RustFS console or via `aws s3api`
3. Copy existing R2 data to RustFS: `rclone sync r2:skatelab-pipeline rustfs:skatelab-pipeline`
4. Update `.env.prod` with new `S3_*` variables pointing to RustFS
5. Update backend config: `region_name`, `addressing_style`
6. Run integration tests
7. Switch DNS/Caddy to point to RustFS
8. Remove R2 configuration and old `R2_*` env vars

---

## 7. References

- [AWS SDK Service-Specific Endpoints](https://docs.aws.amazon.com/sdkref/latest/guide/feature-ss-endpoints.html) — official `AWS_ENDPOINT_URL_S3` convention
- [boto3 1.28.0 endpoint_url env vars](https://alexocallaghan.com/configure-boto3-endpoint-url) — `AWS_ENDPOINT_URL` and `AWS_ENDPOINT_URL_S3` support
- [RustFS GitHub](https://github.com/rustfs/rustfs) — 23k+ stars, Apache 2.0, 3,048 commits
- [RustFS official site](https://rustfs.com) — product overview, features
- [RustFS docker-compose-simple.yml](https://github.com/rustfs/rustfs/blob/main/docker-compose-simple.yml) — single-node config template
- [RustFS MinIO migration (Issue #2212)](https://github.com/rustfs/rustfs/issues/2212) — drop-in binary replacement guide
- [FreshBrewed Science: RustFS and Garage](https://freshbrewed.science/2025/12/31/rustfsgarage.html) — hands-on deployment comparison
- [Cloudflare R2 Presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls) — R2-specific presigned URL behavior
- [Langfuse S3 Configuration](https://langfuse.com/self-hosting/deployment/infrastructure/blobstorage) — mature S3 config pattern with `FORCE_PATH_STYLE` and `EXTERNAL_ENDPOINT`
- [PostHog Environment Variables](https://posthog.com/docs/self-host/configure/environment-variables) — `OBJECT_STORAGE_*` and `OBJECT_STORAGE_PUBLIC_ENDPOINT`
- [Sealos: What Is RustFS](https://sealos.io/blog/what-is-rustfs) — balanced assessment, "evaluate-carefully" recommendation
- [Tigris: Migrate from MinIO](https://www.tigrisdata.com/docs/migration/minio) — migration patterns, shadow buckets
- [boto3 issue #1375: endpoint_url from env var](https://github.com/boto/boto3/issues/1375) — long-awaited feature, resolved in 1.28.0