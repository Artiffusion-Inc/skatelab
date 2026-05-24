# Infra Cleanup & S3 Unification Design

**Goal:** Навести порядок в `infra/` — единый source of truth, универсальные S3-переменные, удалить мёртвый код, чёткое разделение трёх областей (infra/prod/dev).

**Architecture:** Один compose.yaml для shared сервисов (infra), отдельный compose.prod.yaml для SkateLab app. PostHog через Docker profiles. R2→S3 полный рефактор — единый S3-совместимый бекенд (RustFS). Android emulator удалён.

**Tech Stack:** Docker Compose, RustFS (S3), Valkey, PostgreSQL 17/15, Caddy, PostHog self-hosted

---

## 0. Research Summary

5 специализированных агентов исследовали: S3-миграцию, compose-структуру, PostHog-оптимизацию, env-менеджмент, single-server patterns. Ключевые находки:

**CRITICAL — Path-style addressing:** `s3={"addressing_style": "path"}` обязателен в BotoConfig для RustFS/MinIO. Без этого boto3 генерирует virtual-hosted URLs (`bucket.s3.skatelab.ru/key`) вместо path-style (`s3.skatelab.ru/bucket/key`).

**CRITICAL — region_name:** `"auto"` (R2) не распознаётся RustFS. Должно быть `"us-east-1"` или конфигурируемое через `S3_REGION`.

**Новые env vars:** `S3_REGION` (default `us-east-1`), `S3_PATH_STYLE` (default `true`), `S3_PUBLIC_ENDPOINT_URL` (for presigned URLs).

**ClickHouse оптимизация:** mark_cache 1GB → 256MB (экономия ~900MB). Добавить `max_server_memory_usage_to_ram_ratio: 0.75`, disable MySQL/PostgreSQL ports, disable verbose logs, добавить disk spilling.

**Compose naming:** `name: infra` / `name: skatelab` явно в compose-файлах. `depends_on` с `required: false` для cross-profile зависимостей.

**Backup:** `clickhouse-backup` (Altinity) вместо `clickhouse-client dump` — надёжнее, поддерживает S3 upload.

**RustFS risk:** Alpha software, crashes under high concurrency (512+ threads). `S3_*` абстракция позволяет сменить бекенд заменой endpoint.

См. полные отчёты: `research-agent-s3-migration.md`, `research-agent-compose-structure.md`, `research-agent-posthog-optimization.md`, `research-agent-env-management.md`, `research-agent-single-server.md`.

---

## 1. Три области

| Область | Путь (dedic) | Содержимое | Деплой |
|---------|-------------|-----------|--------|
| **infra** | `/opt/infra/` | Shared сервисы: PG, Valkey, RustFS, Caddy, PostHog, utility | Ручной `docker compose up -d` |
| **prod** | `/opt/skatelab/` | SkateLab app: backend, frontend, prometheus | CI/CD через GitHub Actions |
| **dev** | `/home/dev/skatelab/` | Код и файлы, никаких Docker контейнеров | Ручная разработка |

**Локальная разработка** (на машине разработчика): `infra/compose.yaml` из репо → `podman compose up valkey postgres` для зависимостей.

### Правила

- Infra compose — единственный источник правды для shared сервисов
- Prod compose — только SkateLab app, подключается к `infra_app_network`
- Внутри PG контейнера infra — отдельные DB: `skatelab` (prod), `posthog` (PostHog), `miniflux`, `windmill`, `baikal`
- PostHog сервисы — `profiles: [posthog]` в infra compose
- На dev нет контейнеров — только файлы

## 2. R2 → S3 полный рефактор

### Мотивация

R2 — Cloudflare-специфичный нейминг. RustFS — универсальный S3-совместимый бекенд. Единый набор `S3_*` переменных покрывает и SkateLab, и PostHog.

### Изменения в backend

