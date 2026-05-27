# API Subdomain Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate API from `skatelab.ru/api/v1/*` to `api.skatelab.ru/v1/*` with zero downtime via phased dual-prefix rollout.

**Architecture:** Caddy proxies `api.skatelab.ru` → `backend:8000`. Backend temporarily serves both `/api/v1` and `/v1` prefixes. Frontend switches `API_BASE` to cross-subdomain URL with `credentials: "include"` and `EventSource({ withCredentials: true })`. Cookie domain set to `.skatelab.ru` for cross-subdomain sharing. Phase 3 removes legacy prefix.

**Tech Stack:** Caddy (reverse proxy), Litestar (Python backend), Next.js 16 (frontend), Kotlin Multiplatform (mobile)

---

## File Structure

| File | Change | Responsibility |
|------|--------|---------------|
| `infra/caddy/Caddyfile` | Modify | Add `api.skatelab.ru` block, later remove `/api/*` from `skatelab.ru` |
| `backend/app/main.py` | Modify | Dual-prefix routers, updated excludes |
| `backend/app/routes/auth.py` | Modify | Cookie `domain="skatelab.ru"`, updated `path` for refresh_token |
| `backend/app/config.py` | Modify | Add `https://skatelab.ru` to CORS defaults |
| `infra/compose.prod.yaml` | Modify | Health check path `/v1/health` (Phase 3) |
| `infra/deploy.sh` | Modify | Health check path (Phase 3) |
| `frontend/src/lib/api-client.ts` | Modify | `API_BASE` reads `NEXT_PUBLIC_API_URL` |
| `frontend/src/lib/auth.ts` | Modify | Fix 3 hardcoded `/api/v1` paths |
| `frontend/src/hooks/use-process-stream.ts` | Modify | `EventSource` with `withCredentials: true` |
| `frontend/src/proxy.ts` | Modify | Add `https://api.skatelab.ru` to CSP `connect-src` |
| `frontend/next.config.ts` | Modify | Remove `/api/:path*` rewrite |
| `mobile/androidApp/.../di/AppModule.kt` | Modify | Update `baseUrl` to `/v1` |
| `backend/tests/conftest.py` | Modify | Add `https://skatelab.ru` to mocked CORS origins |

---

## Wave 1: Backend dual-prefix + cookie domain + CORS

### Task 1: Add dual-prefix routers in `backend/app/main.py`

**Files:**

- Modify: `backend/app/main.py:89-106`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_api_prefix.py
import pytest
from litestar.testing import AsyncTestClient


@pytest.mark.asyncio
async def test_v1_prefix_routes_work(client: AsyncTestClient):
    """Routes under /v1 prefix return same responses as /api/v1."""
    response = await client.get("/v1/health")
    assert response.status_code == 200

    response_legacy = await client.get("/api/v1/health")
    assert response_legacy.status_code == 200


@pytest.mark.asyncio
async def test_v1_auth_excludes_match_api_v1(client: AsyncTestClient):
    """JWT exclude paths exist under both /v1 and /api/v1 prefixes."""
    for prefix in ["/v1", "/api/v1"]:
        resp = await client.post(f"{prefix}/auth/login", json={"email": "x@x.com", "password": "12345678"})
        # Should NOT return 401 (auth excluded) — may return 400/401/403 for bad creds
        assert resp.status_code != 405  # route exists
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_api_prefix.py -v`
Expected: FAIL — `/v1/health` returns 404 (no `/v1` router)

- [ ] **Step 3: Add dual-prefix routers**

In `backend/app/main.py`, replace lines 89-106 with:

```python
    # Assemble routers under /api/v1 (legacy) and /v1 (new)
    _handlers = [
        auth,
        users,
        detect,
        models,
        process,
        misc,
        sessions,
        metrics,
        connections,
        uploads,
        choreography,
        workspaces,
    ]

    api_v1_legacy = Router(path="/api/v1", route_handlers=_handlers)
    api_v1 = Router(path="/v1", route_handlers=_handlers)
