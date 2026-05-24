# PostHog Analytics Integration — Design Spec

**Date:** 2026-05-24
**Status:** Approved (v2 — revised after 5-agent deep research review)
**Scope:** Self-hosted PostHog on existing dedicated server, full feature set (events, session recordings, feature flags, A/B tests)

## Context

SkateLab has no analytics. Sentry handles errors only. The cookies policy already mentions PostHog as a planned integration. Need: user behavior analytics, UX analysis via session recordings, A/B tests, traffic monitoring from organic social (TikTok build-in-public).

## Infrastructure

### PostHog Self-Hosted Stack

Deploy on existing Hetzner dedic (62GB RAM, 16 vCPU, 735GB free disk) alongside existing services.

**Actual service count: ~28 containers** (not 7 as initially estimated). The official `docker-compose.hobby.yml` deploys:

**Core services:**
- `web` — Django app (UI + API)
- `worker` — Celery worker (event processing)
- `plugins` — Plugin server (Node.js)
- `clickhouse` — ClickHouse (events storage)
- `db` — PostgreSQL 15.12 (metadata + Temporal schemas)
- `kafka` — Redpanda v25.1.9 (NOT Apache Kafka — single binary, no JVM/ZooKeeper)
- `redis7` — Redis 7.2 (cache + queue, 200MB maxmemory default)

**Rust capture services:**
- `capture`, `replay-capture`, `capture-ai`, `capture-logs`

**Node.js ingestion services:**
- `ingestion-general`, `ingestion-sessionreplay`, `ingestion-error-tracking`, `ingestion-logs`, `ingestion-traces`
- `recording-api`

**Rust infrastructure services:**
- `property-defs-rs`, `feature-flags`, `personhog-replica`, `personhog-router`
- `hypercache-server`, `cyclotron-janitor`, `cymbal`

**Workflow engine:**
- `temporal`, `elasticsearch`, `temporal-admin-tools`, `temporal-ui`, `temporal-django-worker`

**Object storage (replaced by RustFS — see Shared Infrastructure section):**
- ~~`objectstorage` (MinIO)~~ — replaced by existing `infra-rustfs-1`
- ~~`seaweedfs`~~ — replaced by existing `infra-rustfs-1`

**Redis (replaced by shared Valkey — see Shared Infrastructure section):**
- ~~`redis7`~~ — replaced by existing `infra-valkey-1` (DB number 2)

### Resource Allocation (Revised)