| Файл | Было | Стало |
|------|------|-------|
| `backend/app/config.py` | `class R2Config(BaseSettings)` | `class S3Config(BaseSettings)` |
| `backend/app/config.py` | `env_prefix = "R2_"` | `env_prefix = "S3_"` |
| `backend/app/config.py` | `r2: R2Config` в AppConfig | `s3: S3Config` |
| `backend/app/storage.py` | `_R2_CONFIG` | `_S3_CONFIG` |
| `backend/app/storage.py` | `get_r2_client()` | `get_s3_client()` |
| `backend/app/storage.py` | `get_r2_async_client()` | `get_s3_async_client()` |
| `backend/app/storage.py` | `reset_r2_async_client()` | `reset_s3_async_client()` |
| `backend/app/storage.py` | `close_r2_clients()` | `close_s3_clients()` |
| `backend/app/storage.py` | `_async_client_instance`, `_credential_hash` | без изменений (внутренние) |
| `backend/app/storage.py` | Все `r2_key` переменные | `s3_key` |
| `backend/app/storage.py` | Комментарии "R2" | "S3" |
| `backend/app/vastai/client.py` | `r2_endpoint_url`, `r2_access_key_id`, `r2_secret_access_key`, `r2_bucket` | `s3_endpoint_url`, `s3_access_key_id`, `s3_secret_access_key`, `s3_bucket` |
| `backend/app/routes/uploads.py` | `from app.storage import get_r2_client` | `from app.storage import get_s3_client` |
| `backend/app/routes/uploads.py` | `r2 = get_r2_client()` | `s3 = get_s3_client()` |
| `backend/app/routes/uploads.py` | `get_settings().r2.bucket` | `get_settings().s3.bucket` |
| `backend/app/routes/misc.py` | Комментарии "R2" | "S3" |
| `backend/app/routes/choreography.py` | `r2_key`, "R2" в логах | `s3_key`, "S3" |
| `backend/app/routes/users.py` | "Upload to R2" комментарий | "Upload to S3" |

### Изменения в frontend

| Файл | Было | Стало |
|------|------|-------|
| `frontend/src/proxy.ts` | `https://*.r2.cloudflarestorage.com` | `s3.skatelab.ru` |

### Изменения в infra

| Файл | Было | Стало |
|------|------|-------|
| `.env.prod.template` | `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET` |
| `.env.prod.template` | `RUSTFS_ACCESS_KEY_ID`, `RUSTFS_SECRET_ACCESS_KEY` | Удалены (дублировали S3_*) |
| `compose.prod.yaml` | `R2_*` env vars | `S3_*` |
| `compose.yaml` (PostHog) | `RUSTFS_ACCESS_KEY_ID`, `RUSTFS_SECRET_ACCESS_KEY` | `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` |

### Новые S3 env vars (из research)

| Variable | Default | Purpose |
|----------|---------|---------|
| `S3_ENDPOINT_URL` | (required) | Internal endpoint (Docker DNS) |
| `S3_PUBLIC_ENDPOINT_URL` | `$S3_ENDPOINT_URL` | External URL для presigned URLs (future-proof) |
| `S3_ACCESS_KEY_ID` | (required) | S3 access key |
| `S3_SECRET_ACCESS_KEY` | (required) | S3 secret key |
| `S3_BUCKET` | `skatelab-pipeline` | Default bucket |
| `S3_REGION` | `us-east-1` | Region (R2 использовал `"auto"`, RustFS не распознаёт) |
| `S3_PATH_STYLE` | `true` | Обязателен для self-hosted S3 |

### Критические изменения в backend коде

**BotoConfig — path-style addressing:**
```python
# БЫЛО:
_R2_CONFIG = BotoConfig(signature_version="s3v4", ...)

# СТАЛО:
_S3_CONFIG = BotoConfig(
    signature_version="s3v4",
    s3={"addressing_style": "path"},  # ОБЯЗАТЕЛЬНО для RustFS/MinIO
    connect_timeout=10,
    read_timeout=300,
    retries={"max_attempts": 3, "mode": "adaptive"},
)
```

**region_name — `"auto"` → configurable:**
```python
# БЫЛО: region_name="auto"  (R2-specific)
# СТАЛО: region_name=s.s3.region  (default "us-east-1")
```

**S3Config — новые поля:**
```python
class S3Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="S3_")
    endpoint_url: str = ""
    public_endpoint_url: str = ""  # для presigned URLs
    access_key_id: str = ""
    secret_access_key: str = ""
    bucket: str = "skatelab-pipeline"
    region: str = "us-east-1"      # было "auto"
    path_style: bool = True        # обязательно для self-hosted
    presign_expires: int = 3600
```