```

Then update the `Litestar()` call on line 158-169 to include both routers:

```python
    return Litestar(
        route_handlers=[api_v1_legacy, api_v1],
        lifespan=[app_lifespan],
        cors_config=cors_config,
        compression_config=CompressionConfig(backend="gzip"),
        response_cache_config=ResponseCacheConfig(default_expiration=60),
        middleware=[rate_limit_config.middleware],
        exception_handlers={HTTPException: http_exception_handler},
        debug=settings.app.log_level == "DEBUG",
        on_app_init=init_handlers,
        dependencies=dependencies,
    )
```

- [ ] **Step 4: Update rate limit exclude paths**

Replace line 117 with dual-prefix excludes:

```python
    _prefixes = ["/api/v1", "/v1"]
    rate_limit_config = RateLimitConfig(
        rate_limit=("minute", 60),
        exclude=[f"{p}/health" for p in _prefixes]
        + [f"{p}/docs" for p in _prefixes]
        + [f"{p}/redoc" for p in _prefixes]
        + [f"{p}/openapi.json" for p in _prefixes],
    )
```

- [ ] **Step 5: Update JWT auth exclude paths**

Replace lines 124-141 with dual-prefix excludes:

```python
    jwt_auth = JWTAuth[User](
        token_secret=settings.jwt.secret_key.get_secret_value(),
        retrieve_user_handler=retrieve_user_handler,
        algorithm="HS256",  # noqa: S106
        exclude=[
            f"{p}/auth/register" for p in _prefixes
        ] + [
            f"{p}/auth/login" for p in _prefixes
        ] + [
            f"{p}/auth/refresh" for p in _prefixes
        ] + [
            f"{p}/auth/logout" for p in _prefixes
        ] + [
            f"{p}/auth/forgot-password" for p in _prefixes
        ] + [
            f"{p}/auth/reset-password" for p in _prefixes
        ] + [
            f"{p}/auth/verify-email" for p in _prefixes
        ] + [
            f"{p}/auth/resend-verification" for p in _prefixes
        ] + [
            f"{p}/health" for p in _prefixes
        ] + [
            f"{p}/models" for p in _prefixes
        ] + [
            f"{p}/outputs" for p in _prefixes
        ] + [
            f"{p}/metrics/registry" for p in _prefixes
        ] + [
            f"{p}/choreography/elements/registry" for p in _prefixes
        ] + [
            f"{p}/docs" for p in _prefixes
        ] + [
            f"{p}/redoc" for p in _prefixes
        ] + [
            f"{p}/openapi.json" for p in _prefixes
        ],
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_api_prefix.py -v`
Expected: PASS

- [ ] **Step 7: Run existing backend tests to verify no regressions**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/ -x --timeout=60`
Expected: PASS (all existing tests still use `/api/v1` which is preserved)

- [ ] **Step 8: Commit**

```bash
git add backend/app/main.py backend/tests/test_api_prefix.py
git commit -m "feat(backend): add /v1 dual-prefix router alongside /api/v1 legacy"
```

---

### Task 2: Add cookie `domain="skatelab.ru"` and update `refresh_token` path in `backend/app/routes/auth.py`

**Files:**

- Modify: `backend/app/routes/auth.py:72-115`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cookie_domain.py
import pytest
from litestar.testing import AsyncTestClient


@pytest.mark.asyncio
async def test_auth_cookies_have_domain(client: AsyncTestClient, authed_user):
    """Auth cookies set domain=.skatelab.ru for cross-subdomain sharing."""
    token = create_access_token(user_id=authed_user.id)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "pass"},
    )
    # Check Set-Cookie headers
    set_cookie_headers = [
        h for h in response.headers.getall("set-cookie") if "access_token" in h or "refresh_token" in h or "sb_auth" in h
    ]
    for header in set_cookie_headers:
        assert "domain=skatelab.ru" in header.lower() or "domain=.skatelab.ru" in header.lower(), \
            f"Cookie missing domain attribute: {header}"


@pytest.mark.asyncio
async def test_refresh_token_cookie_path_v1(client: AsyncTestClient, authed_user):
    """Refresh token cookie path works for both /api/v1/auth and /v1/auth."""
    # This test verifies the cookie path is broad enough for both prefixes
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "pass"},
    )
    set_cookie_headers = response.headers.getall("set-cookie")
    refresh_cookie = [h for h in set_cookie_headers if "refresh_token" in h]
    # Path should be / (not /api/v1/auth) so it works for /v1/auth too
    assert any("path=/" in h.lower() for h in refresh_cookie), \
        f"refresh_token cookie path not broad enough: {refresh_cookie}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_cookie_domain.py -v`
