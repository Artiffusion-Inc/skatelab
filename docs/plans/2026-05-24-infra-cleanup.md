# Infra Cleanup & S3 Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** R2→S3 полный рефактор, удаление мёртвого кода, чистая структура infra/

**Architecture:** R2Config→S3Config с новыми полями (region, path_style, public_endpoint_url), path-style addressing в BotoConfig, region_name configurable, хардкод image tags, удаление android-emulator, ClickHouse оптимизация

**Tech Stack:** Python/FastAPI (backend), TypeScript/Next.js (frontend), Docker Compose (infra), boto3/aiobotocore (S3)

---

## Wave 1: Backend R2→S3 refactor (config + storage)

### Task 1: R2Config → S3Config in config.py

**Files:**

- Modify: `backend/app/config.py:100-110`

- [ ] **Step 1: Replace R2Config class with S3Config**

```python
class S3Config(BaseSettings):
    """S3-compatible object storage (RustFS / any S3 backend)."""

    access_key_id: SecretStr = SecretStr("")
    secret_access_key: SecretStr = SecretStr("")
    bucket: str = "skatelab-pipeline"
    endpoint_url: str = ""
    public_endpoint_url: str = ""
    region: str = "us-east-1"
    path_style: bool = True
    presign_expires: int = 3600

    class Config:
        env_prefix = "S3_"
```

- [ ] **Step 2: Update Settings class reference**

In `backend/app/config.py:190`, change:
```python
r2: R2Config = Field(default_factory=R2Config)
```
to:
```python
s3: S3Config = Field(default_factory=S3Config)
```

- [ ] **Step 3: Update module docstring**

In `backend/app/config.py:11`, change `R2_         — Cloudflare R2 object storage` to `S3_         — S3-compatible object storage (RustFS)`

- [ ] **Step 4: Run type check**

Run: `cd backend && uv run basedpyright app/config.py`
Expected: PASS (no R2 references remain)

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py
git commit -m "refactor(backend): rename R2Config to S3Config with new fields"
```

### Task 2: storage.py R2→S3 + path-style addressing + region_name

**Files:**

- Modify: `backend/app/storage.py` (270 lines)

- [ ] **Step 1: Rename _R2_CONFIG and add path-style addressing**

```python
_S3_CONFIG = BotoConfig(
    signature_version="s3v4",
    s3={"addressing_style": "path"},
    connect_timeout=10,
    read_timeout=300,
    retries={"max_attempts": 3, "mode": "adaptive"},
)
```

- [ ] **Step 2: Rename get_r2_client → get_s3_client, fix region_name**

```python
def get_s3_client():
    """Per-thread boto3 client (thread-safe for asyncio.to_thread)."""
    client = getattr(_thread_local, "s3_client", None)
    if client is None:
        s = get_settings()
        client = boto3.client(
            "s3",
            endpoint_url=s.s3.endpoint_url or None,
            aws_access_key_id=s.s3.access_key_id.get_secret_value(),
            aws_secret_access_key=s.s3.secret_access_key.get_secret_value(),
            config=_S3_CONFIG,
            region_name=s.s3.region,
        )
        _thread_local.s3_client = client
    return client
```

- [ ] **Step 3: Rename get_r2_async_client → get_s3_async_client**

All `r2` → `s3` references in the async client function. Change:
- `_thread_local.r2_client` → `_thread_local.s3_client`
- `s.r2.endpoint_url` → `s.s3.endpoint_url`
- `s.r2.access_key_id` → `s.s3.access_key_id`
- `s.r2.secret_access_key` → `s.s3.secret_access_key`
- `region_name="auto"` → `region_name=s.s3.region`

- [ ] **Step 4: Rename reset_r2_async_client → reset_s3_async_client**

Same pattern: all `r2` → `s3`.

- [ ] **Step 5: Rename close_r2_clients → close_s3_clients**

Change `_thread_local.r2_client` → `_thread_local.s3_client`.

- [ ] **Step 6: Update all helper functions**

Every function that calls `get_r2_client()` → `get_s3_client()`, `get_r2_async_client()` → `get_s3_async_client()`, `get_settings().r2` → `get_settings().s3`.

Full list of renames in helper functions:
- `upload_file`: `get_r2_client()` → `get_s3_client()`, `s.r2.bucket` → `s.s3.bucket`
- `download_file`: same
- `delete_object`: same
- `upload_bytes`: same
- `stream_object`: same
- `object_exists`: same
- `get_object_url`: same
- `list_objects`: same
- `upload_file_async`: `get_r2_async_client()` → `get_s3_async_client()`, `s.r2.bucket` → `s.s3.bucket`
- `download_file_async`: same
- `upload_bytes_async`: same
- `object_exists_async`: same
- `stream_object_async`: same
- `get_object_url_async`: same
- `delete_object_async`: same
- `list_objects_async`: same

- [ ] **Step 7: Update docstring and comments**

Module docstring: `"Cloudflare R2"` → `"S3-compatible (RustFS)"`. All inline `R2` → `S3` in comments.

- [ ] **Step 8: Update _get_credential_hash**

```python
def _get_credential_hash() -> str:
    s = get_settings()
    return hashlib.sha256(
        (s.s3.access_key_id.get_secret_value() + s.s3.secret_access_key.get_secret_value()).encode()
    ).hexdigest()