Original spec allocated 8GB — **confirmed unstable** (GitHub Issue #27120: 8GB deployment became unresponsive after 30 minutes).

| Service | RAM | Notes |
|---------|-----|-------|
| ClickHouse | 4GB | Tuned down from 8GB default via `config.d/custom.xml` (sufficient for <1M events/mo) |
| PostgreSQL | 1GB | **Separate container** (postgres:15.12-alpine, not shared with SkateLab PG 17). See Shared Infrastructure section. |
| Redpanda (Kafka) | 3GB | Default from base.yml: `--memory 3G --reserve-memory 500M --smp 2` |
| Redis/Valkey | 0 | **Shared** with existing Valkey (DB number 2). See Shared Infrastructure section. |
| Temporal + Elasticsearch | 1GB | ES heap 256MB, Temporal ~700MB |
| Rust services (~8 containers) | 1.5GB | ~200MB each |
| Node.js services (~7 containers) | 1.5GB | ~200MB each |
| Web + Worker (Django) | 2GB | Django app + Celery |
| Caddy proxy | 0 | Use existing `infra-caddy-1` |
| **Total PostHog** | **~14.5GB** | (saved 1.5GB via shared Valkey + RustFS) |
| **Remaining for existing services** | **~47.5GB** | Out of 62GB total |

### Shared Infrastructure

**RustFS (Object Storage):** Use existing `infra-rustfs-1` instead of MinIO/SeaweedFS. PostHog needs S3-compatible storage for session recordings and plugin exports. RustFS is already deployed on the dedic and accessible at `rustfs:9000` (internal) / `s3.skatelab.ru` (external).

```
OBJECT_STORAGE_ENDPOINT=http://infra-rustfs-1:9000
OBJECT_STORAGE_ACCESS_KEY_ID=<rustfs-key>
OBJECT_STORAGE_SECRET_ACCESS_KEY=<rustfs-secret-key>
SESSION_RECORDING_V2_S3_ENDPOINT=http://infra-rustfs-1:9000
SESSION_RECORDING_V2_S3_ACCESS_KEY_ID=<rustfs-key>
SESSION_RECORDING_V2_S3_SECRET_ACCESS_KEY=<rustfs-secret-key>
```

Eliminates 2 containers (MinIO + SeaweedFS) + ~1GB RAM. Session recordings stored on local disk (~5-10GB/mo at our scale, negligible on 735GB free).

**PostgreSQL (Separate Container):** Cannot share with SkateLab PG 17. PostHog pins `postgres:15.12-alpine` — PG 17 is untested and may break Django migrations. Run a separate `postgres:15.12-alpine` container on the same host. PostgreSQL databases within different containers are fully isolated (different processes, different data directories). Memory: ~1GB (tune `shared_buffers=256MB`).

```
# In PostHog's docker-compose, override:
db:
  image: postgres:15.12-alpine
  # Separate data volume, separate port (5433 vs 5432)
```

**Valkey/Redis (Shared, DB number 2):** Share existing `infra-valkey-1` using Redis database number isolation. PostHog uses DB 2 (`SELECT 2`). Existing SkateLab services use DB 0 (default). This works because:
- Valkey supports 16 databases (DB 0-15) by default
- `FLUSHDB` only affects the selected DB, not others
- Our Valkey runs `noeviction` policy — no risk of arq queue eviction
- PostHog wants `maxmemory 200MB + allkeys-lru` — we skip this and let PostHog DB grow under the global `noeviction` policy. At our scale (<10K MAU), PostHog's Redis usage is minimal (~50MB).

Eliminates 1 container (redis7) + ~512MB RAM. Trade-off: no eviction on PostHog's keys, but acceptable at our scale.

```
# PostHog config:
REDIS_URL=redis://infra-valkey-1:6379/2
```

### ClickHouse Tuning for 1K-10K MAU

Override defaults in `config.d/custom.xml`:

```xml
<clickhouse>
    <max_server_memory_usage>4294967296</max_server_memory_usage>  <!-- 4GB -->
    <mark_cache_size>1073741824</mark_cache_size>                    <!-- 1GB -->
    <index_mark_cache_size>268435456</index_mark_cache_size>         <!-- 256MB -->
    <max_bytes_to_merge_at_max_space_in_pool>536870912</max_bytes_to_merge_at_max_space_in_pool> <!-- 512MB -->
</clickhouse>
```

Disk growth estimate: ~2.5GB/month at 1M events/month. 735GB free = 2+ years without retention cleanup.

### Reverse Proxy

Existing `infra-caddy-1` adds route. Subdomain TBD — `ph.skatelab.ru` assumed.
```
ph.skatelab.ru {
    reverse_proxy posthog_web:8000
}
```

Also route capture endpoints: `/e/*`, `/s/*`, `/i/v0/*`, `/batch/*`, `/flags/*` to the Rust capture services.

### Data Retention

| Data type | Retention |
|-----------|-----------|
| Session recordings (R2 blobs) | 30 days |
| Events (ClickHouse) | 12 months |
| ClickHouse hot data | 6 months |
| Feature flags history | 12 months |
| PostgreSQL metadata | Indefinite (backup daily) |

### Backup Strategy

| Component | Frequency | Method |
|-----------|-----------|--------|
| PostgreSQL (PostHog) | Daily | `pg_dump` both `posthog` + `posthog_persons` DBs, gzip to RustFS |
| ClickHouse | Weekly | Native `BACKUP DATABASE posthog TO S3('http://rustfs:9000/...')` (CH 26.3+) |
| Valkey | None | Ephemeral (noeviction, DB 2 is cache-only) |
| RustFS (recordings) | Local disk — rely on dedic backups | No separate action needed |

### Upgrade Strategy

**Do NOT use `docker compose pull && up -d` blindly.** 1-in-5 PostHog upgrades requires config changes.

Safe upgrade:
1. Pin to specific `POSTHOG_APP_TAG` (Docker Hub tag), not `latest`
2. Read changelog between current and target version
3. Pull during low-traffic window (have 30-min routine, 2hr for major)
4. Monitor `asyncmigrationscheck` logs for ClickHouse migration completion
5. Keep previous tag for rollback: `POSTHOG_APP_TAG=<old> docker compose up -d`

### Deployment Order

```
Phase 1: Data layer (no dependencies)
  db (PostgreSQL), redis7, Redpanda
Phase 2: Analytics engine (depends on Phase 1)
  ClickHouse (depends on kafka), R2 bucket setup
Phase 3: Processing services (depends on Phase 1-2)
  kafka-init (creates topics), then Rust + Node.js services
Phase 4: Application (depends on all above)
  web, worker, temporal
Phase 5: Proxy + verification
  Caddy route, test events, confirm data in ClickHouse
```

**Critical path:** Redpanda health. If Redpanda doesn't become healthy, nothing downstream starts.

### Monitoring PostHog

Existing Prometheus scrapes:
- ClickHouse: `http://posthog-clickhouse:8123/metrics`
- Redpanda: `http://kafka:9644/metrics`
- Node-level: existing `node_exporter`
- Docker-level: existing `cAdvisor`

Alerts: ClickHouse disk >80%, CH memory >90% of limit, Redpanda not ready, Web health check fails.

## Frontend Integration

### SDK: `@posthog/next` (not bare `posthog-js`)

**Critical change from v1 spec:** Use `@posthog/next` package instead of bare `posthog-js`. It provides:
- Server Component flag evaluation via `getPostHog()`
- `bootstrapFlags` — zero-flicker client-side flags (server evaluates, client bootstraps)
- `PostHogProvider` as React Server Component
- `PostHogFeature` for conditional rendering
- `postHogMiddleware` for identity cookie + API proxy
- Built-in App Router support (Next.js 14/15/16)

Without bootstrapping, client-side flag evaluation = ~500ms delay → visible layout shift. `@posthog/next` eliminates this.

**Tradeoff:** `bootstrapFlags` opts route into dynamic rendering (no ISR/static). Acceptable — SkateLab is an authenticated app, not a static marketing site.

### Middleware Setup

```typescript
// middleware.ts
import { postHogMiddleware } from '@posthog/next'

export default postHogMiddleware({ proxy: true })

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
```

### Provider Setup

```typescript
// app/layout.tsx
import { PostHogProvider, PostHogPageView } from '@posthog/next'

export default async function RootLayout({ children }) {
  return (
    <html lang={locale} suppressHydrationWarning>
      <body>
        <NextIntlClientProvider messages={messages}>
          <ConsentProvider>
            <PostHogProvider
              clientOptions={{
                api_host: '/ingest',
                opt_out_capturing_by_default: true,
                cookieless_mode: 'on_reject',
                capture_pageview: true,
                capture_pageleave: true,
                autocapture: true,
                session_recording: {
                  maskAllInputs: true,
                  maskTextSelector: '[data-ph-mask]',
                  maskCapturedNetworkRequestFn: (request) => {
                    if (request.name) {
                      request.name = request.name.replace(
                        /([?&](token|auth|email)=)[^&]+/g, '$1[REDACTED]'
                      )
                    }
                    return request
                  },
                },
                __add_tracing_headers: ['skatelab.ru'],
              }}
              bootstrapFlags
            >
              <PostHogPageView />
              <Providers nonce={nonce}>
                {children}
              </Providers>
            </PostHogProvider>
          </ConsentProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
```

**Key decisions:**
- `opt_out_capturing_by_default: true` — no tracking until user consents
- `cookieless_mode: 'on_reject'` — uses daily salted hash of (IP, User-Agent) for non-consenting users instead of cookies. Official PostHog GDPR pattern.
- `bootstrapFlags` — flags work immediately (functional, not tracking)
- `__add_tracing_headers` — sends `X-POSTHOG-DISTINCT-ID` + `X-POSTHOG-SESSION-ID` on API requests for session replay correlation
- `ConsentProvider` wraps `PostHogProvider` — consent state controls `opt_in_capturing()` / `opt_out_capturing()` / `startSessionRecording()` / `stopSessionRecording()`

### Env vars (frontend)

```
NEXT_PUBLIC_POSTHOG_KEY=phc_...
NEXT_PUBLIC_POSTHOG_HOST=https://ph.skatelab.ru
POSTHOG_PERSONAL_API_KEY=phx_...  # for server-side flag evaluation
```

### Flag Key Registry

```typescript
// lib/flags.ts
export const FLAGS = {
  RENEWAL_OFFER_VARIANT: 'renewal_offer_variant',
  NEW_ONBOARDING_FLOW: 'new_onboarding_flow',
  NEW_DASHBOARD: 'new_dashboard',
  THREEJS_COMPARISON: 'threejs_comparison',
} as const

export type FlagKey = (typeof FLAGS)[keyof typeof FLAGS]
```

### Cookie Consent (Opt-In) — Revised

**Key revision:** Feature flags are **functional** (infrastructure), not tracking. They must work regardless of consent.

| Category | What it enables | Default | Rationale |
|----------|----------------|---------|-----------|
| `essential` | Auth, settings, feature flags, `$feature_flag_called` events | Always on | Flags = app behavior, not tracking |
| `analytics` | PostHog events, pageviews, funnels | Off until opted in | User behavior tracking |
| `recordings` | Session recordings, heatmaps | Off until opted in | Most privacy-sensitive |

**Component: `ConsentProvider` + `ConsentBanner`**
- React context provides consent state to entire app
- Banner shown on first visit (or when `localStorage` has no consent data)
- "Accept all" / "Customize" buttons
- Consent stored in `localStorage` (`skatelab_consent` key) + cookie
- On consent change: `posthog.opt_in_capturing()` / `opt_out_capturing()`, `startSessionRecording()` / `stopSessionRecording()`

**Migration from existing cookie banner:**
- Current: `consent_accepted` = `"true"` or `"declined"` in localStorage
- On first load of new consent system:
  - `consent_accepted === "true"` → auto-migrate to `{ analytics: true, recordings: true }`
  - `consent_accepted === "declined"` → set `{ analytics: false, recordings: false }`
  - Delete old `consent_accepted` key after migration

**Behavior:**
- No consent → `opt_out_capturing_by_default: true` + `cookieless_mode: 'on_reject'` (daily salted hash, no cookies, inflated unique counts — documented limitation)
- Analytics consent → `posthog.opt_in_capturing()`, recordings off
- Analytics + recordings → `posthog.opt_in_capturing()` + `posthog.startSessionRecording()`
- `identify()` called ONLY after analytics consent (legal requirement for opt-in)

**Gotchas:**
- `persistence: 'memory'` is an anti-pattern — data lost on refresh, new session each time. Use `cookieless_mode: 'on_reject'` instead.
- Cookieless unique user counts are inflated (different daily hash = different "user"). Document for team.
- `identify()` before consent = legal risk. Guard all `identify()` calls behind consent check.
- Middleware matcher must exclude `/api/*` — `['/((?!_next/static|_next/image|favicon.ico|api).*)']`

**Legal pages update:**
- `/cookies` — add PostHog to analytics cookies section, clarify flag cookies as essential
- `/privacy` — add PostHog data processing details

### Event Tracking

**Autocaptured:**
- `$pageview` — all page transitions (after consent)
- `$autocapture` — clicks on buttons, links, form submissions (after consent)

**Manual events:**

| Event | Trigger | Properties |
|-------|---------|------------|
| `session_created` | New analysis session created | `session_id`, `video_duration_s` |
| `upload_completed` | Video upload finished | `file_size_mb`, `upload_duration_s`, `method` |
| `analysis_started` | ML pipeline dispatched | `session_id`, `gpu` |
| `analysis_completed` | Results delivered | `session_id`, `duration_s`, `elements_detected` |
| `onboarding_step` | Onboarding step completed | `step`, `role` |
| `connection_sent` | Coach invites skater | `role` |
| `choreography_created` | Choreography program created | `element_count`, `music_duration_s` |
| `renewal_offer_seen` | Renewal offer displayed | `variant`, `plan` |
| `renewal_offer_clicked` | User clicked renewal CTA | `variant`, `plan` |
| `subscription_renewed` | Renewal confirmed (backend) | `variant`, `plan` |
| `social_share_clicked` | User clicked share button | `platform`, `content_type` |
| `acquisition_source` | "How did you hear?" answered | `source` (free text) |

### User Identification

```typescript
// After login
posthog.identify(user.id, {
  email: user.email,
  role: user.onboarding_role,
  language: user.language,
  onboarding_completed: user.onboarding_completed,
})

// After logout
posthog.reset()
```

**Identity flow:** Frontend generates anonymous ID → on login, `identify(user.id)` → PostHog merges anonymous + identified person. Backend always uses `user.id` as `distinct_id` → PostHog maps correctly via merge.

**Cross-device gap:** If user clicks TikTok link on phone (anonymous ID-A) then signs up on laptop (anonymous ID-B), ID-A is never merged. Mitigation: "How did you hear about us?" onboarding question.

## Backend Integration

### SDK Setup

`posthog-python` with lazy singleton init. `disabled=True` when no API key = all calls are no-ops. Entire backend integration can be built and merged **before** PostHog is deployed.

```python
# backend/app/analytics.py
from posthog import Posthog
from app.config import get_settings

_posthog: Posthog | None = None

def get_posthog() -> Posthog:
    global _posthog
    if _posthog is not None:
        return _posthog
    settings = get_settings()
    api_key = settings.posthog.api_key.get_secret_value()
    if not api_key:
        _posthog = Posthog(api_key="", host="http://localhost:0", disabled=True)
        return _posthog
    _posthog = Posthog(
        project_api_key=api_key,
        host=settings.posthog.host,
        flush_at=50,
        flush_interval=10,
        max_queue_size=10000,
        max_retries=3,
        timeout=10,
        on_error=lambda e, batch: logger.warning("PostHog upload failed: %s", e),
        send=True,
        gzip=True,
    )
    return _posthog

def capture_event(event: str, distinct_id: str, properties: dict | None = None) -> None:
    """Fire-and-forget. Never raises. O(1) queue put — non-blocking."""
    ph = get_posthog()
    if ph.disabled:
        return
    try:
        ph.capture(event=event, distinct_id=distinct_id, properties=properties or {})
    except Exception as e:
        logger.warning("PostHog capture failed for %s: %s", event, e)

def shutdown_posthog() -> None:
    """Flush + stop consumer threads. 5s timeout to prevent hanging."""
    global _posthog
    if _posthog is None:
        return
    try:
        import signal
        old_handler = signal.signal(signal.SIGALRM, lambda *_: None)
        signal.alarm(5)
        try:
            _posthog.shutdown()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except Exception as e:
        logger.warning("PostHog shutdown error: %s", e)
    _posthog = None
```

**Key properties of `posthog-python`:**
- `capture()` = O(1) `queue.Queue.put()` — non-blocking from caller perspective
- Background daemon thread batches + sends HTTP requests
- Fork-safe: `os.register_at_fork` rebuilds queue + threads in child processes
- No async support needed — `capture()` is already non-blocking

### Config

```python
# backend/app/config.py
class PostHogConfig(BaseSettings):
    api_key: SecretStr = SecretStr("")
    host: str = "https://ph.skatelab.ru"
    class Config:
        env_prefix = "POSTHOG_"

class Settings(BaseSettings):
    # ... existing ...
    posthog: PostHogConfig = Field(default_factory=PostHogConfig)
```

Env vars: `POSTHOG_API_KEY=phc_...`, `POSTHOG_HOST=https://ph.skatelab.ru`

### Middleware: PostHog Tracing Headers

Extract `X-POSTHOG-DISTINCT-ID` and `X-POSTHOG-SESSION-ID` from frontend API requests. Store in `request.state` for session replay correlation.

```python
# backend/app/middleware/posthog_context.py
class PostHogContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.posthog_distinct_id = request.headers.get("X-POSTHOG-DISTINCT-ID")
        request.state.posthog_session_id = request.headers.get("X-POSTHOG-SESSION-ID")
        return await call_next(request)
```

### Events

```python
# backend/app/analytics_events.py — typed event functions
def analysis_completed(distinct_id: str, *, session_id: str, duration_s: float,
                        model: str, elements_count: int, gpu: str) -> None:
    capture_event("analysis_completed", distinct_id, {
        "session_id": session_id, "duration_s": round(duration_s, 2),
        "model": model, "elements_count": elements_count, "gpu": gpu,
    })

def analysis_failed(distinct_id: str, *, session_id: str,
                    error_type: str, retry_count: int) -> None:
    capture_event("analysis_failed", distinct_id, {
        "session_id": session_id, "error_type": error_type,
        "retry_count": retry_count,
    })

def vastai_dispatched(distinct_id: str, *, session_id: str,
                     instance_type: str, estimated_cost_usd: float) -> None:
    capture_event("vastai_dispatched", distinct_id, {
        "session_id": session_id, "instance_type": instance_type,
        "estimated_cost_usd": round(estimated_cost_usd, 4),
    })

def email_sent(distinct_id: str, *, template: str,
               success: bool, bounce_reason: str | None = None) -> None:
    capture_event("email_sent", distinct_id, {
        "template": template, "success": success,
        **({"bounce_reason": bounce_reason} if bounce_reason else {}),
    })

def subscription_renewed(distinct_id: str, *, variant: str, plan: str) -> None:
    capture_event("subscription_renewed", distinct_id, {
        "variant": variant, "plan": plan,
        "$feature_flag": "renewal_offer_variant",
    })
```

### Worker Integration

```python
# backend/app/worker.py — additions
async def startup(ctx: dict[str, Any]) -> None:
    from app.analytics import get_posthog
    get_posthog()  # lazy init — starts consumer thread

async def shutdown(ctx: dict[str, Any]) -> None:
    from app.analytics import shutdown_posthog
    shutdown_posthog()  # 5s timeout flush
```

### Failure Handling

- All PostHog calls: fire-and-forget, try/except, logging only
- Queue full (10K events): `capture()` blocks briefly. Our traffic will never reach this.
- Process crash: in-flight events lost (acceptable for analytics)
- PostHog down: SDK retries 3x exponential backoff, then drops batch

## A/B Tests

### Statistical Engine

PostHog uses **Bayesian statistics** (current default). Reports **chance to win** instead of p-values. Significance when chance_to_win > 95% or < 5%.

### Power Analysis at Our Scale (1K-10K MAU)

| Experiment | Variants | MDE | Required N | Months at 1K MAU | Months at 5K MAU |
|-----------|----------|-----|-----------|-------------------|-------------------|
| **Onboarding flow** | 2 + holdout | 15% | ~1,422 | **3.2 months** | 2 weeks |
| **Renewal offer (3-var)** | 3 + holdout | 20% | ~2,800 | 31 months (infeasible) | 6 months |
| **Renewal offer (2-var)** | 2 + holdout | 50% | ~450 | 5 months | 1 month |

**Decision:** Onboarding A/B first (feasible at current scale). Renewal A/B deferred to 5K+ MAU.

### Onboarding Flow A/B Test (First Experiment)

```
Flag key:          new_onboarding_flow
Type:              Multivariate (2 variants)
Variants:          control | simplified
Allocation:        45% / 45% (with 10% holdout)
Targeting:         New users only (onboarding_completed = false)
Holdout:           10% via built-in PostHog holdout feature
Goal metric:       Funnel — onboarding_step(step=completed)
Guardrail metrics (max 3-5):
  - Time to first analysis session (mean, seconds)
  - 7-day retention (funnel)
  - analysis_completed within 7 days (funnel)
Minimum detectable effect: 15%
```

**Why completion rate, not time:** Faster onboarding that produces lower-quality users (lower retention) is a net loss. Completion = goal, time = secondary, retention = guardrail.

### Renewal Offer A/B Test (Deferred)

Deferred until 5K+ MAU for statistical power. At 1K MAU, a 2-variant test with 50% MDE is the only feasible option — this gives "directional signals," not rigorous conclusions.

When launched:
```
Flag key:          renewal_offer_variant
Type:              Multivariate (start with 2 variants)
Variants:          control | discount_20 (add bonus_month at 5K+ MAU)
Allocation:        45% / 45% (10% holdout)
Targeting:         subscription_end < 14 days
Goal metric:       Funnel — renewal_offer_seen → subscription_renewed (7-day window)
Guardrail metrics:
  - Revenue per user (mean)
  - 7-day retention after renewal (funnel)
  - Support ticket rate (count)
```

### Feature Flag Architecture

**Client-side (primary):**
```typescript
// hooks/use-feature-flag.ts
'use client'
import { useFeatureFlag as usePostHogFeatureFlag } from '@posthog/next'
import type { FlagKey } from '@/lib/flags'

export function useFeatureFlagSafe(key: FlagKey) {
  const flag = usePostHogFeatureFlag(key)
  if (!flag) return { enabled: false }
  if (typeof flag === 'boolean') return { enabled: flag }
  if (typeof flag === 'string') {
    if (flag.startsWith('holdout-')) return { enabled: false }  // holdout = control
    return { enabled: true, variant: flag }
  }
  return { enabled: flag.enabled ?? false, variant: flag.variant }
}
```

**Server-side (for critical server-rendered decisions):**
```typescript
import { getPostHog } from '@posthog/next'
const posthog = await getPostHog()
const flags = await posthog.getAllFlags()
```

Requires `POSTHOG_PERSONAL_API_KEY` + `enable_local_evaluation=True`. Local evaluation polls definitions every 30s, evaluates in-process (10-20ms vs 500ms remote).

**Holdout handling:** PostHog returns `holdout-{id}` as variant. Always treat as control/default experience.

### Graduating Winning Experiments

1. Test wins → roll to 90%, keep holdout 10% for monitoring
2. Monitor 2-4 weeks (check guardrails, session replays of holdout users)
3. Full rollout → set flag to 100% test variant
4. **Remove flag code from codebase** — active flags are technical debt
5. Archive flag in PostHog UI

## Social Traffic Monitoring

### TikTok Attribution: UTM Only

**Critical finding:** TikTok's in-app browser **strips the HTTP Referer header**. Traffic without UTM shows as `$direct` in analytics. UTM parameters in the URL are preserved.

| Mechanism | Reliability |
|-----------|-------------|
| UTM parameters in URL | **HIGH** — survives in-app browser |
| PostHog autocapture (with UTM) | **HIGH** |
| HTTP Referer header | **NONE** — stripped by TikTok/Telegram IAB |
| TikTok pixel / Events API | **N/A** — requires TikTok Ads Manager |

PostHog auto-classifies `utm_source=tiktok` + `utm_medium=organic` as **Organic Video** channel type (correct for our use case).

### UTM Strategy

| Channel | URL pattern |
|---------|------------|
| TikTok bio | `skatelab.ru/tiktok?utm_source=tiktok&utm_medium=organic&utm_campaign=bio_link` |
| TikTok video | `?utm_source=tiktok&utm_medium=organic&utm_campaign=build_in_public&utm_content=v_2026_05_24` |
| Telegram | `?utm_source=telegram&utm_medium=organic&utm_campaign=channel&utm_content=post_2026_05_24` |
| WhatsApp share | `?utm_source=whatsapp&utm_medium=organic&utm_campaign=share&utm_content=session_result` |

**`utm_content` convention:** `v_YYYY_MM_DD` for TikTok videos, `post_YYYY_MM_DD` for Telegram, `share_{type}` for shares.

**Noise threshold:** Don't create >200 unique `utm_content` values. One UTM per video, not per variation.

### Custom Link-in-Bio Page

Build `skatelab.ru/tiktok` — a simple page with links to key destinations, UTM pre-baked. No third-party link-in-bio tool (full control, no redirect chain, full cookie access).

### Attribution Model

PostHog natively supports both via person properties:
- **First-touch** (primary): `Initial UTM Source`, `Initial Referrer Domain` — answers "which video drove discovery?"
- **Last-touch** (secondary): `UTM Source`, `Referrer Domain` — answers "what triggered signup?"

For content-driven marketing, first-touch is the right default.

### Cross-Device Gap

If user clicks TikTok link on phone (anonymous ID-A), then signs up on laptop (anonymous ID-B), ID-A is never merged → attribution lost.

**Mitigations:**
1. "How did you hear about us?" onboarding question → stores as `acquisition_source` person property
2. Accept the gap — inherent to web analytics without mobile app
3. Compare `Initial UTM Source` breakdown vs self-reported source to quantify gap

### Dark Social

~60-84% of sharing is "dark" (DMs, email forwards, copied links). Shows as "Direct" traffic.

**Mitigations:**
- Share buttons with auto-UTM generation
- "How did you hear?" question
- Monitor direct traffic proportion (>40% = significant dark social)
- Future: custom short domain (`sk8.link`) with server-side UTM injection

### Dashboards

**"Traffic by Source":**
- Unique visitors by `utm_source` over time (line)
- Signup conversion rate by `Initial UTM Source` (funnel)
- Signups per source (bar)

**"TikTok Performance":**
- Visitors from TikTok over time (line, filter `utm_source=tiktok`)
- Visitors by campaign (bar, breakdown `utm_campaign`)
- Visitors by video (bar, breakdown `utm_content`)
- TikTok → Signup funnel
- TikTok vs non-TikTok user quality (7-day retention)

**"Content ROI":**
- Per-video signups (table: `utm_content` × signup count)
- Top 10 videos by signups (bar)
- Content series comparison (bar: `utm_campaign`)

### UTM Generator Automation

CLI script for Алиса:
```bash
python scripts/utm_link.py --source tiktok --campaign build_in_public --content v_2026_05_24
# Output: https://skatelab.ru/?utm_source=tiktok&utm_medium=organic&utm_campaign=build_in_public&utm_content=v_2026_05_24
```

Auto-UTM on share buttons: generated URLs include platform + content type automatically.

## Parallelization Strategy

All 3 layers (infra, frontend, backend) can be built independently.

```
Week 1 (parallel):
├── [Infra] Deploy PostHog stack (data layer → processing → app)
├── [Frontend] Install @posthog/next, middleware, provider, consent banner
├── [Backend] Add analytics.py, config, middleware, events, worker hooks
├── [Content] Define UTM templates, build link-in-bio page
└── [Legal] Update cookies + privacy pages

Week 2 (parallel, depends on Week 1 infra):
├── [Frontend] Add event tracking calls, feature flags, PostHogPageView
├── [Backend] Add event calls in routes + worker tasks
├── [Infra] Verify test events in ClickHouse, set up Prometheus alerts
├── [A/B] Create onboarding experiment flag in PostHog UI
└── [Social] Create dashboards, UTM generator script

Week 3+:
├── Launch onboarding A/B experiment
├── Monitor PostHog health, dashboards, data quality
└── Renewal A/B deferred to 5K+ MAU
```

## Scope Boundaries

**In scope:**
- PostHog self-hosted deployment (16GB RAM, ~28 containers, R2 for object storage)
- Frontend: `@posthog/next`, event tracking, consent banner, feature flags
- Backend: `posthog-python`, server-side events, tracing middleware
- A/B tests: onboarding flow (now), renewal offers (deferred)
- UTM tracking for social traffic, link-in-bio page, UTM generator
- "How did you hear?" onboarding question
- Legal pages update (cookies, privacy)
- Prometheus monitoring for PostHog services
- Backup strategy (PostgreSQL daily, ClickHouse weekly)

**Out of scope:**
- PostHog plugins / third-party integrations
- Surveys / NPS
- Data export / ETL to external warehouse
- Custom short domain (`sk8.link`) — Phase 2
- Mobile app analytics
- Multi-touch attribution models beyond first/last touch
- Server-side feature flags (add only when concrete need arises)
- Renewal A/B test (deferred to 5K+ MAU)

## Research Sources

| Topic | Source |
|-------|--------|
| 8GB RAM instability | GitHub Issue #27120 |
| Docker Compose service count | PostHog `docker-compose.hobby.yml` |
| ClickHouse tuning | PostHog `config.xml` defaults |
| `@posthog/next` SSR flags | https://posthog.com/docs/libraries/next-js/posthog-next |
| Flag flicker + bootstrapping | https://posthog.com/tutorials/nextjs-bootstrap-flags |
| Bayesian statistics | https://posthog.com/docs/experiments/statistics-bayesian |
| Sample size calculator | https://posthog.com/docs/experiments/sample-size-running-time |
| Holdout groups | https://posthog.com/docs/experiments/holdouts |
| TikTok IAB referrer stripping | https://app.urlgeni.us/blog/how-in-app-browser-hurts-roi |
| PostHog UTM segmentation | https://posthog.com/docs/data/utm-segmentation |
| PostHog channel types | https://posthog.com/docs/data/channel-type |
| PostHog identity resolution | https://posthog.com/docs/product-analytics/identity-resolution |
| `posthog-python` architecture | GitHub `posthog-python/consumer.py`, `client.py` |
| FastAPI middleware PR | GitHub PR #357 (closed, not merged) |
| Upgrade reliability | Cotera.co production case study (1-in-5 breaks) |