Expected: FAIL — cookies lack `domain` attribute, `refresh_token` path is `/api/v1/auth`

- [ ] **Step 3: Update `_set_auth_cookies` to add `domain` and fix `refresh_token` path**

In `backend/app/routes/auth.py`, replace `_set_auth_cookies` method (lines 72-107) with:

```python
    def _set_auth_cookies(self, response: Response, access: str, refresh: str) -> Response:
        settings = get_settings()
        response.cookies.append(
            Cookie(
                key="access_token",
                value=access,
                httponly=True,
                secure=settings.app.cookie_secure,
                samesite=settings.app.cookie_samesite,
                max_age=settings.jwt.access_token_expire_minutes * 60,
                path="/",
                domain="skatelab.ru",
            )
        )
        response.cookies.append(
            Cookie(
                key="refresh_token",
                value=refresh,
                httponly=True,
                secure=settings.app.cookie_secure,
                samesite=settings.app.cookie_samesite,
                max_age=settings.jwt.refresh_token_expire_days * 86400,
                path="/",
                domain="skatelab.ru",
            )
        )
        response.cookies.append(
            Cookie(
                key="sb_auth",
                value="1",
                httponly=False,
                secure=settings.app.cookie_secure,
                samesite=settings.app.cookie_samesite,
                max_age=settings.jwt.refresh_token_expire_days * 86400,
                path="/",
                domain="skatelab.ru",
            )
        )
        return response
```

Key changes:
- Added `domain="skatelab.ru"` to all 3 cookies
- Changed `refresh_token` `path` from `"/api/v1/auth"` to `"/"` — cookie must be sent to `/v1/auth/refresh` too, and path `/` covers both prefixes

- [ ] **Step 4: Update `_clear_auth_cookies` to add `domain` and fix path**

Replace `_clear_auth_cookies` method (lines 109-115) with:

```python
    def _clear_auth_cookies(self, response: Response) -> Response:
        response.cookies.append(
            Cookie(key="access_token", value="", max_age=0, path="/", domain="skatelab.ru")
        )
        response.cookies.append(
            Cookie(key="refresh_token", value="", max_age=0, path="/", domain="skatelab.ru")
        )
        response.cookies.append(
            Cookie(key="sb_auth", value="", max_age=0, path="/", domain="skatelab.ru")
        )
        return response
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_cookie_domain.py -v`
Expected: PASS

- [ ] **Step 6: Run existing tests for regressions**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/ -x --timeout=60`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/auth.py backend/tests/test_cookie_domain.py
git commit -m "feat(backend): add domain=skatelab.ru to auth cookies, broaden refresh_token path"
```

---

### Task 3: Add `https://skatelab.ru` to CORS origins default in `backend/app/config.py`

**Files:**

- Modify: `backend/app/config.py:90-96`
- Modify: `backend/tests/conftest.py:178,256`

- [ ] **Step 1: Update CORS defaults**

In `backend/app/config.py`, replace `CORSConfig` (lines 90-96):

```python
class CORSConfig(BaseSettings):
    """Cross-origin resource sharing."""

    origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://skatelab.ru",
    ]

    class Config:
        env_prefix = "CORS_"
```

- [ ] **Step 2: Update mocked CORS origins in test conftest**

In `backend/tests/conftest.py`, update both occurrences of `settings.cors.origins` (line 178 and line 256):

```python
settings.cors.origins = ["http://localhost:3000", "https://skatelab.ru"]
```

- [ ] **Step 3: Run backend tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/ -x --timeout=60`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py backend/tests/conftest.py
git commit -m "feat(backend): add https://skatelab.ru to CORS origins"
```

---

## Wave 2: Caddy + DNS configuration

### Task 4: Add `api.skatelab.ru` block to Caddyfile

**Files:**

- Modify: `infra/caddy/Caddyfile`

- [ ] **Step 1: Add the api subdomain block**

Add the following block BEFORE the `skatelab.ru` block in `infra/caddy/Caddyfile`:

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

**Important:** Do NOT add `encode gzip` to this block — it buffers SSE responses. `flush_interval -1` alone handles streaming.

