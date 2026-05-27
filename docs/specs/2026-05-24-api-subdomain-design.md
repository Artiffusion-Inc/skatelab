# API Subdomain Migration: skatelab.ru/api/v1 → api.skatelab.ru/v1

**Date:** 2026-05-24
**Status:** Approved (post deep-review)

## Goal

Move backend API from path-based routing (`skatelab.ru/api/v1/*`) to subdomain-based routing (`api.skatelab.ru/v1/*`). Clean domain separation: `skatelab.ru` = frontend, `api.skatelab.ru` = backend.

## Motivation

- Clean separation of concerns — frontend and API on distinct domains
- Simpler mental model for API consumers
- Foundation for future independent scaling

## Key Discovery

**Mobile app (`mobile/androidApp/.../di/AppModule.kt:96`) already hardcodes `https://api.skatelab.ru/api/v1`.** Only the path prefix needs updating to `/v1`. Mobile uses Bearer token auth (not cookies), so no CORS/cookie changes needed for mobile.

## Approach: Phased Caddy-only Migration

Single Caddy, single deploy pipeline. Phased rollout with zero-downtime via temporary dual-prefix support in backend.

## Phase 0: Pre-stage DNS (zero risk, do NOW)

Add A record in Cloudflare:

```
api.skatelab.ru  →  A  →  176.9.0.156
```

Enable Cloudflare proxy (orange cloud). Cloudflare propagation ~5 min for existing zones. Caddy auto-provisions TLS cert via DNS-01 challenge.

Verify: `dig api.skatelab.ru @1.1.1.1`

## Phase 1: Caddy overlap + Backend dual-prefix (zero downtime)

### 1a. Caddyfile (`infra/caddy/Caddyfile`)

Add new block for `api.skatelab.ru` **without removing** the old `/api/*` handler:

```caddyfile
api.skatelab.ru {
  tls {
    dns cloudflare {env.CLOUDFLARE_API_TOKEN} {
      propagation_timeout -1
    }
  }

  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    X-Content-Type-Options "nosniff"
    X-Frame-Options "DENY"
    X-XSS-Protection "1; mode=block"
    Referrer-Policy "strict-origin-when-cross-origin"
    -permissions-policy "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
  }

  handle /v1/* {
    reverse_proxy backend:8000 {
      health_uri /v1/health
      health_interval 10s
      health_timeout 5s
      flush_interval -1
      transport http {
        read_timeout 300s
        write_timeout 300s
        dial_timeout 30s
      }
    }
  }

  handle {
    respond "Not Found" 404
  }
}
```

**Important:** Do NOT add `encode gzip` to the api subdomain block — it buffers SSE responses. `flush_interval -1` alone handles streaming.

Old `skatelab.ru` block: **keep `/api/*` handler unchanged** during this phase.

### 1b. Backend dual-prefix (`backend/app/main.py`)

Mount two routers pointing to the same handlers:

```python
handlers = [auth, users, detect, models, process, misc, sessions, metrics, connections, uploads, choreography, workspaces]

api_v1_legacy = Router(path="/api/v1", route_handlers=handlers)
api_v1_new = Router(path="/v1", route_handlers=handlers)
```

Update JWT auth exclude + rate limit exclude to cover both prefixes:

```python
_prefixes = ["/api/v1", "/v1"]
jwt_exclude = [f"{p}/auth/register" for p in _prefixes] + \
              [f"{p}/auth/login" for p in _prefixes] + \
              # ... etc
rate_limit_exclude = [f"{p}/health" for p in _prefixes] + \
                     [f"{p}/docs" for p in _prefixes] + \
                     # ... etc
```

### 1c. Cookie domain (`backend/app/routes/auth.py`)

Add `domain="skatelab.ru"` (leading dot ignored per RFC 6265bis, works identically) to all auth cookies:

```python
Cookie(
    key="access_token",
    value=access,
    httponly=True,
    secure=settings.app.cookie_secure,
    samesite=settings.app.cookie_samesite,  # "lax" — sufficient for same-eTLD+1
    max_age=settings.jwt.access_token_expire_minutes * 60,
    path="/",
    domain="skatelab.ru",  # ← NEW
)
```

Same for `refresh_token` and `sb_auth` sentinel cookie.

**Why `SameSite=Lax` is sufficient:** `skatelab.ru` → `api.skatelab.ru` share eTLD+1 (`skatelab.ru`), so they are **same-site**. Lax cookies are sent on all same-site requests (GET, POST, fetch, EventSource). `SameSite=None; Secure` is unnecessary and increases CSRF surface.

**Safari caveat:** Safari bug 255524 may cause Lax cookie drops on fetch/SSE. If observed, fallback to `SameSite=None; Secure` for Safari users only.

### 1d. CORS (`backend/app/config.py`)

```python
class CORSConfig(BaseSettings):
    origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://skatelab.ru",
    ]
```

**Note:** `https://api.skatelab.ru` does NOT need to be in CORS origins — it's the API's own origin, not a consumer. Only the frontend origin (`skatelab.ru`) needs to be listed.

**Never use `"*"` with `allow_credentials=True`** — browsers reject `Access-Control-Allow-Origin: *` + `Access-Control-Allow-Credentials: true`.

### 1e. Health check (`infra/compose.prod.yaml`)

Keep pointing to `/api/v1/health` during Phase 1 (dual-prefix). Will update in Phase 3.

**After Phase 1 deploy:** Both `skatelab.ru/api/v1/*` and `api.skatelab.ru/v1/*` work. Zero downtime.

## Phase 2: Frontend + Mobile switch (after Phase 1 verified)

### 2a. Frontend `API_BASE` (`frontend/src/lib/api-client.ts`)