### S3 endpoint

Полный переезд на RustFS. `S3_ENDPOINT_URL` всегда указывает на RustFS:
- Server: `http://infra-rustfs-1:9000` (Docker DNS)
- Local dev: `http://localhost:9000` (или не нужен — R2 отключён)
- Public: `https://s3.skatelab.ru` (Caddy reverse proxy, для presigned URLs)

Bucket `skatelab-pipeline` для SkateLab видео, bucket `posthog` для PostHog.

**RustFS НЕ создаёт buckets автоматически** — нужен init-step (через mc/aws cli или console).

### RustFS alpha risk

RustFS — alpha software (1.0.0-alpha.89), падает при высокой concurrency (512+ threads). Для нашего single-server MVP с низким трафиком — допустимо. `S3_*` абстракция позволяет сменить бекенд заменой endpoint если понадобится.

## 3. PostHog image tags — хардкод в compose

Удалить из `.env.prod.template`:
- `POSTHOG_APP_TAG`
- `POSTHOG_NODE_TAG`
- `POSTHOG_RUST_TAG`

В `compose.yaml` заменить `${POSTHOG_APP_TAG:-1.88.0}` → `1.88.0` прямо в image.

Обновление версии = правка compose.yaml + `docker compose --profile posthog up -d`.

## 4. Удаление android-emulator

Удалить каталог `infra/android-emulator/` целиком:
- `compose.yaml`
- `Containerfile`
- `supervisord.conf`
- `.containerignore`

Убрать упоминания из `infra/CLAUDE.md`.

## 5. .env.prod.template — чистая структура

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

Удалены: `TAG`, `GHCR_OWNER` (в compose.prod.yaml захардкожены), `POSTGRES_DB`/`POSTGRES_USER` (infra compose defaults), `R2_*`, `RUSTFS_*`, `POSTHOG_*_TAG`, `VALKEY_HOST_PORT`, `LOG_LEVEL`, `NEXT_PUBLIC_API_URL`.

Оставлены: `POSTGRES_PASSWORD` (нужна infra compose), `POSTHOG_SECRET_KEY`, `POSTHOG_POSTGRES_PASSWORD`, `POSTHOG_ENCRYPTION_SALT_KEYS`.

## 6. Структура файлов infra/

```
infra/
├── CLAUDE.md
├── compose.yaml           # Shared: valkey, postgres, PostHog (profile), Caddy, utility
├── compose.prod.yaml     # SkateLab app: backend, frontend, prometheus
├── .env.prod.template
├── deploy.sh
├── caddy/
│   └── Caddyfile
├── clickhouse/
│   └── config.d/
│       └── custom.xml
└── prometheus/
    ├── prometheus.yml
    └── rules/
        ├── alerts.yml
        ├── posthog.yml
        └── recording.yml
```

Удалено: `android-emulator/`, `infra/clickhouse-custom.xml` (в subdir).

### Compose project naming

```yaml
# compose.yaml
name: infra  # явное имя проекта → контейнеры infra-postgres-1, infra-valkey-1

# compose.prod.yaml
name: skatelab  # → skatelab-backend-1, skatelab-frontend-1
```

**Не использовать `container_name:`** для сервисов на `infra_app_network` — Docker auto-name `<project>-<service>-<number>` предотвращает коллизии.

### Cross-profile depends_on

PostHog сервисы зависят от core сервисов (postgres, valkey). Использовать `required: false`:

```yaml
posthog_web:
  profiles: ["posthog"]
  depends_on:
    postgres:
      condition: service_healthy
      required: false  # Compose v2.20.2+
```

Profile activation на сервере: `COMPOSE_PROFILES=posthog` в `.env` (постоянно). Локально — не ставить, PostHog не стартует.

### ClickHouse оптимизация (из research)

Текущий `custom.xml` переаллоцирован. Оптимизированный конфиг:

```xml
<clickhouse>
    <!-- Memory limits -->
    <max_server_memory_usage>4294967296</max_server_memory_usage>  <!-- 4GB -->
    <max_server_memory_usage_to_ram_ratio>0.75</max_server_memory_usage_to_ram_ratio>

    <!-- Cache: reduced from 1GB → 256MB for our dataset -->
    <mark_cache_size>268435456</mark_cache_size>
    <index_mark_cache_size>134217728</index_mark_cache_size>  <!-- 128MB, was 256MB -->

    <!-- Disable unused ports -->
    <mysql_port remove="1" />
    <postgresql_port remove="1" />

    <!-- Disable verbose system logs -->
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
        <max_bytes_to_merge_at_max_space_in_pool>268435456</max_bytes_to_merge_at_max_space_in_pool>
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

**Экономия RAM:** mark_cache -768MB, index_mark_cache -128MB, system logs ~-100MB. **~1GB освобождено** внутри 5GB Docker лимита.

### Backup improvements

**ClickHouse:** Заменить `clickhouse-client dump` на `clickhouse-backup` (Altinity):
- Поддержка `FREEZE TABLE`, инкрементальные бэкапы, S3 upload
- Docker sidecar или cron через `docker compose exec`

**PostgreSQL:** Текущий `pg_dumpall` адекватен. Для PITR — WAL-G (future).

**RustFS data:** `rclone sync` или `aws s3 sync` в отдельный backup location.

### Healthcheck ordering

```yaml
# Layer 1: Data stores (no depends_on, start first)
postgres:  healthcheck: pg_isready, start_period: 30s
valkey:    healthcheck: valkey-cli ping
rustfs:    healthcheck: curl -f http://localhost:9000/health, start_period: 15s

# Layer 2: App services
backend:   depends_on: [postgres:healthy, valkey:healthy, rustfs:healthy]

# Layer 3: Reverse proxy
caddy:     depends_on: [backend:healthy]
```

## 7. CLAUDE.md обновление

Обновить `infra/CLAUDE.md`:
- Убрать упоминания android-emulator
- Убрать `dev-postgres`/`dev-valkey` (dev — только файлы)
- Добавить чёткое описание трёх областей
- R2→S3 в Environment Variables
- Убрать POSTHOG_*_TAG из env vars
- Убрать RUSTFS_* из env vars
- Обновить Commands секцию
- Обновить Gotchas (S3_ вместо R2_/RUSTFS_)
- Добавить RustFS alpha risk note
- Добавить S3_PATH_STYLE и S3_REGION в env vars
- Добавить `name: infra` / `name: skatelab` в compose
- Добавить clickhouse-backup вместо clickhouse-client dump
- Добавить healthcheck ordering

---

## 8. Migration Checklist

1. Deploy RustFS alongside existing services в `infra/compose.yaml`
2. Create `skatelab-pipeline` bucket в RustFS console (или через `aws s3api`)
3. Обновить `backend/app/config.py`: R2Config → S3Config с новыми полями (region, path_style, public_endpoint_url)
4. Обновить `backend/app/storage.py`: `_R2_CONFIG` → `_S3_CONFIG` с `s3={"addressing_style": "path"}`, `region_name` configurable
5. Обновить все routes: `get_r2_client` → `get_s3_client`, `r2_key` → `s3_key`
6. Обновить `backend/app/vastai/client.py`: `r2_*` → `s3_*`
7. Обновить `frontend/src/proxy.ts`: CSP `*.r2.cloudflarestorage.com` → `s3.skatelab.ru`
8. Обновить `.env.prod.template`: новый формат с S3_REGION, S3_PATH_STYLE, S3_PUBLIC_ENDPOINT_URL
9. Обновить `compose.prod.yaml`: R2_* → S3_*
10. Обновить `compose.yaml` (PostHog): RUSTFS_ACCESS_KEY → S3_ACCESS_KEY_ID mapping
11. Hardcode PostHog image tags в compose.yaml (убрать переменные)
12. Delete `infra/android-emulator/`
13. Move `infra/clickhouse-custom.xml` → `infra/clickhouse/config.d/custom.xml`
14. Обновить ClickHouse config (оптимизация памяти)
15. Добавить `name: infra` / `name: skatelab` в compose файлы
16. Обновить `infra/CLAUDE.md`
17. Copy existing R2 data to RustFS: `rclone sync r2:skatelab-pipeline rustfs:skatelab-pipeline`
18. Switch endpoints, run integration tests
19. Remove R2 configuration