- [ ] **Step 2: Keep existing `/api/*` handler in `skatelab.ru` block unchanged**

No changes to the `skatelab.ru` block yet. Both `skatelab.ru/api/v1/*` and `api.skatelab.ru/v1/*` will work simultaneously.

- [ ] **Step 3: Validate Caddyfile syntax**

Run: `podman exec infra-caddy-1 caddy validate --config /etc/caddy/Caddyfile`
Expected: valid config (or run locally: `caddy fmt --check infra/caddy/Caddyfile`)

- [ ] **Step 4: Commit**

```bash
git add infra/caddy/Caddyfile
git commit -m "feat(infra): add api.skatelab.ru Caddy block for /v1/* routing"
```

---

## Wave 3: Frontend migration

### Task 5: Make `API_BASE` configurable via env var in `frontend/src/lib/api-client.ts`

**Files:**

- Modify: `frontend/src/lib/api-client.ts:11`

- [ ] **Step 1: Update API_BASE to use environment variable**

Replace line 11:

```diff
- export const API_BASE = "/api/v1"
+ export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://api.skatelab.ru/v1"
```

- [ ] **Step 2: Update `sb_auth` sentinel cookie domain in `setTokens`**

In `setTokens` (line 32), update the cookie to include `Domain`:

```typescript
export function setTokens(_access: string, _refresh: string): void {
  // biome-ignore lint/suspicious/noDocumentCookie: intentional sentinel cookie for SSR gating
  document.cookie = "sb_auth=1; path=/; max-age=31536000; SameSite=Lax; Domain=skatelab.ru"
}
```

Same for `clearTokens` (line 37):

```typescript
export function clearTokens(): void {
  // biome-ignore lint/suspicious/noDocumentCookie: intentional sentinel cookie for SSR gating
  document.cookie = "sb_auth=; path=/; max-age=0; Domain=skatelab.ru"
}
```

And `silentRefresh` success (line 71):

```typescript
    // biome-ignore lint/suspicious/noDocumentCookie: intentional sentinel cookie for SSR gating
    document.cookie = "sb_auth=1; path=/; max-age=31536000; SameSite=Lax; Domain=skatelab.ru"
```

- [ ] **Step 3: Type check**

Run: `cd /home/michael/Github/skating-biomechanics-ml/frontend && bunx tsc --noEmit`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api-client.ts
git commit -m "feat(frontend): make API_BASE configurable via NEXT_PUBLIC_API_URL"
```

---

### Task 6: Fix hardcoded `/api/v1` paths in `frontend/src/lib/auth.ts`

**Files:**

- Modify: `frontend/src/lib/auth.ts:105,144,158`

- [ ] **Step 1: Replace hardcoded paths with API_BASE**

Add import at top of file (line 9 already imports from api-client):

```typescript
import { API_BASE, ApiError, apiFetch, clearTokens } from "@/lib/api-client"
```

Replace `logout` function (lines 104-111):

```typescript
export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: JSON_POST,
  }).catch(() => {})
  clearTokens()
}
```

Replace `verifyEmail` function (lines 143-155):

```typescript
export async function verifyEmail(token: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/auth/verify-email`, {
    method: "POST",
    credentials: "include",
    headers: JSON_POST,
    body: JSON.stringify({ token }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.message ?? "Verification failed")
  }
  return res.json()
}
```

Replace `resendVerification` function (lines 157-169):

```typescript
export async function resendVerification(email: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/auth/resend-verification`, {
    method: "POST",
    credentials: "include",
    headers: JSON_POST,
    body: JSON.stringify({ email }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.message ?? "Resend failed")
  }
  return res.json()
}
```

- [ ] **Step 2: Type check**

Run: `cd /home/michael/Github/skating-biomechanics-ml/frontend && bunx tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/auth.ts
git commit -m "fix(frontend): replace hardcoded /api/v1 paths with API_BASE constant"
```

---

### Task 7: Add `withCredentials: true` to EventSource in `frontend/src/hooks/use-process-stream.ts`

**Files:**

- Modify: `frontend/src/hooks/use-process-stream.ts:22-23`

- [ ] **Step 1: Update EventSource to use API_BASE and withCredentials**

Add import at top:

```typescript
import { API_BASE } from "@/lib/api-client"
```

Replace line 22-23:

```diff
-     const es = new EventSource(`/api/v1/process/${taskId}/stream`)
+     const es = new EventSource(`${API_BASE}/process/${taskId}/stream`, {
+       withCredentials: true,
+     })
```

**Critical:** `withCredentials: true` is mandatory for cross-origin EventSource. Without it, auth cookies are NOT sent to `api.skatelab.ru`.

- [ ] **Step 2: Type check**

Run: `cd /home/michael/Github/skating-biomechanics-ml/frontend && bunx tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/use-process-stream.ts
git commit -m "feat(frontend): EventSource uses API_BASE + withCredentials for cross-origin SSE"
```

---

### Task 8: Add `https://api.skatelab.ru` to CSP `connect-src` in `frontend/src/proxy.ts`