```

- [ ] **Step 9: Run type check**

Run: `cd backend && uv run basedpyright app/storage.py`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add backend/app/storage.py
git commit -m "refactor(backend): rename R2→S3 in storage.py, add path-style addressing"
```

### Task 3: Update vastai/client.py R2→S3

**Files:**

- Modify: `backend/app/vastai/client.py:130-139,188-194`

- [ ] **Step 1: Replace r2_* keys in process_video_remote_async payload**

Lines 136-139, change:
```python
"r2_endpoint_url": settings.r2.endpoint_url,
"r2_access_key_id": settings.r2.access_key_id.get_secret_value(),
"r2_secret_access_key": settings.r2.secret_access_key.get_secret_value(),
"r2_bucket": settings.r2.bucket,
```
to:
```python
"s3_endpoint_url": settings.s3.endpoint_url,
"s3_access_key_id": settings.s3.access_key_id.get_secret_value(),
"s3_secret_access_key": settings.s3.secret_access_key.get_secret_value(),
"s3_bucket": settings.s3.bucket,
```

- [ ] **Step 2: Replace r2_* keys in detect_video_remote_async payload**

Lines 191-194, same rename.

- [ ] **Step 3: Update module docstring**

Line 7: `4. Return R2 keys (no local download)` → `4. Return S3 keys (no local download)`

Line 111: `Video must already be in R2 at \`video_key\`.` → `Video must already be in S3 at \`video_key\`.`

- [ ] **Step 4: Run type check**

Run: `cd backend && uv run basedpyright app/vastai/client.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/vastai/client.py
git commit -m "refactor(backend): rename r2_* to s3_* in vastai client payload"
```

### Task 4: Update routes R2→S3

**Files:**

- Modify: `backend/app/routes/choreography.py:18,46-47,50,62,91-92,105,121,126-127,130`
- Modify: `backend/app/routes/misc.py:1,41`
- Modify: `backend/app/routes/users.py:125-129,135`
- Modify: `backend/app/routes/uploads.py:114`

- [ ] **Step 1: Update choreography.py**

Change import: `from app.storage import get_r2_client` → `from app.storage import get_s3_client`

All `r2 = get_r2_client()` → `s3 = get_s3_client()`
All `r2.create_multipart_upload(` → `s3.create_multipart_upload(`
All `r2.generate_presigned_url(` → `s3.generate_presigned_url(`
All `r2.complete_multipart_upload(` → `s3.complete_multipart_upload(`
`get_settings().r2.bucket` → `get_settings().s3.bucket`
Comment: `direct R2 upload` → `direct S3 upload`

- [ ] **Step 2: Update misc.py**

Line 1: `R2 streaming proxy` → `S3 streaming proxy`
Line 41: `Stream file from R2 as a proxy` → `Stream file from S3 as a proxy`

- [ ] **Step 3: Update users.py**

Line 125: `Upload to R2` → `Upload to S3`
Line 126: `r2_key = f"music/..."` → `s3_key = f"music/..."`
Line 127: `Uploading to R2: %s", r2_key` → `Uploading to S3: %s", s3_key`
Line 128: `upload_file, tmp_path, r2_key` → `upload_file, tmp_path, s3_key`
Line 129: `R2 upload complete` → `S3 upload complete`
Line 135: `r2_key=r2_key` → `s3_key=s3_key`

- [ ] **Step 4: Update uploads.py**

Line 114: `Upload to R2` → `Upload to S3`

- [ ] **Step 5: Run type check**

