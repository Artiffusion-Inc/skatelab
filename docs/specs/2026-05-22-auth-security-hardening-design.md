# Phase 1b: Auth/Security Hardening

**Date:** 2026-05-22
**Status:** Draft (v2 — after 5-agent deep review)
**Depends on:** Phase 1a (connection pooling) — merged
**Review report:** `docs/specs/2026-05-22-auth-security-hardening-review.md`

## Problem

1. **XSS token theft** — JWT stored in `localStorage`, accessible to any injected script. Moving to httpOnly cookies eliminates this attack vector.
2. **No email verification gate** — users can login without verifying email. Enables spam accounts and credential stuffing with unverified identities.
3. **No token binding** — refresh tokens are fully portable. A stolen token works from any device/browser without detection.
4. **Default JWT secret in production** — `JWT_SECRET_KEY` defaults to `"change-me-to-a-random-secret"`. Production deployments can accidentally run with this.
5. **No audit trail** — auth events (login, logout, token revoke, password reset) are not recorded. Impossible to investigate security incidents.
6. **Expired tokens accumulate** — `refresh_tokens` and `password_reset_tokens` grow indefinitely. No cleanup mechanism.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Auth migration | Progressive — cookie as optional layer, header still works | Zero-downtime, rollback-safe, gradual frontend migration |
| Cookie SameSite | Lax | Blocks cross-site POST/DELETE; sufficient for API-only backend; doesn't break email links |
| Email verification | Required before login | Prevents spam accounts; migration backfills existing users as verified |
| Token binding | User-Agent hash only (no IP) | IP changes on mobile networks cause false positives; UA is stable per session |
| Audit log | DB table, flush immediately | Persistent history; `await db.flush()` ensures entries persist even on read-only endpoints |
| Token cleanup | arq cron hourly (no probabilistic) | Deterministic, testable, no math surprises; lazy probabilistic ineffective under low traffic |
| JWT secret | Reject default unconditionally (with `SKIP_JWT_SECRET_CHECK` dev override) | `APP_LOG_LEVEL` is not a reliable production indicator |
| Account lockout | Not implemented | Per-endpoint rate limiting already sufficient; lockout adds UX pain |
| Frontend transition | Keep localStorage fallback for one release | Enables safe rollback if cookie auth has issues in production |

## Changes

### 1. Cookie Auth — `middleware/cookie_auth.py` (Create)

ASGI middleware: reads `access_token` httpOnly cookie and injects `Authorization: Bearer <token>` header if no `Authorization` header present.

```python
class CookieToHeaderMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            # Check if Authorization header already present
            has_auth = any(k == b"authorization" for k, _ in scope.get("headers", []))
            if not has_auth:
                # Find cookie header by iterating raw headers
                cookie_value = None
                for k, v in scope.get("headers", []):
                    if k == b"cookie":
                        cookie_value = v.decode("latin-1")
                        break
                if cookie_value:
                    for part in cookie_value.split(";"):
                        part = part.strip()
                        if "=" in part:
                            name, value = part.split("=", 1)
                            if name.strip() == "access_token":
                                # Inject Authorization header via MutableScopeHeaders
                                headers = MutableScopeHeaders(scope=scope)
                                headers["authorization"] = f"Bearer {unquote(value.strip())}"
                                break
        await self.app(scope, receive, send)
```

Wire in `main.py` via `DefineMiddleware(CookieToHeaderMiddleware)` **after** `RateLimitMiddleware` in the `middleware` list, **before** `JWTAuth` (injected via `on_app_init`). Execution order on ingress: RateLimit → CookieToHeader → JWTAuth.

### 2. Cookie Management — `routes/auth.py` (Modify)

Backend sets 3 cookies on login/register/refresh:

| Cookie | httpOnly | SameSite | Path | Max-Age |
|--------|----------|----------|------|---------|
| `access_token` | yes | Lax | `/` | `access_token_expire_minutes * 60` |
| `refresh_token` | yes | Lax | `/api/v1/auth` | `refresh_token_expire_days * 86400` |
| `sb_auth` | no | Lax | `/` | `refresh_token_expire_days * 86400` |

`sb_auth` is a non-httpOnly flag cookie for SSR: `document.cookie` readable, signals session exists without JWT decode. **Note:** `sb_auth` is readable by XSS payloads — it is a session oracle. Accepted tradeoff: the cookie only reveals whether the user is logged in, not their identity or tokens. In a future phase, replace with an httpOnly signed cookie or a lightweight `/api/v1/auth/session` endpoint.

Logout: set `max_age=0` on all 3 cookies **with matching paths** + revoke refresh token.

Helper methods on `AuthController`:

```python
def _set_auth_cookies(self, response: Response, access: str, refresh: str) -> Response:
    settings = get_settings()
    response.cookies.append(Cookie(
        key="access_token", value=access, httponly=True,
        secure=settings.app.cookie_secure, samesite=settings.app.cookie_samesite,
        max_age=settings.jwt.access_token_expire_minutes * 60, path="/",
    ))
    response.cookies.append(Cookie(
        key="refresh_token", value=refresh, httponly=True,
        secure=settings.app.cookie_secure, samesite=settings.app.cookie_samesite,
        max_age=settings.jwt.refresh_token_expire_days * 86400, path="/api/v1/auth",
    ))
    response.cookies.append(Cookie(
        key="sb_auth", value="1", httponly=False,
        secure=settings.app.cookie_secure, samesite=settings.app.cookie_samesite,
        max_age=settings.jwt.refresh_token_expire_days * 86400, path="/",
    ))
    return response

def _clear_auth_cookies(self, response: Response) -> Response:
    # Path must match the path used when setting the cookie
    response.cookies.append(Cookie(key="access_token", value="", max_age=0, path="/"))
    response.cookies.append(Cookie(key="refresh_token", value="", max_age=0, path="/api/v1/auth"))
    response.cookies.append(Cookie(key="sb_auth", value="", max_age=0, path="/"))
    return response
```

Return type changes from `TokenResponse` to `Response[TokenResponse]` for login/register/refresh/logout.

### 3. Cookie Config — `config.py` (Modify)

Add to `AppConfig`:

```python
cookie_secure: bool = False
cookie_samesite: str = "lax"
```

`cookie_secure` defaults to `False` for local dev. Production sets `APP_COOKIE_SECURE=true`.

Add startup warning: if `cookie_secure=False` and `APP_LOG_LEVEL != "DEBUG"`, log warning about non-secure cookies in production.

### 4. Frontend Cookie Migration

**`api-client.ts`:**
- Remove `TOKEN_KEY`, `REFRESH_KEY`, `getAccessToken`, `getRefreshToken`, `setTokens`, `authHeaders()`
- Add `credentials: "include"` to all `fetch()` calls
- **Keep `silentRefresh` mechanism** — on 401, call `/auth/refresh` with `credentials: "include"`, no body, then retry. Remove only `setTokens`/`localStorage` writes — trust browser cookie jar after refresh.
- `clearTokens()` only clears `sb_auth` client-side (backend handles httpOnly cookies)

**`auth.ts`:**
- Remove all localStorage token helpers
- `login()`/`register()` — no token storage, cookies set automatically by backend
- `refreshToken()` — POST `/auth/refresh` with `credentials: "include"`, no body. Backend reads `refresh_token` from cookie first, falls back to `data.refresh_token` from body for backward compat
- `logout()` — POST `/auth/logout`, clear `sb_auth`

**`auth-provider.tsx`:**
- Remove `getAccessToken()`/`getRefreshToken()` from mount check
- Check `sb_auth` cookie for session existence: `document.cookie.includes("sb_auth=1")`
- On 401 → silent refresh → retry; on refresh failure → redirect to login
- Handle 403 from `/auth/login` (email not verified) — show "resend verification" link

**`api.ts` + `choreography.ts`:**
- `detectEnqueue` — ensure `authFetch` includes `credentials: "include"`
- **`uploadMusicFile` in `lib/api/choreography.ts`** — replace hardcoded `http://localhost:8000` with env-configured base URL or Next.js proxy path (`/api/v1/...`). Replace `xhr.setRequestHeader("Authorization", ...)` with `xhr.withCredentials = true`. Remove `getAccessToken` import from `choreography/new/page.tsx`.

**Transition period:** Keep `setTokens` as a no-op stub for one release cycle so that if cookie auth is rolled back, the frontend can revert without breaking. Remove the stub in the next release.

### 5. Email Verification Gate — `routes/auth.py` (Modify)

In `AuthController.login`, after password verification:

```python
if not user.is_verified:
    raise ClientException(
        status_code=403,
        detail="Email not verified. Check your inbox.",
    )
```

**Note:** The column is `is_verified`, not `is_email_verified` (from migration `2026_05_07_1200-c7d8e9f0a1b2`).

Response includes hint for frontend to show "resend verification" link.

Migration backfill: `UPDATE users SET is_verified = TRUE WHERE is_verified = FALSE` — existing users not locked out.

### 6. User-Agent Binding — `models/refresh_token.py` + `routes/auth.py`

New column: `user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)`

On refresh token creation: `user_agent_hash = sha256(request.headers["user-agent"]).hexdigest()`