```diff
- export const API_BASE = "/api/v1"
+ export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://api.skatelab.ru/v1"
```

**SSR note:** Current architecture does NOT make API calls during SSR — auth gating only reads `sb_auth` cookie via `cookies()`, data fetching is client-side. So `NEXT_PUBLIC_API_URL` (build-time inlined) is sufficient. No separate server-side env var needed.

### 2b. Frontend `auth.ts` — fix hardcoded paths

Replace all hardcoded `/api/v1/auth/*` with `${API_BASE}/auth/*`:
- `logout()` (line ~105)
- `verifyEmail()` (line ~144)
- `resendVerification()` (line ~158)

### 2c. Frontend SSE (`frontend/src/hooks/use-process-stream.ts`)

```diff
- const es = new EventSource(`/api/v1/process/${taskId}/stream`)
+ const es = new EventSource(`${API_BASE}/process/${taskId}/stream`, {
+   withCredentials: true,  // REQUIRED for cross-origin cookie auth
+ })
```

**Critical:** `withCredentials: true` is mandatory. Without it, cookies are NOT sent on cross-origin EventSource connections. The browser treats `skatelab.ru` → `api.skatelab.ru` as cross-origin (different host), even though same-site.

### 2d. Frontend Next.js rewrite (`frontend/next.config.ts`)

Remove the `/api/:path*` → `localhost:8000` rewrite. Dev now hits backend directly via `NEXT_PUBLIC_API_URL`.

### 2e. Frontend CSP (`frontend/src/proxy.ts`)

Add `https://api.skatelab.ru` to `connect-src` in production CSP.

### 2f. Dev environment

```bash
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
```

### 2g. Mobile (`mobile/androidApp/.../di/AppModule.kt`)

Update hardcoded URL from `https://api.skatelab.ru/api/v1` to `https://api.skatelab.ru/v1`.

Mobile uses Bearer token auth (Ktor `Auth` plugin), not cookies. No CORS/cookie changes needed.

## Phase 3: Cleanup (after all clients migrated)

### 3a. Remove legacy router from backend

Drop `api_v1_legacy` Router. Keep only `api_v1_new = Router(path="/v1", ...)`.

Remove dual-prefix exclude lists — use `/v1/` only.

Update health check in `compose.prod.yaml`:
```diff
- urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)
+ urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=2)
```

### 3b. Remove `/api/*` handler from `skatelab.ru` Caddy block

```diff
skatelab.ru {
-  handle /api/* {
-    reverse_proxy backend:8000 { ... }
-  }
   handle {
     reverse_proxy frontend:3000 { ... }
   }
}
```

### 3c. Tests

- Backend: all route assertions `/api/v1/*` → `/v1/*`
- Backend: `conftest.py` origin stays `http://localhost:3000`
- Frontend: mock URLs use `API_BASE` constant
- Frontend test env: `NEXT_PUBLIC_API_URL=http://localhost:8000/v1`

## Parallel Deployment Strategy

| Step | Parallel? | Prerequisites | Duration |
|------|-----------|---------------|----------|
| DNS A record for `api.skatelab.ru` | Standalone | None | 5 min |
| Caddy add `api.skatelab.ru` block | After DNS | DNS verified | 30 min |
| Backend dual-prefix + cookie domain + CORS | After Caddy | Caddy serves api subdomain | 1-2 hr |
| Frontend API_BASE + EventSource + auth.ts | After backend | Backend serves `/v1` | 1-2 hr |
| Mobile URL update | After backend | Backend serves `/v1` | 30 min |
| Remove legacy router + old Caddy handler | After ALL clients migrated | Monitor 404s | 30 min |

**Steps 3-4-5 can overlap** — once backend has dual-prefix, frontend and mobile changes are independent of each other.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Cookie not sent cross-subdomain | High | `domain="skatelab.ru"` on all auth cookies. Test in staging before deploy. |
| EventSource fails cross-origin | High | `withCredentials: true` mandatory. Backend CORS must echo explicit origin (not `*`). |
| Safari drops Lax cookies on fetch/SSE | Medium | Monitor. If observed, fallback `SameSite=None; Secure`. |
| CORS preflight failure on POST | Low | Litestar CORSConfig handles preflight automatically when origin in `allow_origins`. |
| DNS propagation delay | Low | Cloudflare existing zone → ~5 min. Pre-stage before code changes. |
| Caddy TLS cert for new subdomain | Low | DNS-01 challenge auto-provisions via Cloudflare API token. |
| Double TLS (Cloudflare + Caddy) | Low | Both terminate TLS. Cloudflare-to-origin uses Full (strict) mode. Caddy cert is valid. No conflict. |
| Backend health check fails during deploy | Medium | Keep `/api/v1/health` in compose until Phase 3. |
| SSR fetch from api.skatelab.ru inside Docker | Low | Current SSR doesn't call API. If future SSR needs it, the extra network hop (container → Cloudflare → Caddy → backend) is negligible at current scale. |
| OpenAPI schema duplicates during dual-prefix | Low | Harmless for 1-2 week migration. Clean up in Phase 3. |

## Real-World References

- **GitHub API**: Always used `api.github.com` — separate subdomain from day one
- **Stripe API**: Always `api.stripe.com/v1/` — subdomain avoids migration pain
- **AWS Strangler Fig pattern**: Zero-downtime API migration via overlapping old/new paths
- **Caddy SSE**: `flush_interval -1` required; never add `encode gzip` on SSE endpoints
- **SameSite cookies**: `skatelab.ru` ↔ `api.skatelab.ru` are same-site (shared eTLD+1), `Lax` sufficient