Run: `cd backend && uv run basedpyright app/routes/`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/
git commit -m "refactor(backend): rename R2→S3 in all routes"
```

### Task 5: Update backend tests R2→S3

**Files:**

- Modify: `backend/tests/test_storage.py`
- Modify: `backend/tests/test_vastai_client.py:166-169`
- Modify: `backend/tests/test_vastai_client_extended.py:19-22`
- Modify: `backend/tests/routes/test_choreography_upload.py:121`

- [ ] **Step 1: Update test_storage.py**

All `@patch("app.storage.get_r2_client")` → `@patch("app.storage.get_s3_client")`
All `@patch("app.storage.get_r2_async_client"` → `@patch("app.storage.get_s3_async_client"`

Docstring: `Tests for R2 storage operations.` → `Tests for S3 storage operations.`

- [ ] **Step 2: Update test_vastai_client.py**

Line 166-169, change mock settings:
```python
s.r2.endpoint_url = "https://r2.example.com"
s.r2.access_key_id.get_secret_value.return_value = "key-id"
s.r2.secret_access_key.get_secret_value.return_value = "secret"
s.r2.bucket = "test-bucket"
```
to:
```python
s.s3.endpoint_url = "https://s3.example.com"
s.s3.access_key_id.get_secret_value.return_value = "key-id"
s.s3.secret_access_key.get_secret_value.return_value = "secret"
s.s3.bucket = "test-bucket"
```

- [ ] **Step 3: Update test_vastai_client_extended.py**

Same pattern in `_make_settings()`: `s.r2.*` → `s.s3.*`

- [ ] **Step 4: Update test_choreography_upload.py**

Line 121: `r2_key="music/user_123/music_456.mp3"` → `s3_key="music/user_123/music_456.mp3"`

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/
git commit -m "test(backend): update R2→S3 in all test mocks"
```

### Task 6: Frontend CSP R2→S3

**Files:**

- Modify: `frontend/src/proxy.ts:20,25`

- [ ] **Step 1: Replace R2 CSP domains with S3 domain**

Line 20: `"https://*.r2.cloudflarestorage.com",` → `"https://s3.skatelab.ru",`

Line 25: `: ["'self'", "blob:", "https://*.r2.cloudflarestorage.com"]` → `: ["'self'", "blob:", "https://s3.skatelab.ru"]`

- [ ] **Step 2: Run TypeScript check**

Run: `cd frontend && bunx tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/proxy.ts
git commit -m "refactor(frontend): replace R2 CSP domains with s3.skatelab.ru"
```

---

## Wave 2: Infra files

### Task 7: .env.prod.template cleanup + S3_* vars

**Files:**

- Modify: `infra/.env.prod.template`

- [ ] **Step 1: Rewrite .env.prod.template per spec**

Replace entire file with:
```env
# ── Infra (shared services) ──────────────
POSTGRES_PASSWORD=change-me-32-chars-min

# ── SkateLab App ──────────────────────────
DATABASE_URL=postgresql+asyncpg://skatelab:change-me@infra-postgres-1:5432/skatelab
S3_ENDPOINT_URL=http://infra-rustfs-1:9000
S3_PUBLIC_ENDPOINT_URL=https://s3.skatelab.ru
S3_ACCESS_KEY_ID=change-me
S3_SECRET_ACCESS_KEY=change-me
S3_BUCKET=skatelab-pipeline
S3_REGION=us-east-1
S3_PATH_STYLE=true
JWT_SECRET_KEY=change-me-64-chars-min
VALKEY_URL=redis://infra-valkey-1:6379/3
VASTAI_API_KEY=
RESEND_API_KEY=

# ── PostHog ───────────────────────────────
POSTHOG_SECRET_KEY=change-me-64-chars
POSTHOG_POSTGRES_PASSWORD=change-me
POSTHOG_ENCRYPTION_SALT_KEYS=
POSTHOG_API_KEY=
POSTHOG_HOST=https://ph.skatelab.ru
NEXT_PUBLIC_POSTHOG_KEY=
NEXT_PUBLIC_POSTHOG_HOST=https://ph.skatelab.ru
POSTHOG_PERSONAL_API_KEY=

# ── Domain / TLS ──────────────────────────
DOMAIN=skatelab.ru
CLOUDFLARE_API_TOKEN=change-me
```

- [ ] **Step 2: Commit**

```bash
git add infra/.env.prod.template
git commit -m "refactor(infra): clean .env.prod.template, S3_* vars, remove R2/RUSTFS/TAG"
```

### Task 8: compose.prod.yaml R2→S3

**Files:**

- Modify: `infra/compose.prod.yaml:15-18,10,39,45`

- [ ] **Step 1: Replace R2_* env vars with S3_***

Lines 15-18, change:
```yaml
R2_ENDPOINT_URL: ${R2_ENDPOINT_URL}
R2_ACCESS_KEY_ID: ${R2_ACCESS_KEY_ID}
R2_SECRET_ACCESS_KEY: ${R2_SECRET_ACCESS_KEY}
R2_BUCKET: ${R2_BUCKET}
```
to:
```yaml
S3_ENDPOINT_URL: ${S3_ENDPOINT_URL:-}
S3_PUBLIC_ENDPOINT_URL: ${S3_PUBLIC_ENDPOINT_URL:-}
S3_ACCESS_KEY_ID: ${S3_ACCESS_KEY_ID:-}
S3_SECRET_ACCESS_KEY: ${S3_SECRET_ACCESS_KEY:-}
S3_BUCKET: ${S3_BUCKET:-skatelab-pipeline}
S3_REGION: ${S3_REGION:-us-east-1}
S3_PATH_STYLE: ${S3_PATH_STYLE:-true}
```

- [ ] **Step 2: Hardcode image tags, remove TAG/GHCR_OWNER**

Line 10: `image: ghcr.io/${GHCR_OWNER:-artiffusion-inc}/skatelab-backend:${TAG:-latest}` → `image: ghcr.io/artiffusion-inc/skatelab-backend:latest`

Line 39: `image: ghcr.io/${GHCR_OWNER:-artiffusion-inc}/skatelab-frontend:${TAG:-latest}` → `image: ghcr.io/artiffusion-inc/skatelab-frontend:latest`

- [ ] **Step 3: Remove LOG_LEVEL, NEXT_PUBLIC_API_URL**

Line 24: Delete `LOG_LEVEL: ${LOG_LEVEL:-info}`

Line 45: Delete `NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-/api}`

- [ ] **Step 4: Commit**

```bash
git add infra/compose.prod.yaml
git commit -m "refactor(infra): R2→S3 env vars, hardcode image tags in compose.prod"
```

### Task 9: compose.yaml — hardcode PostHog tags + add name

**Files:**

- Modify: `infra/compose.yaml`

- [ ] **Step 1: Add `name: infra` at top of file**

After `services:` line, add before services:
```yaml
name: infra
```

- [ ] **Step 2: Hardcode PostHog image tags**

Replace all `${POSTHOG_APP_TAG:-1.88.0}` → `1.88.0` (or the current pinned version).
Replace all `${POSTHOG_NODE_TAG:-1.88.0}` → `1.88.0`.
Replace all `${POSTHOG_RUST_TAG:-1.88.0}` → `1.88.0`.

- [ ] **Step 3: Replace RUSTFS_* with S3_* mapping**

In the RustFS service, change:
```yaml
RUSTFS_ACCESS_KEY: ${RUSTFS_ACCESS_KEY_ID:-rustfsadmin}
RUSTFS_SECRET_KEY: ${RUSTFS_SECRET_ACCESS_KEY:-rustfsadmin}
```
to:
```yaml
RUSTFS_ACCESS_KEY: ${S3_ACCESS_KEY_ID:-rustfsadmin}
RUSTFS_SECRET_KEY: ${S3_SECRET_ACCESS_KEY:-rustfsadmin}
```

- [ ] **Step 4: Commit**

```bash
git add infra/compose.yaml
git commit -m "refactor(infra): hardcode PostHog tags, add name: infra, RUSTFS→S3 mapping"
```

### Task 10: Delete android-emulator/

**Files:**

- Delete: `infra/android-emulator/compose.yaml`
- Delete: `infra/android-emulator/Containerfile`
- Delete: `infra/android-emulator/supervisord.conf`
- Delete: `infra/android-emulator/.containerignore`

- [ ] **Step 1: Delete the directory**

```bash
rm -rf infra/android-emulator/
```

- [ ] **Step 2: Commit**

```bash
git add -A infra/android-emulator/
git commit -m "chore(infra): remove android-emulator directory"
```

### Task 11: ClickHouse config optimization

**Files:**

- Modify: `infra/clickhouse/config.d/custom.xml`

- [ ] **Step 1: Replace with optimized config**

```xml
<clickhouse>
    <max_server_memory_usage>4294967296</max_server_memory_usage>
    <max_server_memory_usage_to_ram_ratio>0.75</max_server_memory_usage_to_ram_ratio>

    <mark_cache_size>268435456</mark_cache_size>
    <index_mark_cache_size>134217728</index_mark_cache_size>

    <mysql_port remove="1" />
    <postgresql_port remove="1" />

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

    <background_pool_size>2</background_pool_size>
    <background_merges_mutations_concurrency_ratio>2</background_merges_mutations_concurrency_ratio>
    <merge_tree>
        <merge_max_block_size>1024</merge_max_block_size>
        <max_bytes_to_merge_at_max_space_in_pool>268435456</max_bytes_to_merge_at_max_space_in_pool>
        <number_of_free_entries_in_pool_to_lower_max_size_of_merge>2</number_of_free_entries_in_pool_to_lower_max_size_of_merge>
        <number_of_free_entries_in_pool_to_execute_mutation>2</number_of_free_entries_in_pool_to_execute_mutation>
    </merge_tree>

    <max_concurrent_queries>4</max_concurrent_queries>
    <max_execution_time>60</max_execution_time>

    <max_bytes_before_external_group_by>268435456</max_bytes_before_external_group_by>
    <max_bytes_before_external_sort>268435456</max_bytes_before_external_sort>
</clickhouse>
```

- [ ] **Step 2: Commit**

```bash
git add infra/clickhouse/config.d/custom.xml
git commit -m "perf(infra): optimize ClickHouse config, save ~1GB RAM"
```

### Task 12: Update infra/CLAUDE.md

**Files:**

- Modify: `infra/CLAUDE.md`

- [ ] **Step 1: R2→S3 in Environment Variables**

Change `R2_*` → `S3_*` references. Remove `POSTHOG_*_TAG`, `RUSTFS_*` vars.

- [ ] **Step 2: Remove android-emulator references**

Delete any mentions of android-emulator or "Android Emulator (CI)".

- [ ] **Step 3: Remove dev-postgres/dev-valkey**

Dev has no containers — only files.

- [ ] **Step 4: Add three areas description**

Add table: infra (`/opt/infra/`), prod (`/opt/skatelab/`), dev (`/home/dev/skatelab/` — code only).

- [ ] **Step 5: Update Gotchas**

Change `R2_/RUSTFS_` → `S3_` references. Add S3_PATH_STYLE note.

- [ ] **Step 6: Update Commands section**

Ensure PostHog commands use `--profile posthog`.

- [ ] **Step 7: Commit**

```bash
git add infra/CLAUDE.md
git commit -m "docs(infra): update CLAUDE.md — S3_* vars, remove R2/android-emulator"
```

---

## Wave 3: Final verification

### Task 13: Full test suite + grep for stale R2 references

- [ ] **Step 1: Run backend tests**

```bash
cd backend && uv run pytest tests/ -x -q
```

Expected: ALL PASS

- [ ] **Step 2: Run backend type check**

```bash
cd backend && uv run basedpyright app/
```

Expected: PASS

- [ ] **Step 3: Run frontend TypeScript check**

```bash
cd frontend && bunx tsc --noEmit
```

Expected: PASS

- [ ] **Step 4: Grep for stale R2 references**

```bash
grep -rn "R2_\|R2Config\|r2_\|get_r2_\|\.r2\.\|r2\.cloudflarestorage" backend/ frontend/ infra/ --include="*.py" --include="*.ts" --include="*.yaml" --include="*.yml" --include="*.env*" 2>/dev/null | grep -v "__pycache__" | grep -v "node_modules" | grep -v ".git"
```

Expected: NO OUTPUT (zero stale references)

- [ ] **Step 5: Commit any fixes if needed**

```bash
git add -A && git commit -m "fix: clean up stale R2 references"
```

(Only if grep found anything — skip if clean)

---

## Summary

| Wave | Tasks | Scope |
|------|-------|-------|
| 1 | Tasks 1-6 | Backend R2→S3 refactor (config, storage, vastai, routes, tests, frontend CSP) |
| 2 | Tasks 7-12 | Infra files (.env, compose, android-emulator, ClickHouse, CLAUDE.md) |
| 3 | Task 13 | Full verification (tests, type check, grep for stale refs) |