On refresh: compare current UA hash with stored. Mismatch → revoke entire family + raise 401.

```python
current_ua_hash = hashlib.sha256(
    (request.headers.get("user-agent") or "").encode()
).hexdigest()

if existing.user_agent_hash and existing.user_agent_hash != current_ua_hash:
    await revoke_family(db, existing.family_id)
    await log_auth_event(db, "ua_mismatch", user_id=existing.user_id, request=request, family_id=existing.family_id)
    raise ClientException(
        status_code=401,
        detail="Session terminated. Token used from different device.",
    )
```

Migration: `UPDATE refresh_tokens SET user_agent_hash = 'legacy' WHERE user_agent_hash IS NULL` — legacy tokens skip UA check. **Use batched update** (LIMIT 1000 per batch) to avoid row-level lock contention on large tables.

**Limitation:** UA binding is trivially bypassed by an attacker who replicates the UA string. It catches accidental token sharing and naive replay, not sophisticated token theft. Accepted tradeoff for simplicity.

### 7. Audit Log — `models/auth_audit_log.py` + `services/audit.py` + `crud/auth_audit_log.py`

**Model:**

```python
class AuthAuditLog(TimestampMixin, Base):
    __tablename__ = "auth_audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    metadata_: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

**Events:**

| Event type | When |
|------------|------|
| `login` | Successful login |
| `login_failed` | Failed login |
| `logout` | Logout |
| `refresh` | Successful refresh |
| `reuse_detected` | Refresh token reuse |
| `ua_mismatch` | UA mismatch on refresh |
| `password_reset_request` | forgot-password |
| `password_reset_complete` | reset-password success |
| `email_verify` | Email verified |
| `token_revoke` | Logout / family revoke |

**Helper:**

```python
async def log_auth_event(
    db: AsyncSession,
    event_type: str,
    *,
    user_id: str | None = None,
    request: Request | None = None,
    **metadata,
) -> None:
    ua = request.headers.get("user-agent", "")[:512] if request else None
    entry = AuthAuditLog(
        id=str(uuid4()),
        user_id=user_id,
        event_type=event_type,
        ip_address=request.client.host if request and request.client else "unknown",
        user_agent=ua,
        metadata_=metadata or None,
    )
    db.add(entry)
    await db.flush()  # Ensure entry persists even on read-only endpoints
```

Key changes from v1:
- **`await db.flush()`** added — ensures audit entries are written to DB even when the handler performs only SELECTs (e.g., failed login). Entry is still in the same transaction and will rollback if the main transaction rolls back.
- **`user_agent` truncated to 512 chars** — prevents `DataError` on long UA strings.
- **`request.client` None guard** — returns `"unknown"` instead of crashing.
- **`event_type` should use enum validation** — add a CHECK constraint or Python enum in a future phase. For now, the helper accepts any string but callers must use the defined event types above.

No query API in this phase. Read via direct SQL or future admin panel.

### 8. RefreshRequest Schema — `schemas.py` (Modify)

Make `refresh_token` optional so cookie-only refresh requests (no JSON body) pass validation:

```python
class RefreshRequest(BaseModel):
    refresh_token: str | None = None
```

In `AuthController.refresh`:

```python
refresh_from_cookie = request.cookies.get("refresh_token")
token = refresh_from_cookie or data.refresh_token
if not token:
    raise ClientException(status_code=401, detail="Refresh token required")
token_hash = hash_token(token)
```

### 9. JWT Secret Hardening — `main.py` + `config.py`

In `create_app()`, before `Litestar(...)`:

```python
from os import environ

if environ.get("SKIP_JWT_SECRET_CHECK") != "true" and settings.jwt.secret_key.get_secret_value() == "change-me-to-a-random-secret":
    raise RuntimeError(
        "JWT secret key is using the default value. "
        "Set JWT_SECRET_KEY environment variable to a secure random string. "
        "Set SKIP_JWT_SECRET_CHECK=true to bypass (dev only)."
    )
```

This is unconditional — any environment (DEBUG or not) with the default secret will fail to start. Dev must explicitly set `SKIP_JWT_SECRET_CHECK=true` or provide a real secret.

### 10. Token Cleanup

**arq cron only (no probabilistic)** — in `worker.py`, add to `FastWorkerSettings.cron_jobs`:

```python
async def cleanup_expired_tokens(ctx: dict) -> int:
    """Delete expired refresh tokens and password reset tokens."""
    from app.crud.refresh_token import cleanup_expired as cleanup_refresh
    from app.crud.password_reset_token import cleanup_expired as cleanup_reset
    from app.di import async_session_factory

    async with async_session_factory() as db:
        n1 = await cleanup_refresh(db, batch_size=500)
        n2 = await cleanup_reset(db, batch_size=500)
        await db.commit()
        return n1 + n2