**Files:**

- Modify: `frontend/src/proxy.ts:25`

- [ ] **Step 1: Add api subdomain to production connect-src**

Replace the production `connectSrc` array (line 25):

```diff
-     : ["'self'", "blob:", "https://*.r2.cloudflarestorage.com"]
+     : ["'self'", "blob:", "https://*.r2.cloudflarestorage.com", "https://api.skatelab.ru"]
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/proxy.ts
git commit -m "feat(frontend): add https://api.skatelab.ru to CSP connect-src"
```

---

### Task 9: Remove Next.js rewrite for `/api/*` in `frontend/next.config.ts`

**Files:**

- Modify: `frontend/next.config.ts:11-13`

- [ ] **Step 1: Remove the rewrite block**

Replace `nextConfig` definition (lines 7-14):

```typescript
const nextConfig: NextConfig = {
  output: "standalone",
  images: { unoptimized: true },
  turbopack: { root: path.resolve(__dirname) },
}
```

The `async rewrites()` function is removed entirely — dev now hits backend directly via `NEXT_PUBLIC_API_URL`.

- [ ] **Step 2: Create dev `.env.local` file**

Create `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
```

- [ ] **Step 3: Add `.env.local` to `.gitignore` if not already**

Check `frontend/.gitignore` for `.env.local`. If missing, add it:

```
.env.local
```

- [ ] **Step 4: Type check**

Run: `cd /home/michael/Github/skating-biomechanics-ml/frontend && bunx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/next.config.ts
git commit -m "refactor(frontend): remove /api rewrite, dev uses NEXT_PUBLIC_API_URL directly"
```

---

## Wave 4: Mobile URL update

### Task 10: Update mobile `baseUrl` from `/api/v1` to `/v1` in `AppModule.kt`

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt:96`

- [ ] **Step 1: Update baseUrl**

Replace line 96:

```diff
-                 baseUrl = "https://api.skatelab.ru/api/v1",
+                 baseUrl = "https://api.skatelab.ru/v1",
```

- [ ] **Step 2: Run ktlint check**

Run: `cd /home/michael/Github/skating-biomechanics-ml/mobile && ./gradlew ktlintCheck`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt
git commit -m "fix(mobile): update API baseUrl from /api/v1 to /v1"
```

---

## Wave 5: Phase 3 cleanup (remove legacy prefix)

### Task 11: Remove `/api/v1` legacy router and update all paths to `/v1`

**Files:**

- Modify: `backend/app/main.py`
- Modify: `backend/app/routes/auth.py` (if any `/api/v1` references remain)
- Modify: `infra/compose.prod.yaml:24`
- Modify: `infra/deploy.sh:47`

- [ ] **Step 1: Remove legacy router from `backend/app/main.py`**

Replace the router section with single prefix:

```python
    # Assemble routers under /v1
    api_v1 = Router(
        path="/v1",
        route_handlers=[
            auth,
            users,
            detect,
            models,
            process,
            misc,
            sessions,
            metrics,
            connections,
            uploads,
            choreography,
            workspaces,
        ],
    )
```

Remove `_prefixes` list. Use single `"/v1"` for all exclude paths:

```python
    rate_limit_config = RateLimitConfig(
        rate_limit=("minute", 60),
        exclude=["/v1/health", "/v1/docs", "/v1/redoc", "/v1/openapi.json"],
    )

    jwt_auth = JWTAuth[User](
        token_secret=settings.jwt.secret_key.get_secret_value(),
        retrieve_user_handler=retrieve_user_handler,
        algorithm="HS256",
        exclude=[
            "/v1/auth/register",
            "/v1/auth/login",
            "/v1/auth/refresh",
            "/v1/auth/logout",
            "/v1/auth/forgot-password",
            "/v1/auth/reset-password",
            "/v1/auth/verify-email",
            "/v1/auth/resend-verification",
            "/v1/health",
            "/v1/models",
            "/v1/outputs",
            "/v1/metrics/registry",
            "/v1/choreography/elements/registry",
            "/v1/docs",
            "/v1/redoc",
            "/v1/openapi.json",
        ],
    )
```

Update `Litestar()` call:

```python
        route_handlers=[api_v1],
```

- [ ] **Step 2: Update health check in `infra/compose.prod.yaml`**

Replace line 24:

```diff
-       test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)\""]
+       test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=2)\""]
```

- [ ] **Step 3: Update health check in `infra/deploy.sh`**

Replace line 47:

```diff
- timeout 120 bash -c "while true; do /usr/bin/docker exec $BACKEND python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)\" 2>/dev/null && echo 'Backend healthy' && exit 0; sleep 10; done"
+ timeout 120 bash -c "while true; do /usr/bin/docker exec $BACKEND python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=2)\" 2>/dev/null && echo 'Backend healthy' && exit 0; sleep 10; done"
```

- [ ] **Step 4: Remove `/api/*` handler from `skatelab.ru` Caddy block**

In `infra/caddy/Caddyfile`, remove the `/api/*` handler from the `skatelab.ru` block:

```diff
 skatelab.ru {
   tls { ... }
   header { ... }

-  handle /api/* {
-    reverse_proxy backend:8000 {
-      health_uri /api/v1/health
-      health_interval 10s
-      health_timeout 5s
-      flush_interval -1
-      transport http {
-        read_timeout 300s
-        write_timeout 300s
-        dial_timeout 30s
-      }
-    }
-  }

-  handle /prometheus/* {
-    respond "Forbidden" 403
-  }

   handle {
     reverse_proxy frontend:3000 {
       ...
     }
   }
 }
```

Keep the `/prometheus/*` handler if it exists, or remove if no longer needed.

- [ ] **Step 5: Update test file from Task 1 to remove legacy prefix assertions**

Update `backend/tests/test_api_prefix.py` — remove `/api/v1` test or update to only test `/v1`:

```python
import pytest
from litestar.testing import AsyncTestClient


@pytest.mark.asyncio
async def test_v1_prefix_routes_work(client: AsyncTestClient):
    """Routes under /v1 prefix return expected responses."""
    response = await client.get("/v1/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_v1_auth_routes_exist(client: AsyncTestClient):
    """JWT-excluded auth routes exist under /v1."""
    resp = await client.post("/v1/auth/login", json={"email": "x@x.com", "password": "12345678"})
    assert resp.status_code != 405
```

- [ ] **Step 6: Run full backend test suite**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/ -x --timeout=60`
Expected: PASS (all tests now use `/v1` prefix — update any test that hardcodes `/api/v1`)

- [ ] **Step 7: Check for remaining `/api/v1` references in backend tests**

Run: `grep -r "/api/v1" backend/tests/`
Fix any remaining hardcoded `/api/v1` paths to `/v1`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/main.py backend/tests/test_api_prefix.py infra/compose.prod.yaml infra/deploy.sh infra/caddy/Caddyfile
git commit -m "refactor: remove legacy /api/v1 prefix, use /v1 only"
```

---

## DNS and Production Deploy (manual, outside code changes)

These steps happen on the server / Cloudflare dashboard, not in code:

1. **Add DNS A record:** `api.skatelab.ru` → `176.9.0.156` in Cloudflare (orange cloud enabled)
2. **Verify:** `dig api.skatelab.ru @1.1.1.1`
3. **Deploy Wave 1-2:** Backend dual-prefix + Caddy `api.skatelab.ru` block → `caddy reload`
4. **Verify:** `curl -I https://api.skatelab.ru/v1/health` → 200
5. **Deploy Wave 3-4:** Frontend + mobile updates
6. **Monitor:** Check Caddy access logs for 404s or 401s on `api.skatelab.ru`
7. **Deploy Wave 5:** Remove legacy prefix after confirming no old-client traffic