# In FastWorkerSettings:
cron_jobs = [
    cron(cleanup_expired_tokens, hour="*", minute=7),  # every hour at :07
]
```

**CRUD cleanup functions** — in `crud/refresh_token.py` and `crud/password_reset_token.py`:

```python
async def cleanup_expired(db: AsyncSession, batch_size: int = 500) -> int:
    result = await db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(UTC)).limit(batch_size)
    )
    await db.flush()
    return result.rowcount
```

Deterministic, testable, no probability math. Runs hourly. Under high load with many expired tokens, `batch_size=500` prevents long-running transactions.

## Files Changed

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/middleware/cookie_auth.py` | Create | CookieToHeaderMiddleware |
| `backend/app/services/audit.py` | Create | Audit log helper |
| `backend/app/models/auth_audit_log.py` | Create | Audit log ORM model |
| `backend/app/crud/auth_audit_log.py` | Create | Audit log CRUD |
| `backend/app/models/refresh_token.py` | Modify | Add `user_agent_hash` column |
| `backend/app/routes/auth.py` | Modify | Cookie set/clear; email verify gate; UA check; audit logging; refresh dual-input |
| `backend/app/main.py` | Modify | Wire CookieToHeaderMiddleware; reject default JWT secret |
| `backend/app/config.py` | Modify | Cookie config; JWT secret validation |
| `backend/app/schemas.py` | Modify | `RefreshRequest.refresh_token` optional; 403 email-not-verified error schema |
| `backend/app/middleware/__init__.py` | Modify | Export CookieToHeaderMiddleware |
| `backend/app/worker.py` | Modify | Add cleanup cron job to FastWorkerSettings |
| `backend/app/crud/refresh_token.py` | Modify | Add UA hash on create; cleanup_expired |
| `backend/app/crud/password_reset_token.py` | Modify | cleanup_expired |
| `frontend/src/lib/api-client.ts` | Modify | Remove localStorage; add `credentials: "include"`; keep silentRefresh |
| `frontend/src/lib/auth.ts` | Modify | Remove token helpers; cookie-based auth |
| `frontend/src/components/auth-provider.tsx` | Modify | Remove token refresh logic; sb_auth cookie check |
| `frontend/src/lib/api/choreography.ts` | Modify | Replace hardcoded URL; `xhr.withCredentials`; remove getAccessToken |
| `frontend/src/app/(app)/choreography/new/page.tsx` | Modify | Remove getAccessToken import |

## Alembic Migrations

1. `add_user_agent_hash_to_refresh_tokens` — column + batched backfill `'legacy'` (LIMIT 1000 per batch)
2. `create_auth_audit_log_table` — new table with indexes
3. `set_existing_users_email_verified` — `UPDATE users SET is_verified = TRUE WHERE is_verified = FALSE`

## Risks

| Risk | Mitigation |
|------|------------|
| Frontend migration breaks existing sessions | Cookie auth is additive — header auth still works during migration |
| SameSite=Lax breaks email link flows | Lax allows top-level GET navigations; POST from email links not affected (reset uses POST from our own page) |
| UA mismatch false positives (browser updates) | Browser minor updates don't change UA string significantly; major updates are rare |
| Audit log table grows unbounded | Indexed on `user_id` + `created_at`; 90-day retention policy in future phase |
| `sb_auth` readable by XSS | Tradeoff accepted — only reveals login state, not tokens. Replace with httpOnly signed cookie in future phase |
| Rollback after partial frontend migration | Header auth continues to work; localStorage fallback kept for one release cycle |
| `uploadMusicFile` hardcoded localhost | Must fix during frontend migration — use Next.js proxy path or env-configured URL |
| Concurrent refreshes trigger reuse detection | Accepted security behavior — one refresh wins, other triggers family revocation |

## Out of Scope

- Account lockout after failed logins (rate limiting sufficient)
- CSRF double-submit token (SameSite=Lax sufficient for API-only backend)
- Access token UA binding (15-min lifetime, overhead not justified)
- IP binding on refresh (mobile networks change IP frequently)
- Audit log query API (admin panel — future phase)
- JWT secret rotation support (manual env update sufficient for current scale)
- RS256 / asymmetric JWT signing (HS256 adequate for single-service architecture)
- `__Host-` cookie prefix (requires `Secure` always; deferred until HTTPS-only deployment)
- Forced re-auth on migration (would lock out all users; consider in future phase)
- Constant-time password comparison (passlib's bcrypt.verify is already resistant for correct hashes; timing only leaks on invalid hash format)
